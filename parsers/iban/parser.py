import os
import re
import shutil
import subprocess
import tempfile
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from parsers.base import BaseParser

ANAF_BASE_URL = (
    "https://static.anaf.ro/static/10/Anaf/AsistentaContribuabili_r/iban2014/"
)
ANAF_PAGE_URL = (
    "https://www.anaf.ro/anaf/internet/ANAF/"
    "asistenta_contribuabili/plata_oblig_fiscale/coduri_iban"
)
LOCALAPI_URL = "https://address.localapi.ro"

# Funding sources that belong to public institutions
PUBLIC_INSTITUTION_SOURCES = {"E", "F", "G"}

# HTM pages on the ANAF site that are budget chapter lists, not county pages
BUDGET_PAGES = {"bugetstat", "bugetlocal", "bass", "fnuass", "somaj"}

RO_DIACRITICS = {
    "ă": "a", "â": "a", "î": "i", "ș": "s", "ş": "s", "ț": "t", "ţ": "t",
    "Ă": "A", "Â": "A", "Î": "I", "Ș": "S", "Ş": "S", "Ț": "T", "Ţ": "T",
}


def normalize_ro(text):
    """Remove Romanian diacritics for comparison."""
    for old, new in RO_DIACRITICS.items():
        text = text.replace(old, new)
    return text


class IbanParser(BaseParser):
    name = "iban"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0 (anaf-parser)"})

    def run(self):
        self._archive_old_output()

        print("Fetching county data from localapi...")
        counties_meta = self._fetch_counties_meta()

        print("Fetching ANAF IBAN page...")
        county_entries = self._fetch_anaf_index()

        for entry in county_entries:
            county_name = entry["name"]
            print(f"\n=== {county_name} ===")

            meta = self._match_county(county_name, counties_meta)
            all_trezorerii = []

            for pdf_info in entry["pdfs"]:
                treasury_name, accounts = self._download_and_parse_pdf(
                    pdf_info["url"]
                )
                if not accounts:
                    continue
                all_trezorerii.append(
                    {
                        "cod": pdf_info["code"],
                        "denumire": treasury_name or pdf_info.get("name", ""),
                        "conturi": accounts,
                    }
                )

            # Split accounts into regular vs public institution
            regular_trez = []
            public_trez = []
            for trez in all_trezorerii:
                reg = [
                    a
                    for a in trez["conturi"]
                    if a["sursa_finantare"]["cod"] not in PUBLIC_INSTITUTION_SOURCES
                ]
                pub = [
                    a
                    for a in trez["conturi"]
                    if a["sursa_finantare"]["cod"] in PUBLIC_INSTITUTION_SOURCES
                ]
                if reg:
                    regular_trez.append({**trez, "conturi": reg})
                if pub:
                    public_trez.append({**trez, "conturi": pub})

            file_key = entry.get("file_key") or meta.get("auto", county_name[:2]).lower()

            self.save_json(
                {"judet": meta, "trezorerii": regular_trez}, f"{file_key}.json"
            )
            if public_trez:
                self.save_json(
                    {"judet": meta, "trezorerii": public_trez},
                    f"institutii_publice/{file_key}.json",
                )

        print("\nDone!")

    def _archive_old_output(self):
        """Move existing output to old/ subdirectory before a fresh run."""
        if not self.output_dir.exists():
            return
        # Check if there are any files to archive (exclude old/ itself)
        has_files = any(
            p for p in self.output_dir.iterdir() if p.name != "old"
        )
        if not has_files:
            return

        old_dir = self.output_dir / "old"
        if old_dir.exists():
            shutil.rmtree(old_dir)
        old_dir.mkdir(parents=True)

        for item in self.output_dir.iterdir():
            if item.name == "old":
                continue
            shutil.move(str(item), str(old_dir / item.name))
        print(f"Archived previous output to {old_dir}")

    # ------------------------------------------------------------------
    # Data fetching
    # ------------------------------------------------------------------

    def _fetch_counties_meta(self):
        resp = self.session.get(f"{LOCALAPI_URL}/judete/")
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else data.get("judete", data)

    def _match_county(self, anaf_name, counties_meta):
        norm = self._normalize_for_match(anaf_name)
        for county in counties_meta:
            if self._normalize_for_match(county["denumire"]) == norm:
                return county
        # Bucharest special case
        if "BUCURE" in norm:
            for county in counties_meta:
                if "BUCURE" in county["denumire"]:
                    return county
        return {
            "denumire": anaf_name,
            "cod_jud": "",
            "auto": anaf_name[:2].upper(),
            "siruta": "",
        }

    @staticmethod
    def _normalize_for_match(text):
        """Normalize county name for matching: remove diacritics, punctuation, case."""
        text = normalize_ro(text.strip()).upper()
        return re.sub(r"[^A-Z]", "", text)

    def _fetch_anaf_index(self):
        """Parse the ANAF IBAN page to discover county HTM pages and Bucharest PDFs."""
        resp = self.session.get(ANAF_PAGE_URL)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        county_entries = {}
        bucharest_pdfs = []

        for link in soup.find_all("a", href=True):
            href = link["href"]
            text = link.get_text(strip=True)

            if href.endswith(".htm") and "iban2014/" in href:
                filename = href.split("/")[-1].replace(".htm", "")
                if filename.lower() in BUDGET_PAGES:
                    continue
                county_name = self._county_name_from_link(text, filename)
                if county_name and county_name not in county_entries:
                    county_entries[county_name] = {
                        "name": county_name,
                        "htm_url": href,
                        "pdfs": [],
                    }

            elif href.endswith(".pdf") and "iban_TREZ000" in href:
                m = re.search(r"(TREZ\d+)\.pdf", href)
                if m:
                    bucharest_pdfs.append(
                        {"code": m.group(1), "name": " ".join(text.split()), "url": href}
                    )

        # Fetch PDF lists from each county HTM page
        for name, entry in county_entries.items():
            print(f"  Fetching treasury list for {name}...")
            entry["pdfs"] = self._fetch_county_pdfs(entry["htm_url"])

        # Bucharest: one entry per sector so each gets its own output file
        for pdf in bucharest_pdfs:
            code = pdf["code"]  # TREZ700..TREZ706
            sector_num = int(code.replace("TREZ", "")) - 700
            if sector_num == 0:
                key = "București"
                file_key = "b"
            else:
                key = f"București - Sector {sector_num}"
                file_key = f"b-s{sector_num}"
            county_entries[key] = {
                "name": key,
                "file_key": file_key,
                "pdfs": [pdf],
            }

        return list(county_entries.values())

    @staticmethod
    def _county_name_from_link(text, filename):
        """Derive a clean county name from anchor text or HTM filename."""
        if text:
            cleaned = re.sub(r"TREZ\d+\s*", "", text).strip(" -–—\t")
            # "Trezoreria" alone is generic (all links have it), use filename
            if cleaned and cleaned.lower() not in ("trezoreria", "trezorerie"):
                return cleaned
        return filename.replace("_", " ")

    def _fetch_county_pdfs(self, htm_url):
        """Parse a county HTM page and return a list of treasury PDF entries."""
        resp = self.session.get(htm_url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        pdfs = []
        for link in soup.find_all("a", href=True):
            href = link["href"]
            if not href.endswith(".pdf") or "iban_" not in href.lower():
                continue

            m = re.search(r"iban_(TREZ\d+)_(TREZ\d+)\.pdf", href, re.IGNORECASE)
            if not m:
                continue

            code = m.group(2)
            if not href.startswith("http"):
                href = urljoin(htm_url, href)

            name = " ".join(link.get_text(strip=True).split())
            pdfs.append({"code": code, "name": name, "url": href})

        return pdfs

    # ------------------------------------------------------------------
    # PDF downloading and parsing
    # ------------------------------------------------------------------

    def _download_and_parse_pdf(self, url):
        """Download a PDF and return (treasury_name, accounts)."""
        filename = url.split("/")[-1]
        print(f"  Parsing {filename}...")
        try:
            resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"    ERROR downloading {filename}: {e}")
            return "", []

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(resp.content)
            tmp_path = tmp.name

        try:
            result = subprocess.run(
                ["pdftotext", "-layout", tmp_path, "-"],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode != 0:
                print(f"    ERROR pdftotext: {result.stderr.strip()}")
                return "", []
            return self._parse_pdf_text(result.stdout)
        except subprocess.TimeoutExpired:
            print(f"    ERROR pdftotext timed out for {filename}")
            return "", []
        finally:
            os.unlink(tmp_path)

    @staticmethod
    def _parse_pdf_text(text):
        """Parse pdftotext -layout output into (treasury_name, [accounts])."""
        lines = text.split("\n")

        # Extract treasury name from the header (first few lines)
        treasury_name = ""
        for line in lines[:15]:
            stripped = line.strip()
            if re.match(r"Trezoreri[ea]", stripped):
                treasury_name = stripped
                break

        accounts = []
        current_sursa = {"cod": "", "denumire": ""}
        current_account = None

        sursa_re = re.compile(r"Sursa de finantare:\s+([A-Z])\s+(.*\S)")
        account_re = re.compile(
            r"(\d{2}-\d{2}-\d{2})\s+(RO\d{2}TREZ\S+)\s+(\S+)\s+(.*\S)"
        )
        skip_re = re.compile(
            r"^(Coduri IBAN|Trezoreri|Data publicarii|Pag\.\s+\d+|"
            r"\d{2}/\d{2}/\d{4}|Sursa de finantare)"
        )

        for line in lines:
            # Section header: funding source
            m = sursa_re.search(line)
            if m:
                if current_account:
                    accounts.append(current_account)
                    current_account = None
                current_sursa = {"cod": m.group(1), "denumire": m.group(2).strip()}
                continue

            # Account data line
            m = account_re.search(line)
            if m and not line.startswith(" " * 40):
                if current_account:
                    accounts.append(current_account)

                dd, mm, yy = m.group(1).split("-")
                year = 2000 + int(yy) if int(yy) < 50 else 1900 + int(yy)

                cont = m.group(3)
                # Extract capitol/subcapitol from account code:
                # format is 2 digits + sursa letter + 2-digit capitol
                #   + 2-digit subcapitol + rest
                # e.g. 21E150100 → capitol=15, subcapitol=01
                cap_m = re.match(r"\d{2}[A-Z](\d{2})(\d{2})", cont)
                capitol = cap_m.group(1) if cap_m else ""
                subcapitol = cap_m.group(2) if cap_m else ""

                current_account = {
                    "data_publicarii": f"{year:04d}-{mm}-{dd}",
                    "iban": m.group(2),
                    "cont": cont,
                    "capitol": capitol,
                    "subcapitol": subcapitol,
                    "denumire": m.group(4).strip(),
                    "sursa_finantare": current_sursa.copy(),
                }
                continue

            # Continuation line (heavily indented description text)
            stripped = line.strip()
            if current_account and stripped and line.startswith(" " * 30):
                if not skip_re.match(stripped):
                    current_account["denumire"] += " " + stripped

        if current_account:
            accounts.append(current_account)

        return treasury_name, accounts
