import datetime
from functools import partial

from qtpy import QtCore
from qtpy import QtGui
from qtpy import QtWidgets
from qtpy.QtCore import Qt
from qtpy.QtCore import Signal

from .. import actions
from .. import cmds
from .. import core
from .. import gitcmds
from .. import hotkeys
from .. import icons
from .. import textwrap
from .. import qtutils
from .. import spellcheck
from ..interaction import Interaction
from ..gitcmds import commit_message_path
from ..i18n import N_
from ..models import dag
from ..models import prefs
from ..qtutils import get
from ..utils import Group
from . import defs
from . import standard
from .selectcommits import select_commits
from .spellcheck import SpellCheckLineEdit, SpellCheckTextEdit
from .text import LineEdit, anchor_mode


class CommitMessageEditor(QtWidgets.QFrame):
    commit_finished = Signal(object)
    cursor_changed = Signal(int, int)
    down = Signal()
    up = Signal()

    def __init__(self, context, parent):
        QtWidgets.QFrame.__init__(self, parent)
        cfg = context.cfg
        self.context = context
        self.model = model = context.model
        self.spellcheck_initialized = False
        self.spellcheck = spellcheck.NorvigSpellCheck()
        self.spellcheck.set_dictionary(cfg.get('cola.dictionary', None))

        self._linebreak = None
        self._textwidth = None
        self._tabwidth = None
        self._last_commit_datetime = None  # The most recently selected commit date.
        self._last_commit_datetime_backup = None  # Used when amending.
        self._git_commit_date = None  # Overrides the commit date when committing.
        self._widgets_initialized = False  # Defers initialization of the cursor position label height.

        # Actions
        self.signoff_action = qtutils.add_action(
            self, cmds.SignOff.name(), cmds.run(cmds.SignOff, context), hotkeys.SIGNOFF
        )
        self.signoff_action.setIcon(icons.style_dialog_apply())
        self.signoff_action.setToolTip(N_('Sign off on this commit'))

        self.commit_action = qtutils.add_action(
            self, N_('Commit@@verb'), self.commit, hotkeys.APPLY
        )
        self.commit_action.setIcon(icons.commit())
        self.commit_action.setToolTip(N_('Commit staged changes'))
        self.clear_action = qtutils.add_action(self, N_('Clear...'), self.clear)

        self.launch_editor = actions.launch_editor_at_line(context, self)
        self.launch_difftool = actions.launch_difftool(context, self)

        self.move_up = actions.move_up(self)
        self.move_down = actions.move_down(self)

        # Menu actions
        self.menu_actions = menu_actions = [
            self.signoff_action,
            self.commit_action,
            None,
            self.launch_editor,
            self.launch_difftool,
            None,
            self.move_up,
            self.move_down,
            None,
        ]

        # Widgets
        self.summary = CommitSummaryLineEdit(context, check=self.spellcheck)
        self.summary.menu_actions.extend(menu_actions)
        self.summary.addAction(self.commit_action)
        self.summary.addAction(self.move_up)
        self.summary.addAction(self.move_down)
        self.summary.addAction(self.signoff_action)

        self.description = CommitMessageTextEdit(
            context, check=self.spellcheck, parent=self
        )
        self.description.menu_actions.extend(menu_actions)

        commit_button_tooltip = N_('Commit staged changes\nShortcut: Ctrl+Enter')
        self.commit_button = qtutils.create_button(
            text=N_('Commit@@verb'), tooltip=commit_button_tooltip, icon=icons.commit()
        )
        self.commit_group = Group(self.commit_action, self.commit_button)
        self.commit_progress_bar = standard.progress_bar(
            self,
            disable=(self.commit_button, self.summary, self.description),
        )

        # make the position label fixed size to avoid layout issues
        font = qtutils.default_monospace_font()
        text_width = qtutils.text_width(font, '999:999')
        cursor_position_label = self.cursor_position_label = QtWidgets.QLabel(self)
        cursor_position_label.setFont(font)
        cursor_position_label.setMinimumWidth(text_width)
        cursor_position_label.setAlignment(Qt.AlignCenter)

        self.actions_menu = qtutils.create_menu(N_('Actions'), self)
        self.actions_button = qtutils.create_toolbutton(
            icon=icons.configure(), tooltip=N_('Actions...')
        )
        self.actions_button.setMenu(self.actions_menu)
        self.actions_button.setStyleSheet("")

        self.actions_menu.addAction(self.signoff_action)
        self.actions_menu.addAction(self.commit_action)
        self.actions_menu.addSeparator()

        # Amend checkbox
        self.amend_action = self.actions_menu.addAction(N_('Amend Last Commit'))
        self.amend_action.setIcon(icons.edit())
        self.amend_action.setCheckable(True)
        self.amend_action.setShortcuts(hotkeys.AMEND)
        self.amend_action.setShortcutContext(Qt.ApplicationShortcut)

        # Commit Date
        self.commit_date_action = self.actions_menu.addAction(N_('Set Commit Date'))
        self.commit_date_action.setCheckable(True)
        self.commit_date_action.setChecked(False)
        qtutils.connect_action_bool(self.commit_date_action, self.set_commit_date)

        # Bypass hooks
        self.bypass_commit_hooks_action = self.actions_menu.addAction(
            N_('Bypass Commit Hooks')
        )
        self.bypass_commit_hooks_action.setCheckable(True)
        self.bypass_commit_hooks_action.setChecked(False)

        # Sign commits
        self.sign_action = self.actions_menu.addAction(N_('Create Signed Commit'))
        self.sign_action.setCheckable(True)
        signcommits = cfg.get('cola.signcommits', default=False)
        self.sign_action.setChecked(signcommits)

        # Spell checker
        self.check_spelling_action = self.actions_menu.addAction(N_('Check Spelling'))
        self.check_spelling_action.setCheckable(True)
        spell_check = prefs.spellcheck(context)
        self.check_spelling_action.setChecked(spell_check)
        self.toggle_check_spelling(spell_check)

        # Line wrapping
        self.autowrap_action = self.actions_menu.addAction(N_('Auto-Wrap Lines'))
        self.autowrap_action.setCheckable(True)
        self.autowrap_action.setChecked(prefs.linebreak(context))

        # Commit message
        self.actions_menu.addSeparator()
        self.load_commitmsg_menu = self.actions_menu.addMenu(
            N_('Load Previous Commit Message')
        )
        self.load_commitmsg_menu.aboutToShow.connect(self.build_commitmsg_menu)

        self.fixup_commit_menu = self.actions_menu.addMenu(N_('Fixup Previous Commit'))
        self.fixup_commit_menu.aboutToShow.connect(self.build_fixup_menu)

        self.toplayout = qtutils.hbox(
            defs.no_margin,
            defs.spacing,
            self.actions_button,
            self.summary,
            self.commit_progress_bar,
            self.cursor_position_label,
            self.commit_button,
        )

        self.mainlayout = qtutils.vbox(defs.no_margin, defs.spacing, self.toplayout, self.description)
        self.mainlayout.setContentsMargins(4, 0, 4, 0)
        self.setLayout(self.mainlayout)

        qtutils.connect_button(self.commit_button, self.commit)

        # Broadcast the amend mode
        qtutils.connect_action_bool(
            self.amend_action, partial(cmds.run(cmds.AmendMode), context)
        )
        qtutils.connect_action_bool(
            self.check_spelling_action, self.toggle_check_spelling
        )

        # Handle the one-off auto-wrapping
        qtutils.connect_action_bool(self.autowrap_action, self.set_linebreak)

        self.summary.accepted.connect(self.focus_description)
        self.summary.down_pressed.connect(self.summary_cursor_down)

        self.model.commit_message_changed.connect(
            self.set_commit_message, type=Qt.QueuedConnection
        )
        self.commit_finished.connect(self._commit_finished, type=Qt.QueuedConnection)

        self.summary.cursor_changed.connect(self.cursor_changed.emit)
        self.description.cursor_changed.connect(
            # description starts at line 2
            lambda row, col: self.cursor_changed.emit(row + 2, col)
        )
        self.summary.textChanged.connect(self.commit_summary_changed)
        self.description.textChanged.connect(self._commit_message_changed)
        self.description.leave.connect(self.focus_summary)
        self.cursor_changed.connect(self.show_cursor_position)
        # Set initial position.
        self.show_cursor_position(1, 0)

        self.commit_group.setEnabled(False)

        self.set_expandtab(prefs.expandtab(context))
        self.set_tabwidth(prefs.tabwidth(context))
        self.set_textwidth(prefs.textwidth(context))
        self.set_linebreak(prefs.linebreak(context))

        # Loading message
        commit_msg = ''
        commit_msg_path = commit_message_path(context)
        if commit_msg_path:
            commit_msg = core.read(commit_msg_path)
        model.set_commitmsg(commit_msg)

        # Allow tab to jump from the summary to the description
        self.setTabOrder(self.summary, self.description)
        self.setFont(qtutils.diff_font(context))
        self.setFocusProxy(self.summary)

        cfg.user_config_changed.connect(self.config_changed)

    def config_changed(self, key, value):
        if key != prefs.SPELL_CHECK:
            return
        if get(self.check_spelling_action) == value:
            return
        self.check_spelling_action.setChecked(value)
        self.toggle_check_spelling(value)

    def set_initial_size(self):
        self.setMaximumHeight(133)
        QtCore.QTimer.singleShot(1, self.restore_size)

    def restore_size(self):
        self.setMaximumHeight(2**13)

    def focus_summary(self):
        self.summary.setFocus()

    def focus_description(self):
        self.description.setFocus()

    def summary_cursor_down(self):
        """Handle the down key in the summary field

        If the cursor is at the end of the line then focus the description.
        Otherwise, move the cursor to the end of the line so that a
        subsequence "down" press moves to the end of the line.

        """
        self.focus_description()

    def commit_message(self, raw=True):
        """Return the commit message as a Unicode string"""
        summary = get(self.summary)
        if raw:
            description = get(self.description)
        else:
            description = self.formatted_description()
        if summary and description:
            return summary + '\n\n' + description
        if summary:
            return summary
        if description:
            return '\n\n' + description
        return ''

    def formatted_description(self):
        text = get(self.description)
        if not self._linebreak:
            return text
        return textwrap.word_wrap(text, self._tabwidth, self._textwidth)

    def commit_summary_changed(self):
        """Respond to changes to the `summary` field

        Newlines can enter the `summary` field when pasting, which is
        undesirable.  Break the pasted value apart into the separate
        (summary, description) values and move the description over to the
        "extended description" field.

        """
        value = self.summary.value()
        if '\n' in value:
            summary, description = value.split('\n', 1)
            description = description.lstrip('\n')
            cur_description = get(self.description)
            if cur_description:
                description = description + '\n' + cur_description
            # this callback is triggered by changing `summary`
            # so disable signals for `summary` only.
            self.summary.set_value(summary, block=True)
            self.description.set_value(description)
        self._commit_message_changed()

    def _commit_message_changed(self, _value=None):
        """Update the model when values change"""
        message = self.commit_message()
        self.model.set_commitmsg(message, notify=False)
        self.refresh_palettes()
        self.update_actions()

    def clear(self):
        if not Interaction.confirm(
            N_('Clear commit message?'),
            N_('The commit message will be cleared.'),
            N_('This cannot be undone.  Clear commit message?'),
            N_('Clear commit message'),
            default=True,
            icon=icons.discard(),
        ):
            return
        self.model.set_commitmsg('')

    def update_actions(self):
        commit_enabled = bool(get(self.summary))
        self.commit_group.setEnabled(commit_enabled)

    def refresh_palettes(self):
        """Update the color palette for the hint text"""
        self.description.hint.refresh()

    def set_commit_message(self, message):
        """Set the commit message to match the observed model"""
        # Parse the "summary" and "description" fields
        lines = message.splitlines()

        num_lines = len(lines)

        if num_lines == 0:
            # Message is empty
            summary = ''
            description = ''

        elif num_lines == 1:
            # Message has a summary only
            summary = lines[0]
            description = ''

        elif num_lines == 2:
            # Message has two lines; this is not a common case
            summary = lines[0]
            description = lines[1]

        else:
            # Summary and several description lines
            summary = lines[0]
            if lines[1]:
                # We usually skip this line but check just in case
                description_lines = lines[1:]
            else:
                description_lines = lines[2:]
            description = '\n'.join(description_lines)

        focus_summary = not summary
        focus_description = not description

        # Update summary
        self.summary.set_value(summary, block=True)

        # Update description
        self.description.set_value(description, block=True)

        # Update text color
        self.refresh_palettes()

        # Focus the empty summary or description
        if focus_summary:
            self.summary.setFocus()
        elif focus_description:
            self.description.setFocus()
        else:
            self.summary.cursor_position.emit()

        self.update_actions()

    def set_expandtab(self, value):
        self.description.set_expandtab(value)

    def set_tabwidth(self, width):
        self._tabwidth = width
        self.description.set_tabwidth(width)

    def set_textwidth(self, width):
        self._textwidth = width
        self.description.set_textwidth(width)

    def set_linebreak(self, brk):
        self._linebreak = brk
        self.description.set_linebreak(brk)
        with qtutils.BlockSignals(self.autowrap_action):
            self.autowrap_action.setChecked(brk)

    def setFont(self, font):
        """Pass the setFont() calls down to the text widgets"""
        self.summary.setFont(font)
        self.description.setFont(font)

    def set_mode(self, mode):
        can_amend = not self.model.is_merging
        checked = mode == self.model.mode_amend
        with qtutils.BlockSignals(self.amend_action):
            self.amend_action.setEnabled(can_amend)
            self.amend_action.setChecked(checked)
        # Store/restore the last commit date when amending.
        if checked:
            self._last_commit_datetime_backup = self._last_commit_datetime
            self._last_commit_datetime = _get_latest_commit_datetime(self.context)
        else:
            self._last_commit_datetime = self._last_commit_datetime_backup
            self._last_commit_datetime_backup = None

    def commit(self):
        """Attempt to create a commit from the index and commit message."""
        context = self.context
        if not bool(get(self.summary)):
            # Describe a good commit message
            error_msg = N_(
                'Please supply a commit message.\n\n'
                'A good commit message has the following format:\n\n'
                '- First line: Describe in one sentence what you did.\n'
                '- Second line: Blank\n'
                '- Remaining lines: Describe why this change is good.\n'
            )
            Interaction.log(error_msg)
            Interaction.information(N_('Missing Commit Message'), error_msg)
            return

        msg = self.commit_message(raw=False)

        # We either need to have something staged, or be merging.
        # If there was a merge conflict resolved, there may not be anything
        # to stage, but we still need to commit to complete the merge.
        if not (self.model.staged or self.model.is_merging):
            error_msg = N_(
                'No changes to commit.\n\n'
                'You must stage at least 1 file before you can commit.'
            )
            if self.model.modified:
                informative_text = N_(
                    'Would you like to stage and commit all modified files?'
                )
                if not Interaction.confirm(
                    N_('Stage and commit?'),
                    error_msg,
                    informative_text,
                    N_('Stage and Commit'),
                    default=True,
                    icon=icons.save(),
                ):
                    return
            else:
                Interaction.information(N_('Nothing to commit'), error_msg)
                return
            cmds.do(cmds.StageModified, context)

        # Warn that amending published commits is generally bad
        amend = get(self.amend_action)
        check_published = prefs.check_published_commits(context)
        if (
            amend
            and check_published
            and self.model.is_commit_published()
            and not Interaction.confirm(
                N_('Rewrite Published Commit?'),
                N_(
                    'This commit has already been published.\n'
                    'This operation will rewrite published history.\n'
                    "You probably don't want to do this."
                ),
                N_('Amend the published commit?'),
                N_('Amend Commit'),
                default=False,
                icon=icons.save(),
            )
        ):
            return

        sign = get(self.sign_action)
        no_verify = get(self.bypass_commit_hooks_action)
        self.bypass_commit_hooks_action.setChecked(False)
        if self.commit_date_action.isChecked():
            self.commit_date_action.setChecked(False)
            date = self._git_commit_date
        else:
            date = None

        task = qtutils.SimpleTask(
            cmds.run(
                cmds.Commit,
                context,
                amend,
                msg,
                sign,
                no_verify=no_verify,
                date=date,
            )
        )
        self.context.runtask.start(
            task,
            finish=self.commit_finished.emit,
            progress=self.commit_progress_bar,
        )

    def _commit_finished(self, task):
        """Reset widget state on completion of the commit task"""
        title = N_('Commit failed')
        status, out, err = task.result
        Interaction.command(title, 'git commit', status, out, err)
        self.setFocus()

    def build_fixup_menu(self):
        self.build_commits_menu(
            cmds.LoadFixupMessage,
            self.fixup_commit_menu,
            self.choose_fixup_commit,
            prefix='fixup! ',
        )

    def build_commitmsg_menu(self):
        self.build_commits_menu(
            cmds.LoadCommitMessageFromOID,
            self.load_commitmsg_menu,
            self.choose_commit_message,
        )

    def build_commits_menu(self, cmd, menu, chooser, prefix=''):
        context = self.context
        params = dag.DAG('HEAD', 6)
        commits = dag.RepoReader(context, params)

        menu_commits = []
        for idx, commit in enumerate(commits.get()):
            menu_commits.insert(0, commit)
            if idx > 5:
                continue

        menu.clear()
        for commit in menu_commits:
            menu.addAction(prefix + commit.summary, cmds.run(cmd, context, commit.oid))

        if len(commits) == 6:
            menu.addSeparator()
            menu.addAction(N_('More...'), chooser)

    def choose_commit(self, cmd):
        context = self.context
        revs, summaries = gitcmds.log_helper(context)
        oids = select_commits(
            context, N_('Select Commit'), revs, summaries, multiselect=False
        )
        if not oids:
            return
        oid = oids[0]
        cmds.do(cmd, context, oid)

    def choose_commit_message(self):
        self.choose_commit(cmds.LoadCommitMessageFromOID)

    def choose_fixup_commit(self):
        self.choose_commit(cmds.LoadFixupMessage)

    def toggle_check_spelling(self, enabled):
        spell_check = self.spellcheck
        cfg = self.context.cfg

        if prefs.spellcheck(self.context) != enabled:
            cfg.set_user(prefs.SPELL_CHECK, enabled)
        if enabled and not self.spellcheck_initialized:
            # Add our name to the dictionary
            self.spellcheck_initialized = True
            user_name = cfg.get('user.name')
            if user_name:
                for part in user_name.split():
                    spell_check.add_word(part)

            # Add our email address to the dictionary
            user_email = cfg.get('user.email')
            if user_email:
                for part in user_email.split('@'):
                    for elt in part.split('.'):
                        spell_check.add_word(elt)

            # git jargon
            spell_check.add_word('Acked')
            spell_check.add_word('Signed')
            spell_check.add_word('Closes')
            spell_check.add_word('Fixes')

        self.description.highlighter.enable(enabled)

    def show_cursor_position(self, rows, cols):
        """Display the cursor position with warnings and error colors for long lines"""
        display_content = '%02d:%02d' % (rows, cols)
        if cols > 78:
            color = 'red'
        elif cols > 72:
            color = '#ff8833'
        elif cols > 64:
            color = 'yellow'
        else:
            color = ''
        if color:
            radius = defs.small_icon // 2
            stylesheet = f"""
                color: black;
                background-color: {color};
                border-radius: {radius}px;
            """
        else:
            stylesheet = ''
        self.cursor_position_label.setStyleSheet(stylesheet)
        self.cursor_position_label.setText(display_content)

    def set_commit_date(self, enabled):
        """Choose the date and time that is used when authoring commits"""
        if not enabled:
            self._git_commit_date = None
            return
        widget = CommitDateDialog(
            self, self.context, commit_datetime=self._last_commit_datetime
        )
        if widget.exec_() == QtWidgets.QDialog.Accepted:
            commit_date = widget.commit_date()
            Interaction.log(N_('Setting commit date to %s') % commit_date)
            self._git_commit_date = commit_date
            self._last_commit_datetime = CommitDateDialog.tick_time(widget.datetime())
        else:
            self.commit_date_action.setChecked(False)

    # Qt overrides
    def showEvent(self, event):
        """Resize the position label once the sizes are known"""
        super().showEvent(event)
        if not self._widgets_initialized:
            self._widgets_initialized = True
            height = self.summary.height()
            self.commit_button.setMinimumHeight(height)
            self.cursor_position_label.setMaximumHeight(defs.small_icon + defs.spacing)
            self.commit_progress_bar.setMaximumHeight(height - 2)
            self.commit_progress_bar.setMaximumWidth(self.commit_button.width())


def _get_latest_commit_datetime(context):
    """Query the commit time from Git or fallback to the current time when unavailable"""
    commit_datetime = datetime.datetime.now()
    status, out, _ = context.git.log('-1', '--format=%aI', 'HEAD')
    if status != 0 or not out:
        return commit_datetime
    try:
        commit_datetime = datetime.datetime.fromisoformat(out)
    except ValueError:
        pass
    return commit_datetime


class CommitDateDialog(QtWidgets.QDialog):
    """Choose the date and time used when authoring commits"""

    slider_range = 500

    def __init__(self, parent, context, commit_datetime=None):
        QtWidgets.QDialog.__init__(self, parent)
        slider_range = self.slider_range
        self.context = context
        self._calendar_widget = calendar_widget = QtWidgets.QCalendarWidget()
        self._time_widget = time_widget = QtWidgets.QTimeEdit()
        time_widget.setDisplayFormat('hh:mm:ss AP')

        # Horizontal slider moves the date and time backwards and forwards.
        self._slider = slider = QtWidgets.QSlider(Qt.Horizontal)
        slider.setRange(0, slider_range)  # Mapped from 00:00:00 to 23:59:59

        self._tick_backward = tick_backward = qtutils.create_toolbutton_with_callback(
            partial(self._adjust_slider, -1),
            '-',
            None,
            N_('Decrement'),
            repeat=True,
        )
        self._tick_forward = tick_forward = qtutils.create_toolbutton_with_callback(
            partial(self._adjust_slider, 1),
            '+',
            None,
            N_('Increment'),
            repeat=True,
        )
        self._reset_to_commit = (
            reset_to_commit
        ) = qtutils.create_toolbutton_with_callback(
            self._reset_commit_time,
            None,
            icons.sync(),
            N_('Reset time to latest commit'),
        )

        cancel_button = QtWidgets.QPushButton(N_('Cancel'))
        cancel_button.setIcon(icons.close())

        set_commit_time_button = QtWidgets.QPushButton(N_('Set Date and Time'))
        set_commit_time_button.setDefault(True)
        set_commit_time_button.setIcon(icons.ok())

        button_layout = qtutils.hbox(
            defs.no_margin,
            defs.button_spacing,
            cancel_button,
            qtutils.STRETCH,
            set_commit_time_button,
        )
        slider_layout = qtutils.hbox(
            defs.no_margin,
            defs.spacing,
            tick_backward,
            slider,
            tick_forward,
            reset_to_commit,
            time_widget,
        )
        layout = qtutils.vbox(
            defs.small_margin,
            defs.spacing,
            calendar_widget,
            slider_layout,
            defs.button_spacing,
            button_layout,
        )
        self.setLayout(layout)
        self.setWindowTitle(N_('Set Commit Date'))
        self.setWindowModality(Qt.ApplicationModal)

        if commit_datetime is None:
            commit_datetime = self.tick_time(_get_latest_commit_datetime(context))
        time_widget.setTime(commit_datetime.time())
        calendar_widget.setSelectedDate(commit_datetime.date())
        self._update_slider_from_datetime(commit_datetime)

        self._right_action = qtutils.add_action(
            self, N_('Increment'), partial(self._adjust_slider, 1), hotkeys.CTRL_RIGHT
        )
        self._left_action = qtutils.add_action(
            self, N_('Decrement'), partial(self._adjust_slider, -1), hotkeys.CTRL_LEFT
        )

        time_widget.timeChanged.connect(self._update_slider_from_time_signal)
        slider.valueChanged.connect(self._update_time_from_slider)
        calendar_widget.activated.connect(lambda _: self.accept())

        cancel_button.clicked.connect(self.reject)
        set_commit_time_button.clicked.connect(self.accept)

    @classmethod
    def tick_time(cls, commit_datetime):
        """Tick time forward"""
        seconds_per_day = 86400
        seconds_range = seconds_per_day - 1
        one_tick = seconds_range // cls.slider_range  # 172 seconds (2m52s)
        return commit_datetime + datetime.timedelta(seconds=one_tick)

    def datetime(self):
        """Return the calculated datetime value"""
        # Combine the calendar widget's date with the time widget's time.
        time_value = self._time_widget.time().toPyTime()
        date_value = self._calendar_widget.selectedDate().toPyDate()
        date_time = datetime.datetime(
            date_value.year,
            date_value.month,
            date_value.day,
            time_value.hour,
            time_value.minute,
            time_value.second,
        )
        return date_time.astimezone()

    def commit_date(self):
        """Return the selected datetime as a string for use by Git"""
        return self.datetime().strftime('%a %b %d %H:%M:%S %Y %z')

    def _update_time_from_slider(self, value):
        """Map the slider value to an offset corresponding to the current time.

        The passed-in value will be between 0 and range.
        """
        seconds_per_day = 86400
        seconds_range = seconds_per_day - 1
        ratio = value / self.slider_range
        delta = datetime.timedelta(seconds=int(ratio * seconds_range))
        midnight = datetime.datetime(1999, 12, 31)
        new_time = (midnight + delta).time()
        time_widget = self._time_widget
        with qtutils.BlockSignals(time_widget):
            time_widget.setTime(new_time)

    def _adjust_slider(self, amount):
        """Adjust the slider forward or backwards"""
        new_value = self._slider.value() + amount
        self._slider.setValue(new_value)

    def _update_slider_from_time_signal(self, new_time):
        """Update the time slider to match the new time"""
        self._update_slider_from_time(new_time.toPyTime())

    def _update_slider_from_datetime(self, commit_datetime):
        """Update the time slider to match the specified datetime"""
        commit_time = commit_datetime.time()
        self._update_slider_from_time(commit_time)

    def _update_slider_from_time(self, commit_time):
        """Update the slider to match the specified time."""
        seconds_since_midnight = (
            60 * 60 * commit_time.hour + 60 * commit_time.minute + commit_time.second
        )
        seconds_per_day = 86400
        seconds_range = seconds_per_day - 1
        ratio = seconds_since_midnight / seconds_range
        value = int(self.slider_range * ratio)
        with qtutils.BlockSignals(self._slider):
            self._slider.setValue(value)

    def _reset_commit_time(self):
        """Reset the commit time to match the most recent commit"""
        commit_datetime = _get_latest_commit_datetime(self.context)
        with qtutils.BlockSignals(self._time_widget):
            self._time_widget.setTime(commit_datetime.time())
        with qtutils.BlockSignals(self._calendar_widget):
            self._calendar_widget.setSelectedDate(commit_datetime.date())
        self._update_slider_from_datetime(commit_datetime)


class CommitSummaryLineEdit(LineEdit):
    """Text input field for the commit summary"""

    down_pressed = Signal()
    accepted = Signal()

    def __init__(self, context, check=None, parent=None):
        super().__init__(parent)
        hint = N_('Commit summary')
        self.setPlaceholderText(hint)
        self._comment_char = None

        self.textChanged.connect(self._update_summary_text, Qt.QueuedConnection)
        context.cfg.updated.connect(self._refresh_config, type=Qt.QueuedConnection)

    def _refresh_config(self):
        """Update comment char in response to config changes"""

    def _update_summary_text(self):
        """Prevent commit messages from starting with comment characters"""
        value = self.value()
        if self._comment_char and value.startswith(self._comment_char):
            cursor = self.textCursor()
            position = cursor.position()

            value = value.lstrip()
            if self._comment_char:
                value = value.lstrip(self._comment_char).lstrip()

            self.set_value(value, block=True)

            value = self.value()
            if position > 1:
                position = max(0, min(position - 1, len(value) - 1))
                cursor.setPosition(position)
                self.setTextCursor(cursor)


class CommitMessageTextEdit(SpellCheckTextEdit):
    leave = Signal()

    def __init__(self, context, check=None, parent=None):
        hint = N_('Extended description...')
        SpellCheckTextEdit.__init__(self, context, hint, check=check, parent=parent)

        self.action_emit_leave = qtutils.add_action(
            self, 'Shift Tab', self.leave.emit, hotkeys.LEAVE
        )

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Up:
            cursor = self.textCursor()
            position = cursor.position()
            if position == 0:
                # The cursor is at the beginning of the line.
                # If we have selection then simply reset the cursor.
                # Otherwise, emit a signal so that the parent can
                # change focus.
                if cursor.hasSelection():
                    self.set_cursor_position(0)
                else:
                    self.leave.emit()
                event.accept()
                return
            text_before = self.toPlainText()[:position]
            lines_before = text_before.count('\n')
            if lines_before == 0:
                # If we're on the first line, but not at the
                # beginning, then move the cursor to the beginning
                # of the line.
                if event.modifiers() & Qt.ShiftModifier:
                    mode = QtGui.QTextCursor.KeepAnchor
                else:
                    mode = QtGui.QTextCursor.MoveAnchor
                cursor.setPosition(0, mode)
                self.setTextCursor(cursor)
                event.accept()
                return
        elif event.key() == Qt.Key_Down:
            cursor = self.textCursor()
            position = cursor.position()
            all_text = self.toPlainText()
            text_after = all_text[position:]
            lines_after = text_after.count('\n')
            if lines_after == 0:
                select = event.modifiers() & Qt.ShiftModifier
                mode = anchor_mode(select)
                cursor.setPosition(len(all_text), mode)
                self.setTextCursor(cursor)
                event.accept()
                return
        SpellCheckTextEdit.keyPressEvent(self, event)

    def setFont(self, font):
        SpellCheckTextEdit.setFont(self, font)
        width, height = qtutils.text_size(font, 'MMMM')
        self.setMinimumSize(QtCore.QSize(width, height * 2))
