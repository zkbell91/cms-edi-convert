# Terminal usage

The desktop app and CLI read the same persistent settings file. On this Mac it is:

```text
~/.config/cms-edi-convert/settings.json
```

## One command to convert

```sh
cms-edi-convert ~/Downloads/cms1500.pdf ~/Downloads/cms1500.edi
```

That validates the PDF, prints the extracted review, and saves the exact destination you named. It does not submit anything. Test mode is the default (`ISA15=T`). For a production file:

```sh
cms-edi-convert ~/Downloads/cms1500.pdf ~/Downloads/cms1500.edi --production
```

Files with spaces should be quoted. Existing outputs are protected; use a new name or explicitly add `--force` to overwrite. Missing destination directories are created. Errors return a nonzero exit status and prevent creation of an EDI file. The CLI does not require an interactive review checkbox; inspect its review yourself before uploading a production file.

By default, `cms1500.review.txt` and `cms1500.claim.json` are saved beside `cms1500.edi`. The JSON records the outgoing claim identifier and original account/reference mapping. `--no-sidecars` opts out. `--quiet` prints only the output path on success; errors still go to stderr.

## Inspect before generating

```sh
cms-edi-convert review ~/Downloads/cms1500.pdf
cms-edi-convert review ~/Downloads/cms1500.pdf --json
cms-edi-convert fields ~/Downloads/cms1500.pdf --all
cms-edi-convert fields ~/Downloads/cms1500.pdf --all --json
```

`review` runs claim validation. `fields` lists stored form fields even when their old appearances disagree. It does not recover or print appearance-only text. Do not treat its raw listing as a validated claim.

## Edit the PDF from Terminal

Edit any existing form field and save a separate fillable PDF:

```sh
cms-edi-convert edit ~/Downloads/original.pdf ~/Downloads/corrected.pdf \
  --set code22=7 \
  --set 22ref=000PAYERCLAIMNUMBER \
  --set 24dcpt-1=90834 \
  --set 24fdol-1=100 \
  --set 24fcent-1=00 \
  --set dol28=100 \
  --set cent28=00
```

These values are examples, not a billing recommendation. Use the actual reference and charge. Other names can be found using `fields --all`. Repeat `--set` for as many fields as you need. `--set FIELD=` clears a text field. For checkboxes, use `true` or `false`; when changing a selection, clear the old checkbox too.

| Form item | Field name |
|---|---|
| Payer heading | `cname` |
| Member ID | `1a` |
| Patient name | `two` |
| Patient birth month/day/year | `3mm`, `3dd`, `3yy` |
| Patient sex | `sexm`, `sexf` |
| Insured name | `four` |
| Relationship | `self6`, `spouse6`, `child6`, `other6` |
| Insured birth month/day/year | `mm11a`, `dd11a`, `yy11a` |
| Correction code / original payer reference | `code22`, `22ref` |
| Diagnoses A-L | `diag21.1` through `diag21.12` |
| Source patient/account number | `pat26` |
| Service code, first line | `24dcpt-1` |
| First-line modifiers | `24dmod-1`, `24dfer-1`, `24dfera-1`, `24dferb-1` |
| First-line date from | `24amm-1`, `24add-1`, `24ayy-1` |
| First-line date to | `24atomm-1`, `24atodd-1`, `24atoyy-1` |
| First-line place/diagnosis pointer/units | `24b-1`, `24e-1`, `24g-1` |
| First-line charge | `24fdol-1`, `24fcent-1` |
| First-line rendering NPI | `24j-1-1` |
| Claim total | `dol28`, `cent28` |
| Actual patient paid | `dol29`, `cent29` |
| Billing NPI | `grp33a.1` |
| Federal tax ID | `taxid26` |

Change the final line suffix from `-1` to `-2` … `-6` for subsequent service lines. Preserve identifiers as text.

For larger edits, create a JSON object and supply `--fields-json edits.json`. Text field values must be JSON strings, including dates, amounts and IDs; checkbox values may be booleans. Direct `--set` entries override the JSON file. Unknown fields fail rather than being added silently. The original PDF is preserved and an existing destination is not overwritten.

To refresh appearances without changing stored values:

```sh
cms-edi-convert refresh ~/Downloads/input.pdf ~/Downloads/refreshed.pdf
```

Inspect the resulting PDF. A displayed-only change that was never stored in a form field cannot be recovered by this operation. The same template and claim-scope limitations apply in both interfaces.

## Manage every setting from the CLI

```sh
cms-edi-convert settings path
cms-edi-convert settings show
cms-edi-convert settings set /submitter/name "Your Practice LLC"
cms-edi-convert settings set /submitter/contact "Billing Office"
cms-edi-convert settings set /submitter/phone 9045550100
cms-edi-convert settings set /billing_taxonomy YOUR_TAXONOMY
```

The generic `set` and `unset` commands support every configuration key. Use a JSON Pointer beginning with `/`, or a simple dotted path such as `submitter.name`. JSON Pointer supports names containing dots; escape a literal slash with `~1` and a tilde with `~0`.

Values are strings by default, so `00590` stays `00590`. To set booleans or entire objects, add `--json`:

```sh
cms-edi-convert settings set '/payers/BCBS FL (Florida)/id' 'VERIFIED_STEDI_ID'
cms-edi-convert settings set '/payers/BCBS FL (Florida)/confirmed' true --json
cms-edi-convert settings unset '/payers/OLD PAYER NAME'
```

Changing a payer ID with `set` clears its previous verification flag. Confirm the new ID before marking it verified. Convenient commands also exist:

```sh
cms-edi-convert settings payer 'PAYER NAME AS PRINTED' 'VERIFIED_STEDI_ID' --filing BL --verified
cms-edi-convert settings provider 'PROVIDER_NPI' --first 'FIRST' --last 'LAST' --taxonomy 'TAXONOMY'
```

Replace example placeholders with real values. `--verified` records your verification of the professional-claims route in Stedi's directory. Provider taxonomy is optional. The payer filing code must fit the actual plan; the available codes are not payer-specific recommendations.

To edit the full configuration in your preferred Terminal editor:

```sh
EDITOR=nano cms-edi-convert settings edit
```

The program restores the prior file if the edit is not valid JSON with an object at the root. Billing correctness is checked during conversion. The desktop app reads updated settings when you next choose a PDF or reopen Settings; an already-loaded claim must be reloaded after a settings change.

## Alternate settings and automation

```sh
cms-edi-convert input.pdf output.edi --config /path/to/settings.json
cms-edi-convert review input.pdf --config /path/to/settings.json
cms-edi-convert settings --config /path/to/settings.json show
```

Alternatively set `CMS_EDI_SETTINGS=/path/to/settings.json` for both interfaces. This is useful for isolated tests. Do not pass real patient information in command arguments on shared systems if you do not want it in shell history; a local edits JSON file can keep the values out of command history.

## Installation on another Mac or Linux computer

```sh
git clone git@github.com:zkbell91/cms-edi-convert.git
cd cms-edi-convert
python3 install_cli.py
```

It installs a private copy under `~/.local/share/cms-edi-convert` and a launcher at `~/.local/bin/cms-edi-convert`. If that bin directory is not in PATH, the installer tells you to add it (for zsh: `export PATH="$HOME/.local/bin:$PATH"`). It does not edit your shell startup files. Existing commands are not overwritten. Use `--update` for a later version of this program; shared settings are retained. A custom `--prefix` is available.

You can also run `./cms-edi-convert` directly from the cloned repo without installing. Windows has `cms-edi-convert.cmd`; the Unix installer is not intended for Windows. No administrator privileges, Stedi API key, or network connection is required for conversion.
