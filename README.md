# cms-edi-convert

Convert a fillable CMS-1500 PDF into an 837P (X12) claim file. Runs entirely on your computer.

## Install

```sh
git clone https://github.com/zkbell91/cms-edi-convert.git
cd cms-edi-convert
python3 install_cli.py
```

Requires **Python 3.10+**. The installer puts the command at `~/.local/bin/cms-edi-convert`. If that directory is not on your PATH:

```sh
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc && source ~/.zshrc
```

Update later with `python3 install_cli.py --update`.

Or run without installing: `./cms-edi-convert` from this folder. On Windows, use `Run Converter.bat` or `cms-edi-convert.cmd`.

## Convert

```sh
cms-edi-convert claim.pdf claim.edi
```

Writes only `claim.edi` and prints its path. Default is test mode (`ISA15=T`). For production:

```sh
cms-edi-convert claim.pdf claim.edi --production
```

Inspect without writing a file: `cms-edi-convert review claim.pdf`. More commands: [CLI_GUIDE.md](CLI_GUIDE.md).

## Desktop app

Double-click **Run Converter.command** (macOS) or **Run Converter.bat** (Windows). Set practice contact and rendering-provider names under Settings before converting real claims.

## What it does

- Reads fillable CMS-1500 form fields (not flattened scans or image-only PDFs)
- Builds a local 837P `005010X222A1` file
- Maps common commercial payer names on the form to standard payer IDs (see `builtin_payers.json`); override in Settings when needed
- Does not upload claims or send data anywhere

Practice settings live in `~/.config/cms-edi-convert/settings.json` (Windows: `%APPDATA%/CMS-EDI-Converter/settings.json`).

## Editing the PDF

Use the real interactive form fields. Keep the PDF fillable—do not flatten or use Print to PDF.

- Replacement: Box 22 = **7**, plus the payer’s original claim control number (not your internal account number)
- Birth years may be two digits on the form; they expand within the last 120 years (e.g. `61` → 1961). Confirm the full date in `review`
- Service years are two-digit `20xx`
- If stored field values disagree with what you see on screen, re-save in a form editor, or run `cms-edi-convert refresh in.pdf out.pdf` and inspect the new copy

## Supported claims (this version)

Primary commercial outpatient professional claims from the supported one-page fillable template: original / replacement / void, self and dependents, up to six lines and twelve diagnoses, common outpatient POS codes, one rendering provider.

Not supported: Medicare/Medicaid/TRICARE workflows, secondary/COB, accident/work-related, referring-provider loops, and other populated fields the converter lists as unsupported.

## Output

Upload the `.edi` through whatever clearinghouse or payer channel you use. A valid local file is not proof of payer acceptance.

## License / dependency

`pypdf` is vendored under `vendor/` with its license. No pip install required for ordinary use.
