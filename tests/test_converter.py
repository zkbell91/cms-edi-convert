import copy
from datetime import datetime
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from converter import *
from fixtures import fields,config,make_pdf

class Claims(unittest.TestCase):
    def setUp(self): self.f=fields();self.cfg=config()
    def claim(self): return claim_from_fields(self.f,self.cfg)
    def fails(self,pattern):
        with self.assertRaisesRegex(ConversionError,pattern): self.claim()
    def test_replacement_edi_and_envelopes(self):
        edi,pc=build_edi(self.claim(),control='SYNTHETIC000001',now=datetime(2026,9,24,12,0))
        s=edi.splitlines();self.assertEqual(len(s[0]),106)
        self.assertEqual(s[0].split('*')[15],'T')
        self.assertIn('REF*F8*000TESTCLAIM123~',s)
        self.assertIn('SV1*HC:90834:95*100.00*UN*1***1~',s)
        self.assertIn('NM1*IL*1*EXAMPLE*AVERY****MI*000123ABC~',s)
        self.assertIn('N4*BOSTON*MA*02108~',s)
        self.assertIn('CLM*SYNTHETIC000001*100.00***10:B:7*Y*A*Y*Y~',s)
        st=next(i for i,v in enumerate(s) if v.startswith('ST*'))
        se=next(i for i,v in enumerate(s) if v.startswith('SE*'))
        self.assertEqual(int(s[se].split('*')[1]),se-st+1)
        self.assertEqual(s[st].split('*')[2],s[se].split('*')[2].rstrip('~'))
        self.assertEqual(s[0].split('*')[13],s[-1].split('*')[2].rstrip('~'))
    def test_identifier_case_preserved(self):
        self.f['22ref']='000AbcXyz';self.f['1a']='000aBc'
        edi,_=build_edi(self.claim())
        self.assertIn('REF*F8*000AbcXyz~',edi);self.assertIn('MI*000aBc~',edi)
    def test_u_diagnosis_accepted(self):
        self.f['diag21.1']='U07.1'
        self.assertIn('HI*ABK:U071~',build_edi(self.claim())[0])
    def test_missing_original_number(self): self.f['22ref']='';self.fails('payer claim number')
    def test_total_mismatch(self): self.f['dol28']='150';self.fails('sum of line charges')
    def test_preserves_payer_zeros(self):
        self.cfg['payers']['SYNTHETIC TEST PAYER']['id']='00590'
        self.assertIn('PI*00590~',build_edi(self.claim())[0])
    def test_dob_century(self):
        self.f['3yy']='80'
        self.assertEqual(claim_from_fields(self.f, config())['patient']['dob'], '19800412')
        self.f['3yy']='61'
        self.assertEqual(claim_from_fields(self.f, config())['patient']['dob'], '19610412')
    def test_dob_two_digit_matches_insured(self):
        self.f['3yy']='61';self.f['mm11a']='04';self.f['dd11a']='12';self.f['yy11a']='61'
        claim_from_fields(self.f, config())

    def test_invalid_calendar_date(self): self.f['3dd']='31';self.f['3mm']='02';self.fails('calendar')
    def test_invalid_npi(self): self.f['grp33a.1']='1999999985';self.fails('check digit')
    def test_unmapped_payer(self): self.f['cname']='NEW PAYER';self.fails('No built-in payer ID')
    def test_unconfirmed_payer(self): self.cfg['payers']['SYNTHETIC TEST PAYER']['confirmed']=False;self.fails('Confirm')
    def test_builtin_cigna(self):
        self.f['cname']='CIGNA';del self.cfg['payers']
        claim=claim_from_fields(self.f, self.cfg)
        self.assertEqual(claim['payer']['id'],'62308')
        self.assertEqual(claim['payer']['filing_indicator'],'CI')
    def test_settings_override_builtin(self):
        self.f['cname']='CIGNA'
        self.cfg['payers']={'CIGNA':{'id':'99999','filing_indicator':'CI','confirmed':True}}
        self.assertEqual(claim_from_fields(self.f, self.cfg)['payer']['id'],'99999')
    def test_demo_cannot_produce_live(self):
        with self.assertRaisesRegex(ConversionError,'only generate test'): build_edi(self.claim(),'P')
    def test_explicit_production(self):
        self.cfg['payers']['SYNTHETIC TEST PAYER']['test_only']=False
        self.assertEqual(build_edi(self.claim(),'P')[0].splitlines()[0].split('*')[15],'P')
    def test_unknown_field_not_silently_dropped(self): self.f['new_clinical_field']='IMPORTANT';self.fails('Unrecognized populated')
    def test_unsupported_field(self): self.f['name17']='REFER, TEST';self.fails('Unsupported populated')
    def test_cob_block(self): self.f['yes11d']='/Yes';self.fails('other-insurance')
    def test_medicare_block(self): self.f['otheridd1']='';self.f['medicare1']='/Yes';self.fails('commercial')
    def test_multiple_relationships(self): self.f['child6']='/Yes';self.fails('exactly one')
    def test_self_mismatched_name(self): self.f['four']='EXAMPLE, SOMEONE';self.fails('names differ')
    def test_reserved_separator(self): self.f['22ref']='ONE|TWO';self.fails('EDI separators')
    def test_prior_auth_keeps_asterisk(self):
        self.f['code22']='';self.f['22ref']='';self.f['prior23']='262094137*O'
        edi,_=build_edi(self.claim())
        self.assertIn('REF|G1|262094137*O~',edi)
        self.assertTrue(edi.startswith('ISA|'))
        self.assertNotIn('REF*G1*',edi)
    def test_procedure_blank_with_line_data(self): self.f['24dcpt-1']='';self.fails('procedure')
    def test_missing_diag_pointer(self): self.f['24e-1']='B';self.fails('missing diagnosis')
    def test_multiple_lines_and_dates(self):
        for k,v in list(self.f.items()):
            if k.startswith('24') and k.endswith('-1'): self.f[k[:-1]+'2']=v
        self.f['24atodd-2']='31';self.f['dol28']='200'
        edi,_=build_edi(self.claim())
        self.assertEqual(edi.count('LX*'),2)
        self.assertIn('DTP*472*RD8*20260730-20260731~',edi)
    def test_dependent(self):
        self.f.update({'self6':'','child6':'/Yes','four':'EXAMPLE, PARENT','mm11a':'01','dd11a':'02','yy11a':'1955',
            'female11a':'/Yes','add7':'123 TEST STREET','city7':'BOSTON','state7':'MA','zip7':'02108'})
        edi,_=build_edi(self.claim())
        self.assertIn('HL*2*1*22*1~',edi);self.assertIn('HL*3*2*23*0~',edi)
        self.assertIn('PAT*19~',edi);self.assertIn('NM1*QC*1*EXAMPLE*AVERY~',edi)
        self.assertIn('NM1*IL*1*EXAMPLE*PARENT****MI*000123ABC~',edi)
    def test_authorization_and_patient_paid(self):
        self.f['prior23']='000AUTH';self.f['dol29']='30'
        edi,_=build_edi(self.claim())
        self.assertIn('REF*G1*000AUTH~',edi);self.assertIn('AMT*F5*30.00~',edi)
    def test_original_with_reference_block(self): self.f['code22']='1';self.fails('Original claim')
    def test_original_and_void(self):
        self.f['code22']='';self.f['22ref']=''
        edi,_=build_edi(self.claim());self.assertIn('10:B:1',edi);self.assertNotIn('REF*F8',edi)
        self.f['code22']='8';self.f['22ref']='000VOID'
        self.assertIn('10:B:8',build_edi(self.claim())[0])
    def test_birth_after_service(self): self.f['3yy']='2026';self.f['3mm']='08';self.fails('precedes birth')
    def test_source_id_not_used_as_payer_id(self): self.f['22ref']=self.f['pat26'];self.fails('equals Box 26')
    def test_unknown_provider(self): self.cfg['rendering_providers']={};self.fails('rendering provider')

class PDFs(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'test.pdf';make_pdf(self.path)
    def tearDown(self): self.temp.cleanup()
    def mutate(self,fn):
        from pypdf import PdfWriter
        w=PdfWriter();w.clone_document_from_reader(PdfReader(self.path));fn(w)
        with self.path.open('wb') as f: w.write(f)
    def test_synthetic_pdf_extraction(self): self.assertEqual(read_pdf(self.path)['22ref'],'000TESTCLAIM123')
    def test_stale_appearance_rejected(self):
        from pypdf.generic import TextStringObject
        def change(w):
            for r in w.pages[0]['/Annots']:
                if r.get_object().get('/T')=='two': r.get_object()[NameObject('/V')]=TextStringObject('')
        self.mutate(change)
        with self.assertRaisesRegex(ConversionError,'stored value and displayed'): read_pdf(self.path)
    def test_refresh_preserves_new_value_and_original(self):
        from pypdf.generic import TextStringObject
        def change(w):
            for ref in w.pages[0]['/Annots']:
                if ref.get_object().get('/T')=='24dcpt-1':ref.get_object()[NameObject('/V')]=TextStringObject('90837')
        self.mutate(change)
        original=self.path.read_bytes();out=Path(self.temp.name)/'refreshed.pdf'
        refresh_appearances(self.path,out)
        self.assertEqual(read_pdf(out)['24dcpt-1'],'90837')
        self.assertEqual(self.path.read_bytes(),original)
        with self.assertRaisesRegex(ConversionError,'new output filename'):refresh_appearances(self.path,out)
    def test_overlay_rejected(self):
        from pypdf.annotations import FreeText
        self.mutate(lambda w:w.add_annotation(0,FreeText(text='90834',rect=(20,20,100,40))))
        with self.assertRaisesRegex(ConversionError,'markup'): read_pdf(self.path)
    def test_export_snapshot_and_outputs(self):
        p=Path(self.temp.name)/'config.json';p.write_text(json.dumps(config()))
        out=export_bundle(self.path,p,self.temp.name)
        self.assertTrue((out/'claim-T.edi').exists());self.assertTrue((out/'claim-record.json').exists())
        record=json.loads((out/'claim-record.json').read_text())
        self.assertEqual(record['source_box26'],'000TESTACCOUNT');self.assertEqual(record['payer_claim_number'],'000TESTCLAIM123')
        with self.assertRaisesRegex(ConversionError,'PDF changed'): export_bundle(self.path,p,self.temp.name,expected_pdf_hash='bad')
    def test_page_content_overlay_rejected(self):
        from pypdf.generic import DecodedStreamObject
        def change(w):
            old=w.pages[0].get_contents().get_data()
            stream=DecodedStreamObject();stream.set_data(old+b'\nq 1 1 1 rg 0 0 800 900 re f Q\n')
            w.pages[0][NameObject('/Contents')]=w._add_object(stream)
        self.mutate(change)
        with self.assertRaisesRegex(ConversionError,'artwork has changed'): read_pdf(self.path)
    def test_blank_pdf_rejected(self):
        from pypdf import PdfWriter
        w=PdfWriter();w.add_blank_page(width=612,height=792);w.write(self.path)
        with self.assertRaisesRegex(ConversionError,'not the supported'): read_pdf(self.path)
    def test_checkbox_stale(self):
        from pypdf.generic import TextStringObject
        def change(w):
            for r in w.pages[0]['/Annots']:
                if r.get_object().get('/T')=='self6': r.get_object()[NameObject('/V')]=NameObject('/Off')
        self.mutate(change)
        with self.assertRaisesRegex(ConversionError,'checkbox'): read_pdf(self.path)

if __name__=='__main__': unittest.main()
