"""The only file where icon filenames are mentioned"""
import os

from qtpy import QtGui
from qtpy import QtWidgets

from . import core
from . import decorators
from . import qtcompat
from . import resources
from .compat import ustr
from .i18n import N_


KNOWN_FILE_MIME_TYPES = [
    ('text', 'file-code.svg'),
    ('image', 'file-media.svg'),
    ('octet', 'file-binary.svg'),
]

KNOWN_FILE_EXTENSIONS = {
    '.bash': 'file-code.svg',
    '.c': 'file-code.svg',
    '.cpp': 'file-code.svg',
    '.css': 'file-code.svg',
    '.cxx': 'file-code.svg',
    '.h': 'file-code.svg',
    '.hpp': 'file-code.svg',
    '.hs': 'file-code.svg',
    '.html': 'file-code.svg',
    '.java': 'file-code.svg',
    '.js': 'file-code.svg',
    '.ksh': 'file-code.svg',
    '.lisp': 'file-code.svg',
    '.perl': 'file-code.svg',
    '.pl': 'file-code.svg',
    '.py': 'file-code.svg',
    '.rb': 'file-code.svg',
    '.rs': 'file-code.svg',
    '.sh': 'file-code.svg',
    '.zsh': 'file-code.svg',
}


def install(themes):
    for theme in themes:
        icon_dir = resources.icon_dir(theme)
        qtcompat.add_search_path('icons', icon_dir)


def icon_themes():
    return (
        (N_('Default'), 'default'),
        (N_('Dark Theme'), 'dark'),
        (N_('Light Theme'), 'light'),
    )


def name_from_basename(basename):
    """Prefix the basename with "icons:" so that git-cola's icons are found

    "icons" is registered with the Qt resource system during install().

    """
    return 'icons:' + basename


@decorators.memoize
def from_name(name):
    """Return a QIcon from an absolute filename or "icons:basename.svg" name"""
    return QtGui.QIcon(name)


def icon(basename):
    """Given a basename returns a QIcon from the corresponding cola icon"""
    return from_name(name_from_basename(basename))


def from_theme(name, fallback=None):
    """Grab an icon from the current theme with a fallback

    Support older versions of Qt checking for fromTheme's availability.

    """
    if hasattr(QtGui.QIcon, 'fromTheme'):
        base, _ = os.path.splitext(name)
        if fallback:
            qicon = QtGui.QIcon.fromTheme(base, icon(fallback))
        else:
            qicon = QtGui.QIcon.fromTheme(base)
        if not qicon.isNull():
            return qicon
    return icon(fallback or name)


def basename_from_filename(filename):
    """Returns an icon name based on the filename"""
    mimetype = core.guess_mimetype(filename)
    if mimetype is not None:
        mimetype = mimetype.lower()
        for filetype, icon_name in KNOWN_FILE_MIME_TYPES:
            if filetype in mimetype:
                return icon_name
    extension = os.path.splitext(filename)[1]
    return KNOWN_FILE_EXTENSIONS.get(extension.lower(), 'file-text.svg')


def from_filename(filename):
    """Return a QIcon from a filename"""
    basename = basename_from_filename(filename)
    return from_name(name_from_basename(basename))


def mkicon(value, default=None):
    """Create an icon from a string value"""
    if value is None and default is not None:
        value = default()
    elif value and isinstance(value, (str, ustr)):
        value = QtGui.QIcon(value)
    return value


def from_style(key):
    """Maintain a cache of standard icons and return cache entries."""
    style = QtWidgets.QApplication.instance().style()
    return style.standardIcon(key)


def status(filename, deleted, is_staged, untracked):
    """Status icon for a file"""
    if deleted:
        icon_name = 'circle-slash-red.svg'
    elif is_staged:
        icon_name = 'staged.svg'
    elif untracked:
        icon_name = 'question-plain.svg'
    else:
        icon_name = basename_from_filename(filename)
    return icon_name


# Icons creators and SVG file references


def three_bars():
    """Three-bars icon"""
    return from_theme('view-list-text', fallback='three-bars.svg')


def add():
    """Add icon"""
    return from_theme('list-add', fallback='plus.svg')


def alphabetical():
    """Alphabetical icon"""
    return from_theme('view-sort-ascending', fallback='a-z-order.svg')


def branch():
    """Branch icon"""
    return from_theme('vcs-branch', fallback='git-branch.svg')


def check_name():
    """Check mark icon name"""
    return name_from_basename('check.svg')
    return from_theme('checkmark', fallback='check.svg')


def cherry_pick():
    """Cherry-pick icon"""
    return icon('git-commit.svg')


def circle_slash_red():
    """A circle with a slash through it"""
    return icon('circle-slash-red.svg')


def close():
    """Close icon"""
    return icon('window-close.svg')


def cola():
    """Git Cola icon"""
    return icon('git-cola.svg')


def commit():
    """Commit icon"""
    return from_theme('vcs-commit', fallback='document-save-symbolic.svg')


def stash():
    """Stash icon"""
    return from_theme('edit-clear-history-symbolic', fallback='document-save-symbolic.svg') # vcs-stash, folder-stash


def compare():
    """Compare icon"""
    return from_theme('kr_comparedirs', fallback='git-compare.svg')


def configure():
    """Configure icon"""
    return from_theme('configure-symbolic', fallback='gear.svg')


def cut():
    """Cut icon"""
    return from_theme('edit-cut', fallback='edit-cut.svg')


def copy():
    """Copy icon"""
    return from_theme('edit-copy', fallback='edit-copy.svg')


def paste():
    """Paste icon"""
    return from_theme('edit-paste', fallback='edit-paste.svg')


def play():
    """Play icon"""
    return from_theme('media-playback-start', fallback='play.svg')


def delete():
    """Delete icon"""
    return from_theme('edit-delete', fallback='trashcan.svg')


def delete_branch():
    """Delete icon for branches"""
    return from_theme('vcs-branch-delete', fallback='trashcan.svg')


def default_app():
    """Default app icon"""
    return from_theme('system-run', fallback='telescope.svg')


def dot_name():
    """Dot icon name"""
    return name_from_basename('primitive-dot.svg')


def download():
    """Download icon"""
    return from_theme('download-symbolic', fallback='file-download.svg')


def discard():
    """Discard icon"""
    return from_theme('delete', fallback='trashcan.svg')


# folder vs directory: directory is opaque, folder is just an outline
# directory is used for the File Browser, where more contrast with the file
# icons are needed.


def folder():
    """Folder icon"""
    return from_theme('folder', fallback='folder.svg')


def directory():
    """Directory icon"""
    return from_theme('folder', fallback='file-directory.svg')


def diff():
    """Diff icon"""
    return from_theme('vcs-diff', fallback='diff.svg')


def edit():
    """Edit icon"""
    return from_theme('document-edit', fallback='pencil.svg')


def ellipsis():
    """Ellipsis icon"""
    return from_theme('view-filter', fallback='ellipsis.svg')


def external():
    """External link icon"""
    return from_theme('link', fallback='link-external.svg')


def file_code():
    """Code file icon"""
    return from_theme('text-xml', fallback='file-code.svg')


def file_text():
    """Text file icon"""
    return from_theme('text-plain', fallback='file-text.svg')


def file_zip():
    """Zip file / tarball icon"""
    return from_theme('application-x-zip', fallback='file-zip.svg')


def fold():
    """Fold icon"""
    return from_theme('collapse', fallback='fold.svg')


def merge():
    """Merge icon"""
    return from_theme('vcs-merge-request', fallback='git-merge.svg')


def modified():
    """Modified icon"""
    return from_theme('modified-symbolic', fallback='modified.svg')


def modified_name():
    """Modified icon name"""
    return name_from_basename('modified.svg')


def move_down():
    """Move down icon"""
    return from_theme('go-next', fallback='arrow-down.svg')


def move_up():
    """Move up icon"""
    return from_theme('go-previous', fallback='arrow-up.svg')


def new():
    """Add new/add-to-list icon"""
    return from_theme('list-add', fallback='folder-new.svg')


def ok():
    """Ok/accept icon"""
    return from_theme('checkmark', fallback='check.svg')


def open_directory():
    """Open directory icon"""
    return from_theme('folder', fallback='folder.svg')


def up():
    """Previous icon"""
    return from_theme('arrow-up', fallback='arrow-up.svg')


def down():
    """Go to next item icon"""
    return from_theme('arrow-down', fallback='arrow-down.svg')


def partial_name():
    """Partial icon name"""
    return name_from_basename('partial.svg')


def pull():
    """Pull icon"""
    return from_theme('vcs-update-cvs-cervisia', fallback='repo-pull.svg') # vcs-pull, vcs-update-cvs-cervisia, download-later-symbolic


def push():
    """Push icon"""
    return from_theme('vcs-commit-cvs-cervisia', fallback='repo-push.svg') # vcs-push, vcs-commit-cvs-cervisia, upload-later-symbolic


def fetch():
    """Push icon"""
    return from_theme('view-refresh-symbolic', fallback='repo-push.svg') # cloud-download


def question():
    """Question icon"""
    return from_theme('question', fallback='question.svg')


def remove():
    """Remove icon"""
    return from_theme('list-remove', fallback='circle-slash.svg')


def repo():
    """Repository icon"""
    return from_theme('folder-symbolic', fallback='repo.svg')


def reverse_chronological():
    """Reverse chronological icon"""
    return from_theme('view-sort-descending', fallback='last-first-order.svg')


def save():
    """Save icon"""
    return from_theme('document-save', fallback='desktop-download.svg')


def search():
    """Search icon"""
    return from_theme('search', fallback='search.svg')


def select_all():
    """Select all icon"""
    return from_theme('edit-select-all', fallback='edit-select-all')


def staged():
    """Staged icon"""
    return icon('staged.svg')


def staged_name():
    """Staged icon name"""
    return name_from_basename('staged.svg')


def star():
    """Star icon"""
    return icon('star.svg')


def sync():
    """Sync/update icon"""
    return from_theme('view-refresh-symbolic', fallback='sync.svg')


def tag():
    """Tag icon"""
    return from_theme('tag', fallback='tag.svg')


def terminal():
    """Terminal icon"""
    return from_theme('utilities-terminal-symbolic', fallback='terminal.svg')


def undo():
    """Undo icon"""
    return from_theme('edit-undo', fallback='edit-undo.svg')


def redo():
    """Redo icon"""
    return from_theme('edit-redo', fallback='edit-redo.svg')


def style_dialog_apply():
    """Apply icon from the current style"""
    return from_style(QtWidgets.QStyle.SP_DialogApplyButton)


def style_dialog_discard():
    """Discard icon for the current style"""
    return from_style(QtWidgets.QStyle.SP_DialogDiscardButton)


def style_dialog_reset():
    """Reset icon for the current style"""
    return from_style(QtWidgets.QStyle.SP_DialogResetButton)


def unfold():
    """Expand/unfold icon"""
    return from_theme('expand', fallback='unfold.svg')


def visualize():
    """An eye icon to represent visualization"""
    return icon('eye.svg')


def upstream_name():
    """Upstream branch icon name"""
    return name_from_basename('upstream.svg')


def zoom_fit_best():
    """Zoom-to-fit icon"""
    return from_theme('zoom-fit-best', fallback='zoom-fit-best.svg')


def zoom_in():
    """Zoom-in icon"""
    return from_theme('zoom-in', fallback='zoom-in.svg')


def zoom_out():
    """Zoom-out icon"""
    return from_theme('zoom-out', fallback='zoom-out.svg')
