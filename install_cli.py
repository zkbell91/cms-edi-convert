"""Install a private copy and a CLI launcher without modifying shell configuration."""
import argparse
import os
from pathlib import Path
import shutil
import sys
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--prefix',type=Path,default=Path.home()/'.local')
p.add_argument('--update',action='store_true',help='Update an existing installation of this program')
a=p.parse_args()
source=Path(__file__).resolve().parent
base=a.prefix.expanduser();target=base/'share'/'cms-edi-convert';bin_dir=base/'bin';launcher=bin_dir/'cms-edi-convert'
marker=target/'.cms-edi-install'
if target.exists() and (not a.update or not marker.exists()):p.error('Installation already exists; use --update only for an existing installation of this converter.')
if launcher.exists() or launcher.is_symlink():
    if not launcher.is_symlink() or launcher.resolve()!=(target/'cms-edi-convert').resolve():p.error('Another command already exists at '+str(launcher))
shutil.copytree(source,target,dirs_exist_ok=a.update,ignore=shutil.ignore_patterns('__pycache__','*.pyc','settings.json','exports','.DS_Store','.git','.gitignore'))
marker.write_text('CMS-1500 to 837P converter installation\n')
(target/'cms-edi-convert').chmod(0o755)
(target/'Run Converter.command').chmod(0o755)
bin_dir.mkdir(parents=True,exist_ok=True)
if not launcher.is_symlink():launcher.symlink_to(target/'cms-edi-convert')
sys.path.insert(0,str(source))
from shared_settings import ensure
settings=ensure()
print('Installed:',launcher)
print('Shared settings:',settings)
print('Desktop launcher:',target/'Run Converter.command')
if str(bin_dir) not in os.environ.get('PATH','').split(os.pathsep):
    print('Add this directory to your PATH:',bin_dir)
