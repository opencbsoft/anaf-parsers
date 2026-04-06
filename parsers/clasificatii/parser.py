import re
import tempfile
import os

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup

from parsers.base import BaseParser

MFP_PAGE_URL = (
    "https://mfinante.gov.ro/domenii/bugetul-de-stat/clasificatiile-bugetare"
)
MFP_BASE_URL = "https://mfinante.gov.ro"

# Maps Anexa label patterns to output keys and descriptions
ANEXA_MAP = {
    "Anexa I (economica)": {
        "key": "clasificatie_economica",
        "description": "Clasificația economică a cheltuielilor",
    },
    "Anexa I": {
        "key": "clasificatie_indicatori",
        "description": "Clasificația indicatorilor privind finanțele publice",
    },
    "Anexa II": {
        "key": "clasificatie_departamentala",
        "description": "Clasificația în profil departamental",
    },
    "Anexa III": {
        "key": "clasificatie_departamentala_venituri_proprii",
        "description": "Clasificația departamentală - venituri proprii",
    },
    "Anexa 1": {
        "key": "clasificatie_buget_stat",
        "description": "Clasificația indicatorilor privind bugetul de stat",
    },
    "Anexa 2": {
        "key": "clasificatie_bugete_locale",
        "description": "Clasificația indicatorilor privind bugetele locale",
    },
    "Anexa 3": {
        "key": "clasificatie_asigurari_sociale",
        "description": "Clasificația indicatorilor privind bugetul asigurărilor sociale de stat",
    },
    "Anexa 4": {
        "key": "clasificatie_somaj",
        "description": "Clasificația indicatorilor privind bugetul asigurărilor pentru șomaj",
    },
    "Anexa 5": {
        "key": "clasificatie_sanatate",
        "description": "Clasificația indicatorilor privind bugetul FNUASS",
    },
    "Anexa 6": {
        "key": "clasificatie_credite_externe",
        "description": "Clasificația veniturilor și cheltuielilor din credite externe",
    },
    "Anexa 7": {
        "key": "clasificatie_credite_interne",
        "description": "Clasificația veniturilor și cheltuielilor din credite interne",
    },
    "Anexa 8": {
        "key": "clasificatie_fonduri_externe",
        "description": "Clasificația indicatorilor privind bugetul fondurilor externe nerambursabile",
    },
    "Anexa 9": {
        "key": "clasificatie_trezorerie",
        "description": "Clasificația indicatorilor privind bugetul trezoreriei statului",
    },
    "Anexa 10": {
        "key": "clasificatie_institutii_publice",
        "description": "Clasificația indicatorilor privind bugetul instituțiilor publice",
    },
}


class ClasificatiiParser(BaseParser):
    name = "clasificatii"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
        )
        retry = Retry(total=5, backoff_factor=2, status_forcelist=[500, 502, 503, 504])
        self.session.mount("https://", HTTPAdapter(max_retries=retry))

    def run(self):
        print("Fetching MFP budget classifications page...")
        file_map = self._fetch_page_links()

        year = self._detect_year(file_map)
        print(f"  Detected year: {year}")

        for anexa_label, info in ANEXA_MAP.items():
            if anexa_label not in file_map:
                print(f"\n  SKIP {anexa_label} (not found on page)")
                continue

            url = file_map[anexa_label]
            print(f"\n=== {anexa_label}: {info['description']} ===")
            print(f"  Downloading {url.split('/')[-1]}...")

            sheets = self._download_and_parse_xls(url)
            if not sheets:
                continue

            output = {
                "an": year,
                "anexa": anexa_label,
                "descriere": info["description"],
                "url_sursa": url,
                "clasificatii": sheets,
            }

            self.save_json(output, f"{info['key']}_{year}.json")

        print("\nDone!")

    def _fetch_page_links(self):
        """Parse the MFP page and return {label: url} for classification XLS files."""
        resp = self.session.get(MFP_PAGE_URL, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        file_map = {}
        for link in soup.find_all("a", href=True):
            href = link["href"]
            text = link.get_text(strip=True)
            if not any(ext in href.lower() for ext in [".xls", ".xlsx"]):
                continue
            if "clasificatii" not in href.lower():
                continue

            if not href.startswith("http"):
                href = MFP_BASE_URL + href

            # Match to known Anexa labels (prefer exact match, longest first)
            for label in sorted(ANEXA_MAP.keys(), key=len, reverse=True):
                if text == label or text.startswith(label):
                    if label not in file_map:
                        file_map[label] = href
                    break

        return file_map

    @staticmethod
    def _detect_year(file_map):
        """Extract year from the first available URL filename."""
        for url in file_map.values():
            m = re.search(r"(\d{4})\.(xls|xlsx)", url, re.IGNORECASE)
            if m:
                return int(m.group(1)[:4])
            m = re.search(r"_(\d{8})\.", url)
            if m:
                return int(m.group(1)[-4:])
        return 0

    def _download_and_parse_xls(self, url):
        """Download an XLS/XLSX file and parse all sheets into structured data."""
        try:
            resp = self.session.get(url, timeout=60)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"    ERROR downloading: {e}")
            return []

        suffix = ".xlsx" if url.lower().endswith(".xlsx") else ".xls"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(resp.content)
            tmp_path = tmp.name

        try:
            if suffix == ".xlsx":
                return self._parse_xlsx(tmp_path)
            else:
                return self._parse_xls(tmp_path)
        finally:
            os.unlink(tmp_path)

    def _parse_xlsx(self, path):
        import openpyxl

        wb = openpyxl.load_workbook(path, read_only=True)
        sheets = []
        for name in wb.sheetnames:
            ws = wb[name]
            rows = list(ws.iter_rows(values_only=True))
            entries = self._parse_rows(rows)
            if entries:
                sheets.append({"sheet": name, "indicatori": entries})
                print(f"    {name}: {len(entries)} entries")
        return sheets

    def _parse_xls(self, path):
        import xlrd

        wb = xlrd.open_workbook(path)
        sheets = []
        for name in wb.sheet_names():
            ws = wb.sheet_by_name(name)
            rows = []
            for i in range(ws.nrows):
                rows.append(tuple(ws.cell_value(i, j) for j in range(ws.ncols)))
            entries = self._parse_rows(rows)
            if entries:
                sheets.append({"sheet": name, "indicatori": entries})
                print(f"    {name}: {len(entries)} entries")
        return sheets

    @staticmethod
    def _parse_rows(rows):
        """Parse rows into a flat list of classification entries.

        Each row has columns like: code_col1 | code_col2 | code_col3 | description
        Codes look like: '01.00', '01.00.01', '10', '10.01', '10.01.01', etc.
        """
        entries = []
        header_row = None

        for row in rows:
            cells = [str(v).strip() if v is not None else "" for v in row]

            # Detect header row
            if any(
                h in " ".join(cells).upper()
                for h in ["DENUMIREA INDICATORILOR", "DENUMIRE"]
            ):
                header_row = cells
                continue

            if not header_row:
                continue

            # Find the code and description
            code = ""
            description = ""

            for cell in cells:
                if not cell:
                    continue
                # Check if this looks like a budget code: digits with dots
                if re.match(r"^\d{1,2}(\.\d{2}){0,3}$", cell):
                    if not code:
                        code = cell
                    else:
                        code = cell  # take the most specific
                elif len(cell) > 3 and not code:
                    # Could be a combined code + description like "01.00 | text"
                    m = re.match(r"^(\d{1,2}(?:\.\d{2}){0,3})\s*$", cell)
                    if m:
                        code = m.group(1)

            # Description is usually the last non-empty cell (or the widest one)
            for cell in reversed(cells):
                if cell and len(cell) > 3 and not re.match(r"^\d", cell):
                    description = cell
                    break

            # Also check for rows where code is embedded in description
            if not code and description:
                m = re.match(
                    r"^(\d{1,2}(?:\.\d{2}){0,3})\s*[.\-\s]+\s*(.+)", description
                )
                if m:
                    code = m.group(1)
                    description = m.group(2).strip()

            # Skip empty or header-like rows
            if not description or description.upper().startswith("ANEXA"):
                continue

            # Parse code into components
            parts = code.split(".") if code else []
            capitol = parts[0] if len(parts) >= 1 and parts[0] else ""
            subcapitol = parts[1] if len(parts) >= 2 else ""
            paragraf = parts[2] if len(parts) >= 3 else ""

            entry = {
                "cod": code,
                "capitol": capitol,
                "subcapitol": subcapitol,
                "paragraf": paragraf,
                "denumire": description,
            }
            entries.append(entry)

        return entries
