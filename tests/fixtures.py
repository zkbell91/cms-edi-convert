"""Fictional data only. Never derive test patient data from the user's PDF."""
from pathlib import Path

def fields():
    return {
        'cname':'SYNTHETIC TEST PAYER','otheridd1':'/Yes',
        '1a':'000123ABC','two':'EXAMPLE, AVERY','four':'EXAMPLE, AVERY',
        '3mm':'04','3dd':'12','3yy':'1980','sexm':'/Yes',
        'five':'123 TEST STREET','city5':'BOSTON','state5':'MA','zip5':'02108',
        'self6':'/Yes','no10a':'/Yes','no10b':'/Yes','no10d':'/Yes','no11d':'/Yes',
        'signature12':'SIGNATURE ON FILE','signature13':'SIGNATURE ON FILE','signature31':'TEST PROVIDER',
        'icd21':'0','diag21.1':'F331','code22':'7','22ref':'000TESTCLAIM123',
        'taxid26':'000123456','ein':'/Yes','pat26':'000TESTACCOUNT','yes27':'/Yes',
        'dol28':'100','cent28':'00','dol29':'0','cent29':'00',
        'name33.1':'SYNTHETIC TEST PRACTICE','name33.2':'123 TEST STREET','name33.3':'BOSTON MA 021080000',
        'grp33a.1':'1999999984',
        '24amm-1':'07','24add-1':'30','24ayy-1':'26','24atomm-1':'07','24atodd-1':'30','24atoyy-1':'26',
        '24b-1':'10','24dcpt-1':'90834','24dmod-1':'95','24e-1':'A','24fdol-1':'100','24fcent-1':'00','24g-1':'1','24j-1-1':'1999999984',
    }

def config():
    return {'submitter':{'name':'SYNTHETIC TEST PRACTICE','id':'LOCALTEST','contact':'TEST CONTACT','phone':'8005550100'},
        'billing_taxonomy':'',
        'payers':{'SYNTHETIC TEST PAYER':{'id':'TESTPAYER','filing_indicator':'CI','confirmed':True,'test_only':True}},
        'rendering_providers':{'1999999984':{'first':'TEST','last':'PROVIDER','middle':'','taxonomy':''}}}

def make_pdf(path, values=None):
    from reportlab.pdfgen import canvas
    from reportlab.lib.colors import HexColor, black, white
    f=fields() if values is None else values
    # Full field names deliberately mirror the supplied template; this is a test sheet, not a billing form.
    c=canvas.Canvas(str(path),pagesize=(840,1000))
    c.setTitle('Synthetic CMS-1500 field test - not for billing')
    c.setFillColor(HexColor('#142b45'));c.rect(0,915,840,85,fill=1,stroke=0)
    c.setFillColor(white);c.setFont('Helvetica-Bold',20);c.drawString(30,964,'SYNTHETIC CONVERTER TEST')
    c.setFont('Helvetica',12);c.drawString(30,941,'Fictional data / test output only / not a CMS-1500 billing form')
    for index,(name,value) in enumerate(f.items()):
        col=index//29;row=index%29;x=30+col*402;y=887-row*29
        c.setFillColor(black);c.setFont('Helvetica',9);c.drawString(x,y+5,name)
        if value.startswith('/'):
            c.acroForm.checkbox(name=name,x=x+130,y=y,size=14,checked=value=='/Yes',buttonStyle='check',borderWidth=1)
        else:
            c.acroForm.textfield(name=name,x=x+130,y=y,width=246,height=20,value=value,fontName='Helvetica',fontSize=9,borderWidth=1,forceBorder=True)
    c.save()
