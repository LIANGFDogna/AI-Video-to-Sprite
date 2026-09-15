"""Shared machine settings. Atomic merge keeps language and path state independent."""
import json
import logging
import os
from pathlib import Path
import tempfile

log=logging.getLogger('aivsprite.settings')


def settings_path():
    return Path(os.environ.get('AIVSPRITE_SETTINGS',str(Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'AI Video to Sprite'/'app_settings.json')))


class AppSettings:
    def __init__(self,path=None):self.path=Path(path) if path is not None else settings_path()

    def read(self):
        try:
            value=json.loads(self.path.read_text(encoding='utf-8-sig'))
            return value if isinstance(value,dict) else {}
        except (OSError,ValueError):return {}

    def update(self,values):
        data=self.read();data.update(values)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        fd,name=tempfile.mkstemp(prefix='.app-settings-',suffix='.tmp',dir=self.path.parent)
        temp=Path(name)
        try:
            with os.fdopen(fd,'w',encoding='utf-8') as stream:
                json.dump(data,stream,ensure_ascii=False,indent=2);stream.flush();os.fsync(stream.fileno())
            temp.replace(self.path)
        finally:temp.unlink(missing_ok=True)
