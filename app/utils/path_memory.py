"""Purpose-specific user content paths. Never use process cwd as a default."""
import logging
from pathlib import Path
import sys
from app.utils.app_settings import AppSettings

log=logging.getLogger('aivsprite.paths')
WORK_ROOT=Path('E:/AI Video to Sprite/work')
WORK_CANDIDATES=tuple(Path(f'{drive}:/AI Video to Sprite/work') for drive in ('E','D','C'))
PATH_KEYS=frozenset(('project_create','project_open','project_save','video_import','image_import',
    'image_sequence_import','folder_import','png_export','sprite_sheet_export','frame_export',
    'project_export','sprite_sheet_import','group_export','generic_open','generic_save','generic_folder'))


def valid_directory(value,ancestors=False):
    if not value:return None
    try:
        path=Path(value).expanduser()
        if not path.is_absolute():return None
        while True:
            if path.is_dir():return path
            if not ancestors or path.parent==path:return None
            path=path.parent
    except (OSError,ValueError,TypeError):return None


class PathMemoryService:
    def __init__(self,settings=None,work_candidates=None,home=None,application_dirs=None):
        self.settings=AppSettings(settings)
        self.work_candidates=tuple(work_candidates) if work_candidates is not None else WORK_CANDIDATES
        self.home=Path(home) if home is not None else Path.home()
        # Exclusion only, never a default content location.
        self.application_dirs={Path(p) for p in (application_dirs or ())}
        self.application_dirs.add(Path(__file__).resolve().parents[2])
        if getattr(sys,'frozen',False):self.application_dirs.add(Path(sys.executable).parent)
        self._work=None;self.last_error=None

    @property
    def state(self):
        state=self.settings.read().get('path_state',{})
        return state if isinstance(state,dict) else {}

    @property
    def work_root(self):
        if self._work and valid_directory(self._work):return self._work
        for candidate in self.work_candidates:
            candidate=Path(candidate)
            try:
                # A missing drive must not be fabricated as a relative directory.
                if not candidate.is_absolute() or not Path(candidate.anchor).is_dir():continue
                candidate.mkdir(parents=True,exist_ok=True)
                if candidate.is_dir():self._work=candidate;return candidate
            except OSError:log.warning('Work directory unavailable: %s',candidate,exc_info=True)
        self._work=self.home
        return self.home

    def _content_directory(self,value,ancestors=True):
        path=valid_directory(value,ancestors)
        if path is None:return None
        if path in self.application_dirs or any(part.casefold() in ('dist','_internal') for part in path.parts):return None
        return path

    def initial(self,purpose='generic_open',project_directory=None):
        if purpose not in PATH_KEYS:raise ValueError('Unknown path memory purpose')
        state=self.state;recent=state.get('recent_paths',{})
        recent=recent if isinstance(recent,dict) else {}
        if purpose=='project_create':
            return valid_directory(recent.get(purpose),False) or self.work_root
        for value in (recent.get(purpose),state.get('last_location')):
            directory=valid_directory(value,True)
            if directory:return directory
        directory=self._content_directory(project_directory)
        if directory:return directory
        return self.work_root

    def remember(self,purpose,path,*,file=False):
        if purpose not in PATH_KEYS:raise ValueError('Unknown path memory purpose')
        self.last_error=None
        try:
            value=Path(path)
            if file:
                if not value.is_file():return False
                value=value.parent
            directory=valid_directory(value)
            if directory is None:return False
            directory=directory.resolve()
            state=self.state;recent=state.get('recent_paths',{})
            recent=dict(recent) if isinstance(recent,dict) else {}
            recent[purpose]=str(directory)
            self.settings.update({'path_state':dict(version=1,work_root=str(self.work_root),last_location=str(directory),recent_paths=recent)})
            return True
        except (OSError,ValueError) as error:
            self.last_error=str(error);log.warning('Could not save path history',exc_info=True);return False

    def shortcuts(self,project_directory=None):
        result=[('Work',self.work_root)]
        for label,value in (('Current Project',project_directory),('Last Location',self.state.get('last_location'))):
            directory=valid_directory(value)
            if directory is not None:result.append((label,directory))
        result.append(('Home',self.home))
        return result
