import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from fixtures import make_pdf,config
ROOT=Path(__file__).resolve().parents[1]

class CLI(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.dir=Path(self.tmp.name)
        self.pdf=self.dir/'input with spaces.pdf';make_pdf(self.pdf)
        self.cfg=self.dir/'settings.json';self.cfg.write_text(json.dumps(config()))
        self.env=dict(os.environ,CMS_EDI_SETTINGS=str(self.cfg))
    def tearDown(self):self.tmp.cleanup()
    def run_cli(self,*args):return subprocess.run([sys.executable,str(ROOT/'cli.py'),*map(str,args)],env=self.env,text=True,capture_output=True)
    def test_single_command_exact_output_and_zeroes(self):
        out=self.dir/'nested folder'/'exact-name.edi'
        r=self.run_cli(self.pdf,out);self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(r.stdout.strip(),str(out.resolve()))
        self.assertIn('REF*F8*000TESTCLAIM123~',out.read_text())
        self.assertFalse(out.with_suffix('.review.txt').exists())
        self.assertFalse(out.with_suffix('.claim.json').exists())
    def test_existing_output_unchanged(self):
        out=self.dir/'claim.edi';out.write_text('keep this')
        r=self.run_cli(self.pdf,out)
        self.assertNotEqual(r.returncode,0);self.assertEqual(out.read_text(),'keep this')
        self.assertFalse(out.with_suffix('.review.txt').exists())
    def test_sidecars_optional(self):
        out=self.dir/'claim.edi'
        r=self.run_cli(self.pdf,out,'--sidecars');self.assertEqual(r.returncode,0,r.stderr)
        record=json.loads(out.with_suffix('.claim.json').read_text())
        self.assertEqual(record['mode'],'T');self.assertEqual(record['source_box26'],'000TESTACCOUNT')
        self.assertTrue(out.with_suffix('.review.txt').exists())
    def test_force_overwrite(self):
        out=self.dir/'claim.edi';out.write_text('old')
        r=self.run_cli(self.pdf,out,'--force')
        self.assertEqual(r.returncode,0,r.stderr);self.assertTrue(out.read_text().startswith('ISA*'))
        self.assertFalse(out.with_suffix('.claim.json').exists())
    def test_verbose_prints_review(self):
        out=self.dir/'claim.edi'
        r=self.run_cli(self.pdf,out,'--verbose');self.assertEqual(r.returncode,0,r.stderr)
        self.assertIn('Payer:',r.stdout);self.assertTrue(r.stdout.strip().endswith(str(out.resolve())))
    def test_invalid_missing_file_creates_nothing(self):
        out=self.dir/'claim.edi';r=self.run_cli(self.dir/'missing.pdf',out)
        self.assertNotEqual(r.returncode,0);self.assertFalse(out.exists())
    def test_settings_shared_path_and_strings(self):
        r=self.run_cli('settings','path');self.assertEqual(r.stdout.strip(),str(self.cfg))
        r=self.run_cli('settings','set','/payers/SYNTHETIC TEST PAYER/id','00590')
        self.assertEqual(r.returncode,0,r.stderr)
        cfg=json.loads(self.cfg.read_text());self.assertEqual(cfg['payers']['SYNTHETIC TEST PAYER']['id'],'00590')
        self.assertFalse(cfg['payers']['SYNTHETIC TEST PAYER']['confirmed'])
        r=self.run_cli('settings','set','/payers/SYNTHETIC TEST PAYER/confirmed','true','--json')
        self.assertEqual(r.returncode,0,r.stderr);self.assertIs(json.loads(self.cfg.read_text())['payers']['SYNTHETIC TEST PAYER']['confirmed'],True)
    def test_settings_payer_and_provider(self):
        self.assertEqual(self.run_cli('settings','payer','PAYER EXAMPLE','00001','--filing','BL','--verified').returncode,0)
        self.assertEqual(self.run_cli('settings','provider','1999999984','--first','TEST','--last','NEW').returncode,0)
        cfg=json.loads(self.cfg.read_text());self.assertTrue(cfg['payers']['PAYER EXAMPLE']['confirmed'])
        self.assertEqual(cfg['rendering_providers']['1999999984']['last'],'NEW')
    def test_edit_fields_and_convert(self):
        edited=self.dir/'edited.pdf'
        r=self.run_cli('edit',self.pdf,edited,'--set','24dcpt-1=90837','--set','24fdol-1=150','--set','dol28=150','--set','22ref=000CHANGED')
        self.assertEqual(r.returncode,0,r.stderr)
        r=self.run_cli(edited,self.dir/'edited.edi');self.assertEqual(r.returncode,0,r.stderr)
        edi=(self.dir/'edited.edi').read_text();self.assertIn('HC:90837:95*150.00',edi);self.assertIn('REF*F8*000CHANGED~',edi)
        r=self.run_cli('fields',self.pdf,'--json');self.assertEqual(json.loads(r.stdout)['24dcpt-1']['value'],'90834')
    def test_edit_boolean_and_json_updates(self):
        updates=self.dir/'updates.json';updates.write_text(json.dumps({'code22':'1','22ref':'','yes27':False,'no27':True}))
        # Test fixture does not contain no27; an unknown field must not be silently added.
        r=self.run_cli('edit',self.pdf,self.dir/'edited.pdf','--fields-json',updates)
        self.assertNotEqual(r.returncode,0);self.assertFalse((self.dir/'edited.pdf').exists())
    def test_bad_field_no_output(self):
        r=self.run_cli('edit',self.pdf,self.dir/'edited.pdf','--set','TYPO=hello')
        self.assertNotEqual(r.returncode,0);self.assertFalse((self.dir/'edited.pdf').exists())
    def test_review_no_output(self):
        r=self.run_cli('review',self.pdf,'--json');self.assertEqual(r.returncode,0,r.stderr)
        self.assertEqual(json.loads(r.stdout)['frequency'],'7');self.assertFalse(list(self.dir.glob('*.edi')))
    def test_production_demo_block(self):
        r=self.run_cli(self.pdf,self.dir/'claim.edi','--production');self.assertNotEqual(r.returncode,0)
        self.assertFalse((self.dir/'claim.edi').exists())
    def test_settings_unset(self):
        r=self.run_cli('settings','unset','/billing_taxonomy');self.assertEqual(r.returncode,0,r.stderr)
        self.assertNotIn('billing_taxonomy',json.loads(self.cfg.read_text()))

if __name__=='__main__':unittest.main()
