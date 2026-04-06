# ANAF Parsers

Parsers for Romanian public finance data from [ANAF](https://www.anaf.ro) and [MFP](https://mfinante.gov.ro). Outputs structured JSON from PDFs, HTML pages and Excel files.

Data is updated weekly via GitHub Actions and published on the [`data`](https://github.com/opencbsoft/anaf-parsers/tree/data) branch.

## Data links

All files are zip-compressed JSON.

### IBAN Treasury Accounts

Source: [ANAF - Coduri IBAN](https://www.anaf.ro/anaf/internet/ANAF/asistenta_contribuabili/plata_oblig_fiscale/coduri_iban)

| File | Description |
|------|-------------|
| [`iban.json.zip`](https://github.com/opencbsoft/anaf-parsers/blob/data/iban/iban.json.zip) | IBAN accounts grouped by county (sursa A, B, C, D, H, I, J) |
| [`iban_institutii_publice.json.zip`](https://github.com/opencbsoft/anaf-parsers/blob/data/iban/iban_institutii_publice.json.zip) | Public institution IBAN accounts (sursa E, F, G) |

Each account includes: `iban`, `cont`, `capitol`, `subcapitol`, `denumire`, `sursa_finantare`, `data_publicarii`. Each treasury includes matched locality data from [localapi.ro](https://address.localapi.ro).

### Fiscal Obligations Calendar

Source: [ANAF - Calendar obligatii fiscale](https://www.anaf.ro/anaf/internet/ANAF/asistenta_contribuabili/info_obligatii_fiscale/calendar_obligatii_fiscale/)

| File | Description |
|------|-------------|
| [`calendar_2026.json.zip`](https://github.com/opencbsoft/anaf-parsers/blob/data/calendar/calendar_2026.json.zip) | Fiscal obligations calendar |

Each obligation includes: `termen`, `data` (ISO date when available), `obligatie`, `formulare` (form codes + URLs), `contribuabili`, `tip_contribuabil` (tags: PF, PJ, PI, IP, angajator, nerezident, accize, operator), `baza_legala`.

### Budget Classifications

Source: [MFP - Clasificatiile bugetare](https://mfinante.gov.ro/domenii/bugetul-de-stat/clasificatiile-bugetare)

| File | Description |
|------|-------------|
| [`clasificatie_indicatori_2026.json.zip`](https://github.com/opencbsoft/anaf-parsers/blob/data/clasificatii/clasificatie_indicatori_2026.json.zip) | Clasificatia indicatorilor privind finantele publice (Anexa I) |
| [`clasificatie_economica_2026.json.zip`](https://github.com/opencbsoft/anaf-parsers/blob/data/clasificatii/clasificatie_economica_2026.json.zip) | Clasificatia economica a cheltuielilor (Anexa I economica) |
| [`clasificatie_departamentala_2026.json.zip`](https://github.com/opencbsoft/anaf-parsers/blob/data/clasificatii/clasificatie_departamentala_2026.json.zip) | Clasificatia in profil departamental (Anexa II) |
| [`clasificatie_departamentala_venituri_proprii_2026.json.zip`](https://github.com/opencbsoft/anaf-parsers/blob/data/clasificatii/clasificatie_departamentala_venituri_proprii_2026.json.zip) | Clasificatia departamentala - venituri proprii (Anexa III) |
| [`clasificatie_buget_stat_2026.json.zip`](https://github.com/opencbsoft/anaf-parsers/blob/data/clasificatii/clasificatie_buget_stat_2026.json.zip) | Clasificatia indicatorilor privind bugetul de stat (Anexa 1) |
| [`clasificatie_bugete_locale_2026.json.zip`](https://github.com/opencbsoft/anaf-parsers/blob/data/clasificatii/clasificatie_bugete_locale_2026.json.zip) | Clasificatia indicatorilor privind bugetele locale (Anexa 2) |
| [`clasificatie_asigurari_sociale_2026.json.zip`](https://github.com/opencbsoft/anaf-parsers/blob/data/clasificatii/clasificatie_asigurari_sociale_2026.json.zip) | Bugetul asigurarilor sociale de stat (Anexa 3) |
| [`clasificatie_somaj_2026.json.zip`](https://github.com/opencbsoft/anaf-parsers/blob/data/clasificatii/clasificatie_somaj_2026.json.zip) | Bugetul asigurarilor pentru somaj (Anexa 4) |
| [`clasificatie_sanatate_2026.json.zip`](https://github.com/opencbsoft/anaf-parsers/blob/data/clasificatii/clasificatie_sanatate_2026.json.zip) | Bugetul FNUASS (Anexa 5) |
| [`clasificatie_credite_externe_2026.json.zip`](https://github.com/opencbsoft/anaf-parsers/blob/data/clasificatii/clasificatie_credite_externe_2026.json.zip) | Venituri si cheltuieli din credite externe (Anexa 6) |
| [`clasificatie_credite_interne_2026.json.zip`](https://github.com/opencbsoft/anaf-parsers/blob/data/clasificatii/clasificatie_credite_interne_2026.json.zip) | Venituri si cheltuieli din credite interne (Anexa 7) |
| [`clasificatie_fonduri_externe_2026.json.zip`](https://github.com/opencbsoft/anaf-parsers/blob/data/clasificatii/clasificatie_fonduri_externe_2026.json.zip) | Bugetul fondurilor externe nerambursabile (Anexa 8) |
| [`clasificatie_trezorerie_2026.json.zip`](https://github.com/opencbsoft/anaf-parsers/blob/data/clasificatii/clasificatie_trezorerie_2026.json.zip) | Bugetul trezoreriei statului (Anexa 9) |
| [`clasificatie_institutii_publice_2026.json.zip`](https://github.com/opencbsoft/anaf-parsers/blob/data/clasificatii/clasificatie_institutii_publice_2026.json.zip) | Bugetul institutiilor publice (Anexa 10) |

Each classification entry includes: `cod`, `capitol`, `subcapitol`, `paragraf`, `denumire`.

## Running locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Requires pdftotext (poppler-utils) for IBAN parser
# macOS: brew install poppler
# Ubuntu: apt install poppler-utils

python main.py iban
python main.py calendar
python main.py clasificatii
```

Output goes to `output/<parser>/`.

## Adding a new parser

1. Create `parsers/<name>/parser.py` with a class extending `BaseParser`
2. Set `name = "<name>"` and implement `run()`
3. Register it in `main.py` PARSERS dict
4. Add the parser name to the workflow's default list
