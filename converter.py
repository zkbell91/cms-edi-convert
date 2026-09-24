"""Local, fail-closed conversion of the supplied TheraNest fillable CMS-1500 layout."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import secrets
import sys
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
sys.path.insert(0, str(Path(__file__).parent / 'vendor'))
from pypdf import PdfReader, PageObject
from pypdf.generic import NameObject

VERSION = '0.2.0'
class ConversionError(ValueError):
    pass

def require(condition, message):
    if not condition:
        raise ConversionError(message)

def clean(value):
    return re.sub(r'\s+', ' ', str(value or '')).strip()

def edi_text(value, label, maximum=80, required=True):
    value = clean(value).upper()
    require(bool(value) or not required, f'{label}: missing.')
    require(len(value) <= maximum, f'{label}: exceeds {maximum} characters.')
    require(all(32 <= ord(c) <= 126 and c not in '*~:^|<>\\' for c in value),
            f'{label}: contains unsupported characters or EDI separators; correct the PDF/configuration.')
    return value

def identifier(value, label, maximum=50, required=True):
    require(isinstance(value, str), f'{label}: must be text to preserve leading zeros.')
    edi_text(value, label, maximum, required)
    return clean(value)  # Preserve identifier case and leading zeros.

def npi(value, label):
    value = clean(value)
    require(bool(re.fullmatch(r'\d{10}', value)), f'{label}: a 10-digit NPI is required.')
    digits = list(map(int, reversed('80840' + value)))
    total = sum((d * 2 // 10 + d * 2 % 10) if i % 2 else d for i, d in enumerate(digits))
    require(total % 10 == 0, f'{label}: NPI check digit is invalid.')
    return value

def widget_name(widget):
    parts, seen = [], set()
    while widget:
        require(id(widget) not in seen, 'Malformed PDF field parent cycle.')
        seen.add(id(widget))
        if widget.get('/T') is not None:
            parts.insert(0, str(widget['/T']))
        parent = widget.get('/Parent')
        widget = parent.get_object() if parent else None
    return '.'.join(parts)

def inherited(widget, key, default=''):
    seen = set()
    while widget:
        require(id(widget) not in seen, 'Malformed PDF field parent cycle.')
        seen.add(id(widget))
        if key in widget:
            return widget[key]
        parent = widget.get('/Parent')
        widget = parent.get_object() if parent else None
    return default

def background_signature(page):
    """Fingerprint fixed artwork, so page-content overlays cannot hide stored field text."""
    digest = hashlib.sha256()
    contents = page.get_contents()
    digest.update(contents.get_data() if contents is not None else b'')
    def visit(resources, depth=0):
        require(depth < 12, 'PDF artwork nesting is too deep.')
        resources = resources.get_object() if hasattr(resources, 'get_object') else resources
        for name, ref in sorted(resources.get('/XObject', {}).items()):
            obj = ref.get_object()
            digest.update(str(name).encode()); digest.update(str(obj.get('/Subtype')).encode())
            if hasattr(obj, 'get_data'): digest.update(obj.get_data())
            if obj.get('/Resources'): visit(obj['/Resources'], depth+1)
    visit(page.get('/Resources', {}))
    return digest.hexdigest()

def read_pdf(path):
    """Never use appearance values as replacements for stale/missing canonical values."""
    if hasattr(path, 'getbuffer'):
        require(path.getbuffer().nbytes <= 20_000_000, 'PDF exceeds the 20 MB limit.')
    else:
        path = Path(path)
        require(path.stat().st_size <= 20_000_000, 'PDF exceeds the 20 MB limit.')
    reader = PdfReader(path)
    require(not reader.is_encrypted, 'Save an unencrypted, fillable copy first.')
    require(len(reader.pages) == 1, 'This version accepts one one-page claim at a time.')
    fields = reader.get_fields() or {}
    required = {'two', '1a', 'code22', '22ref', '24dcpt-1', 'grp33a.1', 'diag21.1'}
    require(required <= fields.keys(), 'This is not the supported fillable TheraNest template. Flattened/scanned PDFs and other field layouts are not supported.')
    values = {name: clean(field.get('/V', '')) for name, field in fields.items() if field.get('/FT')}
    page = reader.pages[0]
    errors, seen = [], set()
    for ref in page.get('/Annots', []):
        widget = ref.get_object()
        if widget.get('/Subtype') != '/Widget':
            errors.append('PDF contains markup/annotations. Edit the actual form fields, remove overlays, and save again.')
            continue
        name = widget_name(widget)
        if name in seen:
            errors.append(f'{name}: duplicate widget; this layout is not supported.')
        seen.add(name)
        value = clean(inherited(widget, '/V'))
        if name not in values or value != values[name]:
            errors.append(f'{name}: field tree and page widget disagree.')
        ap = widget.get('/AP', {}).get('/N')
        ap = ap.get_object() if ap else None
        typ = inherited(widget, '/FT')
        if typ == '/Btn':
            state = clean(widget.get('/AS', '/Off')) or '/Off'
            if (value or '/Off') != state:
                errors.append(f'{name}: stored checkbox and displayed checkbox disagree.')
        elif typ == '/Tx':
            appearance = ''
            if ap is not None and hasattr(ap, 'get_data'):
                temp = PageObject.create_blank_page(width=684, height=864)
                temp[NameObject('/Contents')] = ap
                temp[NameObject('/Resources')] = ap.get('/Resources', page.get('/Resources', {}))
                try:
                    appearance = clean(temp.extract_text())
                except Exception:
                    errors.append(f'{name}: cannot verify the displayed field text.')
                    continue
            if appearance != value:
                errors.append(f'{name}: stored value and displayed text disagree. Re-save in a PDF form editor that updates field appearances.')
    if errors:
        unique = list(dict.fromkeys(errors))
        if any('disagree' in e for e in unique):
            unique.append(
                'Hint: the converter uses stored form values, not the on-screen appearance cache. '
                'List stored values with: cms-edi-convert fields INPUT.pdf --all\n'
                'Rebuild appearances from stored values (original unchanged): '
                'cms-edi-convert refresh INPUT.pdf OUTPUT.pdf\n'
                'If stored patient/insured fields are blank, re-enter them in a fillable PDF editor and save again—'
                'refresh cannot recover text that exists only in the old appearance.'
            )
        require(False, '\n'.join(unique))
    require(set(values) <= seen, 'Some stored fields have no visible page widget.')
    profiles = json.loads((Path(__file__).parent / 'template-profiles.json').read_text())
    require(background_signature(page) in profiles['background_sha256'], 'The fixed PDF artwork has changed or this is another template. Page-content edits/overlays are not supported; edit the original form fields only.')
    return values

def stored_pdf_fields(source):
    source=Path(source)
    require(source.stat().st_size<=20_000_000,'PDF exceeds the 20 MB limit.')
    r=PdfReader(source)
    require(not r.is_encrypted and len(r.pages)==1,'Only a one-page, unencrypted fillable PDF is supported.')
    fields=r.get_fields() or {}
    require({'two','1a','code22','22ref','24dcpt-1','grp33a.1','diag21.1'}<=fields.keys(),'Unsupported PDF form template.')
    return {name:{'type':'checkbox' if f.get('/FT')=='/Btn' else 'text','value':str(f.get('/V') or '')}
            for name,f in fields.items() if f.get('/FT') in ('/Tx','/Btn')}

def refresh_appearances(source, destination, updates=None):
    """Create a separate copy from stored form values; never infer an edit from appearance text."""
    from pypdf import PdfWriter
    source, destination = Path(source), Path(destination)
    require(source.resolve() != destination.resolve(), 'Choose a different filename; the original is preserved.')
    require(not destination.exists(), 'Choose a new output filename.')
    require(source.stat().st_size <= 20_000_000, 'PDF exceeds the 20 MB limit.')
    reader=PdfReader(source)
    require(not reader.is_encrypted and len(reader.pages)==1, 'Only a one-page unencrypted fillable PDF is supported.')
    fields=reader.get_fields() or {}
    require({'two','1a','code22','22ref','24dcpt-1','grp33a.1','diag21.1'} <= fields.keys(), 'Unsupported form template.')
    profiles=json.loads((Path(__file__).parent/'template-profiles.json').read_text())
    require(background_signature(reader.pages[0]) in profiles['background_sha256'], 'Fixed artwork changed; cannot safely refresh this template.')
    for ref in reader.pages[0].get('/Annots',[]):
        widget=ref.get_object();name=widget_name(widget)
        require(widget.get('/Subtype')=='/Widget','Remove PDF markup/overlays first.')
        require(inherited(widget,'/FT') in ('/Tx','/Btn'),'Signed or unsupported field types cannot be refreshed.')
        require(name in fields and clean(inherited(widget,'/V'))==clean(fields[name].get('/V','')), 'Stored field tree and widgets disagree; cannot choose a value automatically.')
    writer=PdfWriter();writer.clone_document_from_reader(reader)
    values={k:(str(v.get('/V') or '/Off') if v.get('/FT')=='/Btn' else str(v.get('/V') or '')) for k,v in fields.items() if v.get('/FT')}
    for key,value in (updates or {}).items():
        require(key in values, f'Unknown/edit-ineligible PDF field: {key}. Use the fields command to list names.')
        if fields[key].get('/FT')=='/Btn':
            val=str(value).lower()
            require(val in ('true','false','yes','no','1','0','/yes','/off',''),f'{key}: checkbox needs true or false.')
            values[key]='/Yes' if val in ('true','yes','1','/yes') else '/Off'
        else:
            require(isinstance(value,str),f'{key}: text field updates must be strings (quote identifiers in JSON).')
            values[key]=value
    def clear_defaults(ref):
        node=ref.get_object()
        for key in ('/DV','/AA'): node.pop(NameObject(key),None)
        for child in node.get('/Kids',[]): clear_defaults(child)
    for ref in writer._root_object['/AcroForm'].get('/Fields',[]): clear_defaults(ref)
    for ref in writer.pages[0].get('/Annots',[]):
        node=ref.get_object();node.pop(NameObject('/DV'),None);node.pop(NameObject('/AA'),None)
    writer._root_object.pop(NameObject('/OpenAction'),None)
    writer._root_object.pop(NameObject('/AA'),None)
    writer.update_page_form_field_values(None,values,auto_regenerate=False)
    writer.compress_identical_objects(remove_duplicates=True,remove_unreferenced=True)
    try:
        with destination.open('xb') as output: writer.write(output)
    except FileExistsError:
        raise ConversionError('Output already exists; choose a new filename.')
    try:
        new=read_pdf(destination)
        require(all(clean(new[k])==clean(v) for k,v in values.items()), 'Stored values changed unexpectedly.')
    except Exception:
        destination.unlink()
        raise
    return destination

def checked(f, key):
    return f.get(key, '') not in ('', '/Off', 'Off')

def choose(f, keys, label):
    selected = [k for k in keys if checked(f, k)]
    require(len(selected) == 1, f'{label}: select exactly one checkbox in the PDF.')
    return selected[0]

def person(value, label):
    parts = clean(value).split(',')
    require(len(parts) == 2 and all(p.strip() for p in parts), f'{label}: use LAST, FIRST MIDDLE in the form field.')
    given = parts[1].strip().split()
    return {'last': edi_text(parts[0], label, 60), 'first': edi_text(given[0], label, 35),
            'middle': edi_text(' '.join(given[1:]), label, 25, False)}

def address(street, city, state, zip_code, label):
    state = edi_text(state, label + ' state', 2)
    require(bool(re.fullmatch('[A-Z]{2}', state)), f'{label}: US state abbreviation required.')
    zip_code = clean(zip_code).replace('-', '')
    require(bool(re.fullmatch(r'\d{5}(\d{4})?', zip_code)), f'{label}: ZIP must have 5 or 9 digits.')
    return {'street': edi_text(street, label + ' street', 55), 'city': edi_text(city, label + ' city', 30),
            'state': state, 'zip': zip_code}

def organization(f, prefix, label):
    city_line = clean(f.get(prefix + '.3'))
    m = re.fullmatch(r'(.+?)\s+([A-Za-z]{2})\s+(\d{5}(?:-?\d{4})?)', city_line)
    require(bool(m), f'{label}: third address line must be CITY ST ZIP.')
    return {'name': edi_text(f.get(prefix + '.1'), label + ' organization', 60),
            'address': address(f.get(prefix + '.2'), *m.groups(), label)}

def parsed_date(mm, dd, yy, label, birth=False):
    require(mm and dd and yy, f'{label}: complete month, day and year required.')
    require(all(re.fullmatch(r'\d+', x) for x in (mm, dd, yy)), f'{label}: numbers only.')
    if birth:
        require(len(yy) == 4, f'{label}: enter a FOUR-digit birth year in the PDF to avoid guessing the century.')
    else:
        require(len(yy) in (2, 4), f'{label}: use a two- or four-digit year.')
    year = int(yy) + (2000 if len(yy) == 2 else 0)
    try:
        d = date(year, int(mm), int(dd))
    except ValueError:
        raise ConversionError(f'{label}: invalid calendar date.')
    if birth:
        require(date(1900, 1, 1) <= d <= date.today(), f'{label}: birth date is out of range.')
    else:
        require(2000 <= year <= date.today().year + 1, f'{label}: service year is out of range.')
    return d.strftime('%Y%m%d')

def money(dollars, cents, label, optional=False):
    if not dollars and not cents and optional:
        return '0.00'
    require(bool(re.fullmatch(r'\d+', dollars or '')), f'{label}: enter whole dollars in the dollars field.')
    require(bool(re.fullmatch(r'\d{1,2}', cents or '00')), f'{label}: enter 0-99 in the cents field.')
    val = Decimal(dollars) + Decimal(cents or '0') / 100
    require(val < Decimal('100000000'), f'{label}: amount too large.')
    return f'{val:.2f}'

def claim_from_fields(f, config):
    # Fail on populated clinical/billing fields that this version does not encode.
    unsupported = ['other9', 'other9a', 'other9d', 'nucc_other9b', 'nucc_other9c',
        'id_ins11b', 'qual_ins11b', 'claim_codes_10d', 'employmentstate',
        'mm14', 'dd14', 'yy14', 'qual14', 'mm15', 'dd15', 'yy15', 'qual15',
        'mm16', 'dd16', 'yy16', 'mmto16', 'ddto16', 'yyto16',
        'qual17', 'name17', 'qual17a', 'id17a', 'id17b',
        'mm18', 'dd18', 'yy18', 'mmto18', 'ddto18', 'yyto18',
        'charge20', 'charge20other', 'dol30', 'cent30', 'pin32b.0', 'grp33b.0',
        'nucc_line1_8', 'nucc_line2_8', 'nucc_line3_8']
    for i in range(1, 7):
        unsupported += [f'24i-0-{i}', f'24j-0-{i}', f'24h-0-{i}', f'24h-1-{i}']
    populated = [key for key in unsupported if f.get(key)]
    require(not populated, 'Unsupported populated fields (nothing exported): ' + ', '.join(populated))
    for key in ['yes10a', 'yes10b', 'yes10c', 'yes11d', 'yes20']:
        require(not checked(f, key), f'{key}: accident/work-related, other-insurance and outside-lab claims are not supported.')
    for keys, label in [(['yes10a','no10a'],'Box 10a'), (['yes10b','no10b'],'Box 10b'),
                        (['yes10c','no10d'],'Box 10c'), (['yes11d','no11d'],'Box 11d')]:
        choose(f, keys, label)
    insurance = choose(f, ['medicare1','medicaid1','champus1','champva1','group1','feca1','otheridd1'], 'Box 1')
    require(insurance in ('group1', 'otheridd1'), 'This version supports commercial primary outpatient claims only.')
    supported = set("cname caddr1 caddr2 ccsz cpage medicare1 medicaid1 champus1 champva1 group1 feca1 otheridd1 1a two 3mm 3dd 3yy sexm sexf four five self6 spouse6 child6 other6 add7 city5 state5 city7 state7 zip5 area5 phone5 zip7 area7 phne7 ins11 yes10a no10a mm11a dd11a male11a yy11a female11a yes10b no10b yes10c no10d ins11c yes11d no11d signature12 12date signature13 addt_claim_info_19 yes20 no20 icd21 code22 22ref prior23 taxid26 ssn ein pat26 yes27 no27 dol28 cent28 dol29 cent29 33areacode phone33 signature31 31date".split())
    supported.update(unsupported)
    supported.update('diag21.'+str(i) for i in range(1,13))
    supported.update(prefix+'.'+str(i) for prefix in ('name32','name33') for i in (1,2,3))
    supported.update(['pin32a.1','grp33a.1'])
    supported.update(prefix+'-'+str(i) for prefix in ('24amm','24add','24ayy','24atomm','24atodd','24atoyy','24b','24c','24dcpt','24dmod','24dfer','24dfera','24dferb','24e','24fdol','24fcent','24g','24j-1') for i in range(1,7))
    unexpected = [key for key,value in f.items() if value not in ('','/Off','Off') and key not in supported]
    require(not unexpected, 'Unrecognized populated fields (nothing exported): '+', '.join(unexpected))
    payer_name = clean(f.get('cname'))
    matches = [v for k,v in config.get('payers', {}).items() if k.casefold() == payer_name.casefold()]
    require(len(matches) == 1, f'Add a payer mapping in Settings for: {payer_name or "(blank payer name)"}.')
    payer = dict(matches[0])
    payer['name'] = edi_text(payer_name, 'Payer name', 60)
    payer['id'] = identifier(payer.get('id'), 'Stedi payer ID')
    require(payer.get('filing_indicator') in ('CI','BL','HM','OF'), 'Payer filing indicator must be CI, BL, HM, or OF.')
    require(payer.get('confirmed') is True, 'Confirm the payer ID against Stedi’s payer directory in Settings.')
    patient = person(f.get('two'), 'Box 2 patient name')
    patient['dob'] = parsed_date(f.get('3mm'), f.get('3dd'), f.get('3yy'), 'Box 3 date of birth', True)
    patient['gender'] = {'sexm':'M', 'sexf':'F'}[choose(f, ['sexm','sexf'], 'Box 3 sex')]
    patient['address'] = address(f.get('five'), f.get('city5'), f.get('state5'), f.get('zip5'), 'Box 5 patient')
    relationship = {'self6':'18','spouse6':'01','child6':'19','other6':'G8'}[choose(f, ['self6','spouse6','child6','other6'], 'Box 6 relationship')]
    subscriber = person(f.get('four'), 'Box 4 insured name')
    if relationship == '18':
        require(all(subscriber[k] == patient[k] for k in ('last','first','middle')), 'Self relationship selected, but patient and insured names differ.')
        subscriber = dict(patient)
        if any(f.get(k) for k in ('mm11a','dd11a','yy11a')):
            require(parsed_date(f.get('mm11a'),f.get('dd11a'),f.get('yy11a'),'Box 11a date of birth',True) == patient['dob'], 'Patient and insured birth dates differ for a self claim.')
        if checked(f,'male11a') or checked(f,'female11a'):
            require({'male11a':'M','female11a':'F'}[choose(f,['male11a','female11a'],'Box 11a sex')] == patient['gender'], 'Patient and insured sex differs for a self claim.')
        if any(f.get(k) for k in ('add7','city7','state7','zip7')):
            require(address(f.get('add7'),f.get('city7'),f.get('state7'),f.get('zip7'),'Box 7 insured') == patient['address'], 'Patient and insured addresses differ for a self claim.')
    else:
        subscriber['dob'] = parsed_date(f.get('mm11a'),f.get('dd11a'),f.get('yy11a'),'Box 11a insured date of birth',True)
        subscriber['gender'] = {'male11a':'M','female11a':'F'}[choose(f,['male11a','female11a'],'Box 11a insured sex')]
        subscriber['address'] = address(f.get('add7'),f.get('city7'),f.get('state7'),f.get('zip7'),'Box 7 insured')
    member = identifier(f.get('1a',''), 'Box 1a member ID', 80)
    billing = organization(f,'name33','Box 33 billing provider')
    billing['npi'] = npi(f.get('grp33a.1'), 'Box 33a billing NPI')
    require(checked(f,'ein') and not checked(f,'ssn'), 'Box 25: organization EIN is required; individual/SSN billing is not supported.')
    billing['tin'] = clean(f.get('taxid26')).replace('-', '')
    require(bool(re.fullmatch(r'\d{9}', billing['tin'])), 'Box 25: a 9-digit EIN is required.')
    billing['taxonomy'] = edi_text(config.get('billing_taxonomy',''), 'Billing taxonomy', 10, False)
    require(not billing['taxonomy'] or bool(re.fullmatch(r'[A-Z0-9]{10}', billing['taxonomy'])), 'Billing taxonomy must have 10 letters/digits.')
    facility = None
    if any(f.get('name32.' + str(i)) for i in (1,2,3)):
        facility = organization(f,'name32','Box 32 facility')
        facility['npi'] = npi(f.get('pin32a.1'),'Box 32a facility NPI') if f.get('pin32a.1') else ''
    require(f.get('icd21') == '0', 'Box 21 must specify ICD-10 (indicator 0).')
    diagnoses = []
    gap = False
    for i in range(1, 13):
        dx = clean(f.get('diag21.' + str(i))).replace('.','').upper()
        if not dx:
            gap = True
            continue
        require(not gap, 'Box 21 diagnoses must be contiguous, starting at A.')
        require(bool(re.fullmatch(r'[A-Z][0-9][A-Z0-9]{1,5}', dx)), f'Box 21 diagnosis {i}: invalid ICD-10-CM format.')
        diagnoses.append(dx)
    require(diagnoses, 'Box 21: at least one diagnosis required.')
    lines = []
    for i in range(1,7):
        keys = [f'24amm-{i}',f'24add-{i}',f'24ayy-{i}',f'24atomm-{i}',f'24atodd-{i}',f'24atoyy-{i}',f'24b-{i}',f'24c-{i}',f'24dcpt-{i}',f'24dmod-{i}',f'24dfer-{i}',f'24dfera-{i}',f'24dferb-{i}',f'24e-{i}',f'24fdol-{i}',f'24fcent-{i}',f'24g-{i}',f'24j-1-{i}']
        if not any(f.get(k) for k in keys):
            continue
        code = edi_text(f.get(f'24dcpt-{i}'), f'Line {i} procedure', 5)
        require(bool(re.fullmatch(r'[A-Z0-9]{5}', code)), f'Line {i}: procedure must be 5 letters/digits.')
        start = parsed_date(f.get(f'24amm-{i}'),f.get(f'24add-{i}'),f.get(f'24ayy-{i}'),f'Line {i} service date')
        end = parsed_date(f.get(f'24atomm-{i}'),f.get(f'24atodd-{i}'),f.get(f'24atoyy-{i}'),f'Line {i} service end date')
        require(end >= start, f'Line {i}: end date precedes start date.')
        require(patient['dob'] <= start and subscriber['dob'] <= start, f'Line {i}: service precedes birth date.')
        pos = clean(f.get(f'24b-{i}'))
        require(pos in ('02','10','11','12','49','50','71','72'), f'Line {i}: supported outpatient places of service are 02, 10, 11, 12, 49, 50, 71, 72.')
        mods = [clean(f.get(f'{k}-{i}')).upper() for k in ('24dmod','24dfer','24dfera','24dferb')]
        seen_blank = False
        for mod in mods:
            if not mod: seen_blank = True
            else:
                require(not seen_blank and bool(re.fullmatch('[A-Z0-9]{2}',mod)), f'Line {i}: modifiers must be consecutive two-character values.')
        pointers = re.split(r'[ ,;]+', clean(f.get(f'24e-{i}')).upper())
        if len(pointers) == 1 and re.fullmatch('[A-L]{2,4}', pointers[0]): pointers = list(pointers[0])
        require(1 <= len(pointers) <= 4 and len(set(pointers)) == len(pointers), f'Line {i}: use 1-4 distinct diagnosis letters.')
        require(all(len(p)==1 and 'A'<=p<=chr(64+len(diagnoses)) for p in pointers), f'Line {i}: diagnosis pointer references a missing diagnosis.')
        amount = money(f.get(f'24fdol-{i}'),f.get(f'24fcent-{i}'),f'Line {i} charge')
        require(Decimal(amount) > 0, f'Line {i}: positive charge required.')
        units = clean(f.get(f'24g-{i}'))
        require(bool(re.fullmatch(r'\d+(\.\d{1,3})?',units)) and Decimal(units)>0 and Decimal(units)<=9999, f'Line {i}: invalid units.')
        render_npi = npi(f.get(f'24j-1-{i}'),f'Line {i} rendering NPI')
        provider = config.get('rendering_providers',{}).get(render_npi)
        require(bool(provider), f'Add rendering provider {render_npi} in Settings.')
        renderer = {k:edi_text(provider.get(k,''), 'Rendering provider '+k, 60 if k=='last' else 35, k!='middle') for k in ('last','first','middle')}
        renderer['npi'] = render_npi
        renderer['taxonomy'] = edi_text(provider.get('taxonomy',''),'Rendering taxonomy',10,False)
        require(not renderer['taxonomy'] or bool(re.fullmatch('[A-Z0-9]{10}', renderer['taxonomy'])), 'Rendering taxonomy must have 10 letters/digits.')
        emergency = clean(f.get(f'24c-{i}')).upper()
        require(emergency in ('','N','Y'), f'Line {i}: emergency field must be blank, N, or Y.')
        lines.append({'source_line':i, 'code':code,'modifiers':[x for x in mods if x], 'start':start,'end':end,
                      'pos':pos,'pointers':[str(ord(p)-64) for p in pointers],'amount':amount,'units':units,'renderer':renderer,'emergency':emergency})
    require(lines, 'At least one service line required.')
    require(len({x['renderer']['npi'] for x in lines}) == 1, 'Multiple rendering providers on one form are not supported yet.')
    total = money(f.get('dol28'), f.get('cent28'), 'Box 28 total')
    require(sum(Decimal(x['amount']) for x in lines) == Decimal(total), 'Box 28 does not equal the sum of line charges. Update both when changing charges.')
    paid = money(f.get('dol29'),f.get('cent29'),'Box 29 patient amount paid',True)
    require(Decimal(paid)<=Decimal(total), 'Box 29 exceeds total charges; reconcile before conversion.')
    frequency = f.get('code22') or '1'
    require(frequency in ('1','7','8'), 'Box 22: use blank/1 for original, 7 for replacement, or 8 for void.')
    original = identifier(f.get('22ref',''), 'Box 22 payer claim number',50,frequency in ('7','8'))
    require(frequency != '1' or not original, 'Original claim has a prior payer claim number: choose correction code 7/8 or clear the reference.')
    source_control = identifier(f.get('pat26',''), 'Box 26 account/claim identifier', 38)
    require(not original or original != source_control, 'Box 22 equals Box 26. Supply the payer-assigned claim number, not your own account number.')
    for key,label in [('signature12','Box 12'),('signature13','Box 13')]:
        require(clean(f.get(key)).upper() in ('SIGNATURE ON FILE','SOF'), f'{label}: this version requires SIGNATURE ON FILE recorded in the form.')
    require(bool(f.get('signature31')), 'Box 31 provider signature/on-file attestation required.')
    assignment = {'yes27':'A','no27':'C'}[choose(f,['yes27','no27'],'Box 27 assignment')]
    submitter = config.get('submitter',{})
    submitter = {'name':edi_text(submitter.get('name'),'Submitter name',60),
                 'id':identifier(submitter.get('id'),'Submitter ID',80),
                 'contact':edi_text(submitter.get('contact'),'Submitter contact',60),
                 'phone':re.sub(r'[- ()]', '', str(submitter.get('phone','')))}
    require(bool(re.fullmatch(r'\d{10}', submitter['phone'])), 'Submitter contact phone must contain 10 digits.')
    return {'payer':payer,'patient':patient,'subscriber':subscriber,'relationship':relationship,'member_id':member,
            'billing':billing,'facility':facility,'diagnoses':diagnoses,'lines':lines,'total':total,'patient_paid':paid,
            'frequency':frequency,'original_payer_claim_number':original,'source_control':source_control,
            'group_number':edi_text(f.get('ins11'),'Box 11 group number',50,False),
            'plan_name':edi_text(f.get('ins11c'),'Box 11c plan name',60,False),
            'prior_authorization':edi_text(f.get('prior23'),'Box 23 prior authorization',50,False),
            'note':edi_text(f.get('addt_claim_info_19'),'Box 19 claim note',80,False),
            'assignment':assignment,'submitter':submitter}

def build_edi(claim, mode='T', control=None, now=None):
    require(mode in ('T','P'), 'Mode must be T (test) or P (production).')
    require(mode != 'P' or not claim['payer'].get('test_only'), 'The synthetic demo payer can only generate test files.')
    now = now or datetime.now()
    pc = control or ('C'+secrets.token_hex(8).upper())
    require(bool(re.fullmatch('[A-Z0-9]{1,17}', pc)), 'Generated claim identifier must be 1-17 uppercase letters/digits.')
    icn = str(secrets.randbelow(999999999)+1).zfill(9)
    tx = '0001'
    segments = []
    def add(tag,*parts):
        segments.append('*'.join([tag]+[str(x) for x in parts]).rstrip('*')+'~')
    add('ST','837',tx,'005010X222A1')
    add('BHT','0019','00',pc,now.strftime('%Y%m%d'),now.strftime('%H%M'),'CH')
    s=claim['submitter']; b=claim['billing']; sub=claim['subscriber']; pt=claim['patient']
    def named(code,p,member=''):
        add('NM1',code,'1',p['last'],p['first'],p['middle'],'','','MI' if member else '',member)
    def addr(a):
        add('N3',a['street']); add('N4',a['city'],a['state'],a['zip'])
    add('NM1','41','2',s['name'],'','','','','46',s['id'])
    add('PER','IC',s['contact'],'TE',s['phone'])
    add('NM1','40','2','STEDI','','','','','46','STEDI')
    add('HL','1','','20','1')
    if b['taxonomy']: add('PRV','BI','PXC',b['taxonomy'])
    add('NM1','85','2',b['name'],'','','','','XX',b['npi']); addr(b['address']); add('REF','EI',b['tin'])
    dependent = claim['relationship'] != '18'
    add('HL','2','1','22','1' if dependent else '0')
    add('SBR','P','' if dependent else '18',claim['group_number'],claim['plan_name'] if not claim['group_number'] else '','','','','',claim['payer']['filing_indicator'])
    named('IL',sub,claim['member_id']); addr(sub['address']); add('DMG','D8',sub['dob'],sub['gender'])
    add('NM1','PR','2',claim['payer']['name'],'','','','','PI',claim['payer']['id'])
    if dependent:
        add('HL','3','2','23','0'); add('PAT',claim['relationship']); named('QC',pt); addr(pt['address']); add('DMG','D8',pt['dob'],pt['gender'])
    pos=claim['lines'][0]['pos']
    add('CLM',pc,claim['total'],'','',pos+':B:'+claim['frequency'],'Y',claim['assignment'],'Y','Y')
    if Decimal(claim['patient_paid']): add('AMT','F5',claim['patient_paid'])
    if claim['prior_authorization']: add('REF','G1',claim['prior_authorization'])
    if claim['original_payer_claim_number']: add('REF','F8',claim['original_payer_claim_number'])
    if claim['note']: add('NTE','ADD',claim['note'])
    add('HI',*[('ABK:' if i==0 else 'ABF:')+dx for i,dx in enumerate(claim['diagnoses'])])
    render=claim['lines'][0]['renderer']
    add('NM1','82','1',render['last'],render['first'],render['middle'],'','','XX',render['npi'])
    if render['taxonomy']: add('PRV','PE','PXC',render['taxonomy'])
    facility=claim['facility']
    if facility and (facility['address']!=b['address'] or (facility['npi'] and facility['npi']!=b['npi'])):
        add('NM1','77','2',facility['name'],'','','','','XX' if facility['npi'] else '',facility['npi']); addr(facility['address'])
    for i,line in enumerate(claim['lines'],1):
        add('LX',i)
        add('SV1',':'.join(['HC',line['code']]+line['modifiers']),line['amount'],'UN',line['units'],line['pos'] if line['pos']!=pos else '','',':'.join(line['pointers']),'','Y' if line['emergency']=='Y' else '')
        add('DTP','472','D8' if line['start']==line['end'] else 'RD8',line['start'] if line['start']==line['end'] else line['start']+'-'+line['end'])
        add('REF','6R',pc+'L'+str(i))
    add('SE',len(segments)+1,tx)
    isa='*'.join(['ISA','00',' '*10,'00',' '*10,'ZZ','LOCAL'.ljust(15),'ZZ','STEDI'.ljust(15),now.strftime('%y%m%d'),now.strftime('%H%M'),'^','00501',icn,'0',mode,':'])+'~'
    require(len(isa)==106, 'Internal error: malformed ISA length.')
    gs='*'.join(['GS','HC','LOCAL','STEDI',now.strftime('%Y%m%d'),now.strftime('%H%M'),'1','X','005010X222A1'])+'~'
    edi='\n'.join([isa,gs]+segments+['GE*1*1~','IEA*1*'+icn+'~'])+'\n'
    return edi,pc

def review_text(c):
    def name(p): return ', '.join([p['last'], ' '.join(x for x in [p['first'],p['middle']] if x)])
    def addr(a): return f"{a['street']}, {a['city']} {a['state']} {a['zip']}"
    rows=[f"Payer: {c['payer']['name']} | ID {c['payer']['id']} | filing {c['payer']['filing_indicator']}",
          f"Submission: { {'1':'ORIGINAL','7':'REPLACEMENT','8':'VOID'}[c['frequency']] } (code {c['frequency']})",
          f"Original payer claim number: {c['original_payer_claim_number'] or '(none)'}",
          f"Source Box 26: {c['source_control']} | a new unique outgoing claim ID will be generated",
          f"Patient: {name(c['patient'])} | DOB {c['patient']['dob']} | sex {c['patient']['gender']}",
          f"Patient address: {addr(c['patient']['address'])}",
          f"Insured: {name(c['subscriber'])} | DOB {c['subscriber']['dob']} | sex {c['subscriber']['gender']}",
          f"Insured address: {addr(c['subscriber']['address'])}",
          f"Relationship: {c['relationship']} | Member ID: {c['member_id']}",
          f"Group: {c['group_number'] or '(none)'} | Plan: {c['plan_name'] or '(none)'}",
          f"Billing: {c['billing']['name']} | NPI {c['billing']['npi']} | EIN {c['billing']['tin']}",
          f"Billing address: {addr(c['billing']['address'])} | Taxonomy: {c['billing']['taxonomy'] or '(not set)'}",
          f"Diagnoses: {', '.join(chr(65+i)+'='+v for i,v in enumerate(c['diagnoses']))}",
          f"Box 23 authorization: {c['prior_authorization'] or '(none)'}",
          f"Box 19 note: {c['note'] or '(none)'}",
          f"Assignment: {c['assignment']} | patient and insured signatures on file; provider signature present",'','SERVICE LINES']
    for l in c['lines']:
        rows += [f"{l['source_line']}. {l['start']}–{l['end']} | {l['code']} {','.join(l['modifiers'])} | POS {l['pos']} | units {l['units']} | ${l['amount']} | diagnoses {','.join(l['pointers'])} | emergency {l['emergency'] or 'N'}",
                 f"   Rendering: {name(l['renderer'])}, NPI {l['renderer']['npi']}, taxonomy {l['renderer']['taxonomy'] or '(not set)'}"]
    fac=c['facility']
    rows += ['',f"Facility: {fac['name']+' | '+addr(fac['address'])+' | NPI '+fac['npi'] if fac else '(none)'}",
             'Facility loop is omitted when its address/NPI match the billing provider.',
             f"TOTAL: ${c['total']} | PATIENT ALREADY PAID (Box 29): ${c['patient_paid']}",
             'Box 29 must contain actual patient payments, not an estimated copay or an insurer payment.',
             f"Submitter: {c['submitter']['name']} | {c['submitter']['id']} | {c['submitter']['contact']} | {c['submitter']['phone']}",
             '', 'Review every value against the saved PDF. Check DOB centuries and member/subscriber relationship.',
             'All two-digit service years are interpreted as 20xx. Birth years must contain four digits.',
             'This is a primary commercial claim. The converter does not determine payer rules or coding correctness.',
             'It creates a local file only. No submission or TheraNest ledger update occurs.']
    return '\n'.join(rows)

def load_config(path):
    result=json.loads(Path(path).read_text())
    require(isinstance(result,dict), 'Settings must be a JSON object.')
    return result

def export_bundle(pdf_path, config_path, output_dir, mode='T', expected_pdf_hash=None, expected_config_hash=None):
    pdf_path,config_path=Path(pdf_path),Path(config_path)
    ph=hashlib.sha256(pdf_path.read_bytes()).hexdigest();ch=hashlib.sha256(config_path.read_bytes()).hexdigest()
    require(not expected_pdf_hash or ph==expected_pdf_hash,'PDF changed after review. Load it again.')
    require(not expected_config_hash or ch==expected_config_hash,'Settings changed after review. Load the PDF again.')
    c=claim_from_fields(read_pdf(pdf_path),load_config(config_path))
    edi,pc=build_edi(c,mode)
    out=Path(output_dir)/('claim-'+pc)
    out.mkdir(parents=True,exist_ok=False)
    try:
        (out/('claim-'+mode+'.edi')).write_text(edi,encoding='ascii')
        (out/'review.txt').write_text(review_text(c)+'\n\nOutgoing claim ID: '+pc+'\nMode: '+mode+'\n',encoding='utf-8')
        record={'version':VERSION,'created_at':datetime.now().isoformat(),'source_pdf':pdf_path.name,'source_sha256':ph,
                'source_box26':c['source_control'],'outgoing_claim_id':pc,'payer_claim_number':c['original_payer_claim_number'],
                'frequency':c['frequency'],'mode':mode,'claim':c}
        (out/'claim-record.json').write_text(json.dumps(record,indent=2),encoding='utf-8')
    except Exception:
        for f in out.iterdir(): f.unlink()
        out.rmdir()
        raise
    return out

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pdf');parser.add_argument('--config',required=True)
    parser.add_argument('--output');parser.add_argument('--production',action='store_true')
    parser.add_argument('--reviewed',action='store_true',help='Confirm that the PDF and extracted fields have been reviewed')
    a=parser.parse_args()
    try:
        c=claim_from_fields(read_pdf(a.pdf),load_config(a.config))
        print(review_text(c))
        if a.output:
            require(a.reviewed,'Read the review and rerun with --reviewed to generate an EDI file.')
            print('\nSaved:',export_bundle(a.pdf,a.config,a.output,'P' if a.production else 'T'))
    except (ConversionError,ValueError,OSError) as exc:
        print('\nCannot convert:',exc,file=sys.stderr);sys.exit(1)
