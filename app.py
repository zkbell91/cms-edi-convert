"""Offline desktop interface. No network requests and no claim submission."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText
from converter import read_pdf, claim_from_fields, load_config, review_text, export_bundle, refresh_appearances

from shared_settings import ensure as ensure_settings, save as save_settings

ROOT = Path(__file__).resolve().parent

def open_file(path):
    if sys.platform == 'darwin': subprocess.Popen(['open', str(path)])
    elif sys.platform == 'win32':
        import os
        os.startfile(str(path))
    else: subprocess.Popen(['xdg-open', str(path)])

class App:
    def __init__(self, root):
        self.root=root;self.claim=None;self.snapshot=None;self.last_output=None
        self.config_path=ensure_settings()
        root.title('CMS-1500 → 837P');root.geometry('1060x820');root.minsize(850,660)
        style=ttk.Style(root);style.theme_use('clam')
        style.configure('TFrame',background='#f4f6f9');style.configure('TLabel',background='#f4f6f9',font=('Helvetica',11))
        style.configure('Title.TLabel',font=('Helvetica',22,'bold'),foreground='#173450')
        style.configure('TButton',font=('Helvetica',11),padding=9)
        style.configure('Accent.TButton',background='#173450',foreground='white')
        frame=ttk.Frame(root,padding=24);frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='CMS-1500 → 837P',style='Title.TLabel').pack(anchor='w')
        ttk.Label(frame,text='Edit your fillable PDF • review the extracted claim • save an 837P file',wraplength=950).pack(anchor='w',pady=(5,14))
        bar=ttk.Frame(frame);bar.pack(fill='x')
        ttk.Button(bar,text='1  Choose edited PDF',command=self.choose_pdf,style='Accent.TButton').pack(side='left')
        ttk.Button(bar,text='Practice & payer settings',command=self.settings).pack(side='left',padx=9)
        ttk.Button(bar,text='Try synthetic demo',command=self.demo).pack(side='left')
        ttk.Button(bar,text='Refresh PDF fields',command=self.refresh).pack(side='left',padx=9)
        ttk.Button(bar,text='Instructions',command=lambda:open_file(ROOT/'START_HERE.html')).pack(side='right')
        self.path=tk.StringVar();ttk.Label(frame,textvariable=self.path,wraplength=960).pack(anchor='w',pady=(12,3))
        self.status=tk.StringVar(value='Select a saved, fillable CMS-1500 PDF. No data leaves this computer.')
        ttk.Label(frame,textvariable=self.status,wraplength=960,foreground='#344b63').pack(anchor='w',pady=(4,10))
        self.text=ScrolledText(frame,wrap='word',font=('Menlo',11),bg='white',fg='#172f46',padx=15,pady=15)
        self.text.pack(fill='both',expand=True);self.show('Your claim review will appear here.\n\nThis version supports the supplied fillable template, primary commercial outpatient claims, and up to six service lines.\n\nUse the PDF’s actual form fields. Flattened PDFs, image-only PDFs, and added markup are not supported.\n\nThe app stops on missing information, conflicting field appearances, and unsupported populated claim fields.')
        self.reviewed=tk.BooleanVar(value=False)
        ttk.Checkbutton(frame,text='2  I checked the saved PDF against this review, including the payer reference, dates, codes, and charges.',variable=self.reviewed).pack(anchor='w',pady=(14,8))
        bottom=ttk.Frame(frame);bottom.pack(fill='x')
        ttk.Button(bottom,text='Open source PDF',command=self.open_pdf).pack(side='left')
        self.mode=tk.StringVar(value='Test file')
        ttk.Combobox(bottom,textvariable=self.mode,values=['Test file','Production file'],state='readonly',width=17).pack(side='left',padx=12)
        self.generate=ttk.Button(bottom,text='3  Save EDI file',style='Accent.TButton',command=self.save,state='disabled');self.generate.pack(side='right')
        ttk.Label(frame,text='Test is the default. A production file reaches a payer only after you submit it through your clearinghouse.',wraplength=960).pack(anchor='w',pady=(9,0))
    def show(self,text):
        self.text.configure(state='normal');self.text.delete('1.0','end');self.text.insert('1.0',text);self.text.configure(state='disabled')
    def choose_pdf(self):
        p=filedialog.askopenfilename(title='Choose the edited, fillable PDF',filetypes=[('PDF files','*.pdf')])
        if p:
            self.config_path=ensure_settings();self.load(p)
    def load(self,p):
        self.path.set(p);self.reviewed.set(False);self.claim=None;self.generate.configure(state='disabled')
        try:
            f=read_pdf(p);self.claim=claim_from_fields(f,load_config(self.config_path))
            self.snapshot=(hashlib.sha256(Path(p).read_bytes()).hexdigest(),hashlib.sha256(self.config_path.read_bytes()).hexdigest())
            self.show(review_text(self.claim));self.generate.configure(state='normal')
            self.status.set('Ready for review. No file has been generated or submitted.')
        except Exception as exc:
            self.show('CANNOT CONVERT THIS PDF\n\n'+str(exc)+'\n\nCorrect the PDF or settings, then choose the PDF again. No claim file was created.')
            self.status.set('Needs attention. The converter has stopped; it has not guessed missing values.')
    def demo(self):
        self.config_path=ROOT/'examples'/'synthetic-settings.json';self.mode.set('Test file')
        self.load(str(ROOT/'examples'/'synthetic-field-test.pdf'))
    def refresh(self):
        source=self.path.get() or filedialog.askopenfilename(title='Choose a PDF with stale field appearances',filetypes=[('PDF files','*.pdf')])
        if not source:return
        if not messagebox.askokcancel('Create a refreshed copy', 'This creates a separate PDF from the stored form values. Text left only in old appearances will disappear. It does not recover removed patient data.\n\nOpen and inspect the new PDF before converting it. The original will remain unchanged.'):
            return
        target=filedialog.asksaveasfilename(title='Save refreshed PDF as a new file',initialfile=Path(source).stem+'-refreshed.pdf',defaultextension='.pdf')
        if not target:return
        try:
            refresh_appearances(source,target)
            self.claim=None;self.generate.configure(state='disabled');self.reviewed.set(False)
            self.status.set('Refreshed copy saved. Inspect it, complete missing fields, and choose it again for conversion.')
            open_file(target)
        except Exception as exc:messagebox.showerror('Cannot refresh PDF',str(exc))
    def open_pdf(self):
        if self.path.get(): open_file(self.path.get())
    def save(self):
        if not self.claim:return
        if not self.reviewed.get():
            messagebox.showinfo('Review needed','Check the source PDF against the extracted values, then mark the review checkbox.');return
        folder=filedialog.askdirectory(title='Choose where to save the claim folder',initialdir=str(ROOT/'exports'))
        if not folder:return
        try:
            mode='P' if self.mode.get()=='Production file' else 'T'
            result=export_bundle(self.path.get(),self.config_path,folder,mode,*self.snapshot)
            self.last_output=result;self.generate.configure(state='disabled')
            self.status.set('Saved locally. Nothing was submitted. Choose the PDF again to prepare another file.')
            messagebox.showinfo('Saved',f'Saved {result.name}\n\nIncludes the .edi file, a readable review, and a claim-ID crosswalk.\n\nNothing was submitted to a clearinghouse or payer.')
            open_file(result)
        except Exception as exc: messagebox.showerror('Cannot export',str(exc))
    def settings(self):
        settings_path=ensure_settings()
        cfg=load_config(settings_path)
        win=tk.Toplevel(self.root);win.title('Practice & payer settings');win.geometry('800x740')
        box=ttk.Frame(win,padding=20);box.pack(fill='both',expand=True)
        ttk.Label(box,text='One-time settings',style='Title.TLabel').grid(row=0,column=0,columnspan=2,sticky='w',pady=(0,8))
        ttk.Label(box,text='Billing NPI, EIN, and address come from each PDF. These settings supply missing electronic details.',wraplength=740).grid(row=1,column=0,columnspan=2,sticky='w',pady=(0,12))
        entries={};row=2
        def entry(key,label,value='',choices=None):
            nonlocal row
            ttk.Label(box,text=label).grid(row=row,column=0,sticky='w',padx=(0,20),pady=3)
            v=tk.StringVar(value=value);entries[key]=v
            w=ttk.Combobox(box,textvariable=v,values=choices,width=43) if choices is not None else ttk.Entry(box,textvariable=v,width=46)
            w.grid(row=row,column=1,sticky='ew',pady=3);row+=1;return w
        for k,label in [('name','Submitter organization'),('id','Submitter identifier'),('contact','Contact name'),('phone','Contact phone')]: entry('sub_'+k,label,cfg.get('submitter',{}).get(k,''))
        entry('billing_taxonomy','Billing taxonomy (optional)',cfg.get('billing_taxonomy',''))
        ttk.Separator(box).grid(row=row,column=0,columnspan=2,sticky='ew',pady=9);row+=1
        payer_keys=list(cfg.get('payers',{}));payer=payer_keys[0] if payer_keys else ''
        picker=entry('payer_name','Payer name exactly as printed',payer,payer_keys)
        entry('payer_id','Payer ID (keep leading zeros)')
        entry('filing','Filing code: CI / BL / HM / OF','CI',['CI','BL','HM','OF'])
        confirmed=tk.BooleanVar()
        ttk.Checkbutton(box,text='I verified this payer ID for professional claims.',variable=confirmed).grid(row=row,column=0,columnspan=2,sticky='w',pady=5);row+=1
        def payer_changed(event=None):
            v=cfg.get('payers',{}).get(entries['payer_name'].get(),{})
            entries['payer_id'].set(v.get('id',''));entries['filing'].set(v.get('filing_indicator','CI'));confirmed.set(v.get('confirmed',False))
        entries['payer_id'].trace_add('write',lambda *_:confirmed.set(False))
        picker.bind('<<ComboboxSelected>>',payer_changed);payer_changed()
        ttk.Separator(box).grid(row=row,column=0,columnspan=2,sticky='ew',pady=9);row+=1
        provider_keys=list(cfg.get('rendering_providers',{}));provider=provider_keys[0] if provider_keys else ''
        picker2=entry('npi','Rendering provider NPI',provider,provider_keys)
        entry('first','Provider first name');entry('last','Provider last name');entry('middle','Provider middle name (optional)');entry('taxonomy','Rendering taxonomy (optional)')
        def provider_changed(event=None):
            v=cfg.get('rendering_providers',{}).get(entries['npi'].get(),{})
            for k in ('first','last','middle','taxonomy'):entries[k].set(v.get(k,''))
        picker2.bind('<<ComboboxSelected>>',provider_changed);provider_changed()
        def save():
            try:
                cfg['submitter']={k:entries['sub_'+k].get().strip() for k in ('name','id','contact','phone')}
                cfg['billing_taxonomy']=entries['billing_taxonomy'].get().strip()
                pname=entries['payer_name'].get().strip();pid=entries['payer_id'].get().strip()
                if pname:cfg.setdefault('payers',{})[pname]={'id':pid,'filing_indicator':entries['filing'].get().strip(),'confirmed':confirmed.get()}
                np=entries['npi'].get().strip()
                if np:cfg.setdefault('rendering_providers',{})[np]={k:entries[k].get().strip() for k in ('first','last','middle','taxonomy')}
                save_settings(settings_path,cfg)
                self.claim=None;self.generate.configure(state='disabled');self.reviewed.set(False)
                self.status.set('Settings saved. Choose the PDF again to refresh the review.');win.destroy()
            except Exception as exc:messagebox.showerror('Cannot save settings',str(exc),parent=win)
        ttk.Button(box,text='Save settings',style='Accent.TButton',command=save).grid(row=row,column=1,sticky='e',pady=12)
        box.columnconfigure(1,weight=1)

if __name__=='__main__':
    root=tk.Tk();App(root);root.mainloop()
