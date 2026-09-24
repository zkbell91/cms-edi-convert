"""cms-edi-convert INPUT.pdf OUTPUT.edi — local files only, test mode by default."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
from datetime import datetime
from converter import (VERSION, ConversionError, require, read_pdf, claim_from_fields, load_config,
                       review_text, build_edi, refresh_appearances, stored_pdf_fields)
from shared_settings import ensure,save as save_settings

COMMANDS={'convert','review','fields','edit','refresh','settings'}

def parser():
    p=argparse.ArgumentParser(prog='cms-edi-convert',description=__doc__,epilog='You can omit "convert": cms-edi-convert input.pdf output.edi')
    p.add_argument('--version',action='version',version='cms-edi-convert '+VERSION)
    sub=p.add_subparsers(dest='command',required=True)
    def common(q):q.add_argument('--config',type=Path,help='Override the shared settings file for this command')
    q=sub.add_parser('convert',help='Create exactly the output EDI filename you supply');common(q)
    q.add_argument('input',type=Path);q.add_argument('output',type=Path)
    q.add_argument('--production',action='store_true',help='Write ISA15=P; default is T. Does NOT submit the file.')
    q.add_argument('--force',action='store_true',help='Explicitly replace existing output files')
    q.add_argument('--quiet',action='store_true',help='Print output path only, instead of the claim review')
    q.add_argument('--no-sidecars',action='store_true',help='Do not write .review.txt and .claim.json files')
    q=sub.add_parser('review',help='Validate and show the claim without generating EDI');common(q)
    q.add_argument('input',type=Path);q.add_argument('--json',action='store_true')
    q=sub.add_parser('fields',help='List every stored PDF field (does not expose old appearance-only values)')
    q.add_argument('input',type=Path);q.add_argument('--json',action='store_true');q.add_argument('--all',action='store_true',help='Include empty fields')
    q=sub.add_parser('edit',help='Edit any PDF form field and save a separate fillable copy')
    q.add_argument('input',type=Path);q.add_argument('output',type=Path)
    q.add_argument('--set',action='append',default=[],metavar='FIELD=VALUE',help='Repeat for multiple fields; empty VALUE clears a field; checkboxes accept true/false')
    q.add_argument('--fields-json',type=Path,help='JSON object of field names and values')
    q=sub.add_parser('refresh',help='Regenerate displayed appearances from stored form values into a separate PDF')
    q.add_argument('input',type=Path);q.add_argument('output',type=Path)
    q=sub.add_parser('settings',help='Manage the same settings used by the desktop app');common(q)
    ss=q.add_subparsers(dest='action',required=True)
    ss.add_parser('path',help='Print the shared settings path')
    ss.add_parser('show',help='Print all settings as JSON')
    ss.add_parser('edit',help='Open the settings file in $EDITOR and check JSON afterward')
    a=ss.add_parser('set',help='Set any setting by JSON Pointer (/submitter/name) or simple dotted path')
    a.add_argument('key');a.add_argument('value');a.add_argument('--json',action='store_true',help='Parse value as JSON; otherwise preserve it as text, including leading zeros')
    a=ss.add_parser('unset',help='Delete a setting');a.add_argument('key')
    a=ss.add_parser('payer',help='Add/update a payer mapping')
    a.add_argument('name');a.add_argument('id');a.add_argument('--filing',choices=['CI','BL','HM','OF'],required=True)
    a.add_argument('--verified',action='store_true',help='Record that you verified the payer ID in Stedi’s directory')
    a=ss.add_parser('provider',help='Add/update a rendering provider')
    a.add_argument('npi');a.add_argument('--first',required=True);a.add_argument('--last',required=True)
    a.add_argument('--middle',default='');a.add_argument('--taxonomy',default='')
    return p

def keys(path):
    if path.startswith('/'):
        result=[x.replace('~1','/').replace('~0','~') for x in path[1:].split('/')]
    else:result=path.split('.')
    require(all(result),'Setting path cannot have empty components.')
    return result

def update_setting(cfg,path,value=None,delete=False):
    parts=keys(path);node=cfg
    for part in parts[:-1]:
        if delete:require(part in node, 'Setting does not exist.')
        node=node.setdefault(part,{})
        require(isinstance(node,dict),'Parent setting is not an object.')
    if delete:
        require(parts[-1] in node,'Setting does not exist.');del node[parts[-1]]
    else:node[parts[-1]]=value
    if len(parts)==3 and parts[0]=='payers' and parts[2]=='id':node['confirmed']=False

def settings_command(a):
    path=ensure(a.config)
    if a.action=='path':print(path);return
    cfg=load_config(path)
    if a.action=='show':print(json.dumps(cfg,indent=2));return
    if a.action=='edit':
        editor=os.environ.get('EDITOR') or ('notepad' if os.name=='nt' else 'vi')
        backup=path.read_bytes()
        result=subprocess.run(shlex.split(editor)+[str(path)])
        try:
            require(result.returncode==0, 'Editor exited unsuccessfully.')
            load_config(path)
        except Exception:
            path.write_bytes(backup)
            raise ConversionError('Settings edit was invalid; previous settings restored.')
        print('Saved:',path);return
    if a.action=='set':update_setting(cfg,a.key,json.loads(a.value) if a.json else a.value)
    elif a.action=='unset':update_setting(cfg,a.key,delete=True)
    elif a.action=='payer':
        cfg.setdefault('payers',{})[a.name]={'id':a.id,'filing_indicator':a.filing,'confirmed':a.verified}
    elif a.action=='provider':
        cfg.setdefault('rendering_providers',{})[a.npi]={'first':a.first,'last':a.last,'middle':a.middle,'taxonomy':a.taxonomy}
    save_settings(path,cfg);print('Saved:',path)

def write_outputs(files,force=False):
    """Validate all destinations before staging. Refuse overwrite unless explicitly requested."""
    staged=[];published=[]
    try:
        for path,data in files:
            require(not path.exists() or force,f'Output exists: {path}. Use another filename or --force.')
            require(not path.is_symlink(),f'Refusing a symlink output: {path}')
            require(not path.exists() or path.is_file(),f'Not a regular file: {path}')
            path.parent.mkdir(parents=True,exist_ok=True)
            fd,temp=tempfile.mkstemp(prefix='.'+path.name+'-',suffix='.tmp',dir=path.parent)
            with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
            staged.append((path,Path(temp)))
        # Sidecars first, EDI last. With no --force, hard links publish without an overwrite race.
        for path,temp in reversed(staged):
            if force:os.replace(temp,path)
            else:os.link(temp,path);temp.unlink()
            published.append(path)
    except Exception:
        # Never remove a pre-existing file. Newly published files may safely be rolled back.
        if not force:
            for path in published:path.unlink(missing_ok=True)
        raise
    finally:
        for _,temp in staged:temp.unlink(missing_ok=True)

def main(argv=None):
    argv=list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] not in COMMANDS and not argv[0].startswith('-'):argv.insert(0,'convert')
    a=parser().parse_args(argv)
    try:
        if a.command=='settings':settings_command(a);return 0
        a.input=a.input.expanduser()
        require(a.input.is_file(),f'Input PDF does not exist: {a.input}')
        if a.command=='fields':
            f=stored_pdf_fields(a.input)
            selected={k:v for k,v in f.items() if a.all or v['value'] not in ('','/Off','Off')}
            if a.json:print(json.dumps(selected,indent=2))
            else:
                print('STORED VALUES (appearance consistency is checked during conversion)')
                for k,v in selected.items():print(f"{k}\t{v['type']}\t{v['value']}")
            return 0
        if a.command in ('edit','refresh'):
            a.output=a.output.expanduser();a.output.parent.mkdir(parents=True,exist_ok=True)
            changes={}
            if a.command=='edit':
                if a.fields_json:
                    changes=json.loads(a.fields_json.expanduser().read_text())
                    require(isinstance(changes,dict),'Field edits must be a JSON object.')
                for item in a.set:
                    require('=' in item,'Use --set FIELD=VALUE.');k,v=item.split('=',1);changes[k]=v
                require(changes,'Provide --set FIELD=VALUE or --fields-json edits.json.')
            refresh_appearances(a.input,a.output,updates=changes)
            print(a.output.resolve());print('Separate fillable copy saved. Inspect it before converting. Original unchanged.',file=sys.stderr)
            return 0
        cfg_path=ensure(a.config)
        # One immutable in-memory snapshot for extraction + output record.
        pdf_bytes=a.input.read_bytes();cfg_bytes=cfg_path.read_bytes()
        import io
        fields=read_pdf(io.BytesIO(pdf_bytes))
        cfg=json.loads(cfg_bytes)
        require(isinstance(cfg,dict),'Settings must be a JSON object.')
        claim=claim_from_fields(fields,cfg)
        if a.command=='review':
            print(json.dumps(claim,indent=2) if a.json else review_text(claim));return 0
        a.output=a.output.expanduser()
        require(a.output.suffix.lower()=='.edi','Output filename must end in .edi.')
        require(a.input.resolve()!=a.output.resolve(),'Input and output must be different files.')
        mode='P' if a.production else 'T';edi,control=build_edi(claim,mode)
        record={'version':VERSION,'created_at':datetime.now().isoformat(),'mode':mode,
                'source_pdf':a.input.name,'source_sha256':hashlib.sha256(pdf_bytes).hexdigest(),
                'settings_sha256':hashlib.sha256(cfg_bytes).hexdigest(),
                'source_box26':claim['source_control'],'outgoing_claim_id':control,
                'payer_claim_number':claim['original_payer_claim_number'],'frequency':claim['frequency'],'claim':claim}
        review=review_text(claim)+'\n\nOutgoing claim ID: '+control+'\nMode: '+mode+'\n'
        files=[(a.output,edi.encode('ascii'))]
        if not a.no_sidecars:
            files += [(a.output.with_suffix('.review.txt'),review.encode('utf-8')),
                      (a.output.with_suffix('.claim.json'),(json.dumps(record,indent=2)+'\n').encode('utf-8'))]
        require(all(path.resolve() not in (a.input.resolve(),cfg_path.resolve()) for path,_ in files), 'An output would overwrite the input PDF or settings; choose another destination.')
        write_outputs(files,a.force)
        if not a.quiet:print(review+'\nSaved locally; nothing was submitted.\n')
        print(a.output.resolve());return 0
    except (ConversionError,ValueError,OSError,TypeError,KeyError) as exc:
        print('Error: '+str(exc),file=sys.stderr);return 1

if __name__=='__main__':sys.exit(main())
