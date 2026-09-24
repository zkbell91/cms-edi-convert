# CMS-1500 PDF → Stedi 837P converter

Version 0.2.0 — reusable local desktop program for the supplied TheraNest fillable CMS-1500 template.

## Install (another Mac or Linux)

Requires **Python 3.10+** with Tkinter (python.org installers include it). No pip, API key, or network needed for conversion; `pypdf` is vendored.

```sh
git clone git@github.com:zkbell91/cms-edi-convert.git
cd cms-edi-convert
python3 install_cli.py
```

That copies the app to `~/.local/share/cms-edi-convert` and links `~/.local/bin/cms-edi-convert`. If the installer says PATH is missing that bin directory, add it once:

```sh
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc && source ~/.zshrc
```

Update later with `python3 install_cli.py --update` from a fresh clone. Shared settings stay in `~/.config/cms-edi-convert/settings.json`. You can also run `./cms-edi-convert` from the repo without installing. Windows: use **Run Converter.bat** or `cms-edi-convert.cmd` (Unix installer is not for Windows).

## Start (desktop)

1. Clone or extract the project to a folder you can write to.
2. On macOS, double-click **Run Converter.command**. On Windows, use **Run Converter.bat**.
3. Click **Try synthetic demo** to see the review and generate a test file without patient data.
4. Open **Practice & payer settings**. Confirm the practice details and enter the correct Stedi payer ID for each payer name printed on your PDFs. The Florida payer entry is intentionally blank until verified; it is not inferred from the name.
5. Edit a CMS-1500 in your PDF editor, save it, and choose it in the app.
6. Inspect the complete claim review and the saved PDF. Mark the review checkbox and save the EDI file to your chosen folder.

Python 3.10+ with Tkinter is required. The launcher prefers a common `python3` on PATH. The PDF reader dependency is bundled; there is no pip-install or API-key step for ordinary use. Windows is supplied but has not been run on Windows.

The program does not connect to Stedi, upload claims, enroll providers, change TheraNest, or send data elsewhere. Its PDF refresh and conversion work locally. Generated claim folders contain patient and billing information and should be kept with your other claim records.

## Terminal command

```sh
cms-edi-convert ~/Downloads/cms1500.pdf ~/Downloads/cms1500.edi
```

Defaults to a test file. Add `--production` for a production file. Use `settings`, `fields`, `edit`, `refresh`, and `review` for the complete CLI workflow. See [CLI_GUIDE.md](CLI_GUIDE.md) for examples, installation, and all settings/field editing commands.

## Editing your PDF

Use the actual interactive form fields, not text boxes or white rectangles placed over them. Keep the PDF fillable; do not flatten it or use Print to PDF. The fixed page artwork must match this template. The program checks its fingerprint and rejects changed artwork, scans, other layouts, annotations, and disagreements between saved values and displayed appearances. PDF editors that rewrite the artwork may need a new template profile; rejection is preferable to reading an obscured old value.

- For a replacement, put **7** in Box 22 and the payer-assigned original claim control number in its reference field. Your internal TheraNest account/claim number is a different identifier.
- Change the CPT in Box 24D. Preserve applicable modifiers and diagnosis pointers.
- When charges change, update both the line charge (24F) and total (28).
- Include the complete replacement claim, including unchanged lines.
- Enter **four-digit birth years** in Boxes 3 and 11a. The program will not guess a birth century. Two-digit service years are interpreted as 20xx and shown in full in the review.
- Use `LAST, FIRST MIDDLE` for patient and insured names. Select the relationship, sex, and relevant yes/no checkboxes.
- Box 29 is actual patient money already paid toward this claim. It is not an estimated copay or the amount the insurer paid.
- If the patient has a payer-assigned member ID of their own, confirm the appropriate insured/dependent arrangement with the payer. The app follows the relationship on the PDF and does not infer it from the member ID's shape.

### A PDF says one thing but displays another

Some editors save updated values without rebuilding the cached field appearances. Your provided sample had 29 such disagreements; patient fields stored as blank still displayed old content.

The converter refuses to generate an EDI from that state. **Refresh PDF fields** creates a separate, fillable copy using the stored field values and regenerates their appearances. It does not recover deleted values or infer what you intended. The original stays unchanged. Open the new copy, inspect it, finish any missing fields, save it, and choose it again for conversion. A displayed-only change that was never saved into a form field cannot be recovered this way. This feature is appearance repair, not a general PDF redaction service.

## Settings saved between runs

`~/.config/cms-edi-convert/settings.json` (or `%APPDATA%/CMS-EDI-Converter/settings.json` on Windows) holds practice contact information, payer-name-to-ID mappings, rendering provider names keyed by NPI, and optional taxonomies. Both the desktop UI and CLI edit this file. Existing local settings are migrated on first use; an existing shared file is preserved. Billing organization, NPI, EIN, and address are read from each PDF.

The payer name must match the PDF's carrier heading, ignoring capitalization. Add another mapping by typing another payer name in Settings. Check its professional-claims route in Stedi's payer directory; keep IDs such as `00590` as text. Filing indicators supported here: `CI` commercial, `BL` Blue Cross/Blue Shield, `HM` HMO, `OF` other federal. This list is not a recommendation for a particular plan. Traditional Medicare, Medicaid, TRICARE, FECA, and other noncommercial workflows are outside this version's scope.

The `LOCAL` submitter identifier is a local default, not a payer ID. The generated envelope uses LOCAL/STEDI identifiers; Stedi documents that it rebuilds transmission envelopes. Payer routing comes from the payer ID in the claim. Complete any payer-required claim enrollment and supply taxonomies where required.

## Supported claims

- One one-page fillable CMS-1500 per conversion, from the supplied template.
- Primary commercial outpatient professional claims, with an organization billing NPI and EIN.
- Original (`1`, or blank Box 22), replacement (`7`), and void (`8`) files, subject to the payer's requirements.
- Self, spouse, child, and other dependent relationships with the corresponding insured and patient data.
- Up to six service lines and twelve ICD-10 diagnoses, four modifiers per line, diagnosis pointers, date ranges, and units.
- Outpatient places of service 02, 10, 11, 12, 49, 50, 71, and 72.
- One rendering provider per form, optional separate service facility, prior authorization, a short claim note, and actual patient payments.

This is not a universal converter for every CMS-1500 scenario. It rejects secondary/tertiary and coordination-of-benefits claims, accident/work-related claims, outside-lab charges, other claim IDs, populated referring-provider fields, illness/hospitalization/work-disability dates, EPSDT/family-planning fields, and other unsupported populated billing fields. It does not generate attachments, decide coding correctness, determine patient benefits, reconcile payments, or implement Medicare reopening rules. Individual/SSN billing and signed-document modification are unsupported.

Payer mailing addresses, patient/insured telephone numbers, print metadata, and signature dates are not transmitted. The source signature/on-file indicators are represented in CLM, and submitter contact details come from Settings. A plan name is transmitted in SBR04 only when no group number is present. A facility identical to the billing address/NPI does not generate a redundant facility loop.

## Output and Stedi

Each export creates a new folder containing:

- `claim-T.edi` for test mode or `claim-P.edi` for production mode.
- `review.txt` with the extracted information and outgoing identifier.
- `claim-record.json` with the source file hash, original Box 26 value, newly generated outgoing claim ID, payer reference, and normalized claim.

A new 17-character outgoing claim ID is generated for each export, including original claims. Keep the output and crosswalk. Generating another file is a new submission identifier; do not use repeated exports to retry an uncertain transmission without first checking its status.

In Stedi, go to **Claims → Submit claim → Upload raw X12 file** and select the `.edi`. The format is 837P `005010X222A1`. Keep test files in test mode (`ISA15=T`). A production file uses `P` and can be sent to the payer when you submit it. A valid local file is not proof of Stedi or payer acceptance: inspect Stedi's edits and later acknowledgments. No live Stedi submission or payer acceptance test has been performed for this program.

For a paid-claim correction, preserve the original payment record and reconcile any replacement payment/recovery in TheraNest. This converter only creates the claim file.

## Verification and maintenance

Automated tests cover the 837 envelope and counts, reference and modifier placement, dependents, multiple lines and dates, zero preservation, correction requirements, charge totals, NPI checks, unsupported-field blocking, saved/displayed field mismatches, overlays, appearance refresh, and output snapshots. The synthetic demo imports into the macOS GUI; it cannot produce a production file. The actual supplied sample is rejected until its appearance mismatch is refreshed, then remains ineligible for a claim export because required patient fields were removed.

The synthetic PDF is a test field sheet with matching field names, not a CMS-1500 billing form. It contains fictional data only. The provided original PDF and its patient-bearing appearances are not included in the app package.

Developer commands:

```text
python3 -m unittest discover -s tests -v
python3 converter.py edited.pdf --config settings.json
python3 converter.py edited.pdf --config settings.json --output exports --reviewed
```

CLI defaults to test mode. `--production` explicitly changes the mode. PDF refresh and field editing are available in the CLI; refresh is also available in the desktop UI. The app needs no internet connection. For maintenance, the source code and tests are included; pypdf 6.10.0 is vendored with its license.

## Sources

- [Stedi professional claims and X12 requirements](https://www.stedi.com/docs/healthcare/submit-professional-claims)
- [Stedi raw X12 upload](https://www.stedi.com/docs/providers/providers-submit-claims)
- [Stedi correction codes and claim identifiers](https://www.stedi.com/docs/healthcare/resubmit-cancel-claims)
- [UHC complete replacement-claim guidance](https://www.uhcprovider.com/en/resource-library/news/2025/avoid-claim-rejections-denials.html)
- [X12 patient-paid amount interpretation](https://x12.org/resources/requests-for-interpretation/rfi-1634-use-patient-amount-paid)
