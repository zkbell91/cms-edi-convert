"""One persistent settings file shared by the CLI and desktop app."""
import json
import os
from pathlib import Path
import tempfile

ROOT=Path(__file__).resolve().parent

def default_path():
    override=os.environ.get('CMS_EDI_SETTINGS')
    if override:return Path(override).expanduser()
    if os.name=='nt':
        return Path(os.environ.get('APPDATA',str(Path.home()/'AppData'/'Roaming')))/'CMS-EDI-Converter'/'settings.json'
    return Path.home()/'.config'/'cms-edi-convert'/'settings.json'

def save(path,settings):
    if not isinstance(settings,dict):raise ValueError('Settings must be a JSON object.')
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.settings-',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            json.dump(settings,f,indent=2,ensure_ascii=False);f.write('\n');f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def ensure(path=None):
    path=Path(path).expanduser() if path else default_path()
    if not path.exists():
        legacy=ROOT/'settings.json'
        source=legacy if legacy.exists() else ROOT/'settings.example.json'
        save(path,json.loads(source.read_text(encoding='utf-8')))
    return path
