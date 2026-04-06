import re
import shutil

import requests
from bs4 import BeautifulSoup

from parsers.base import BaseParser

ANAF_PAGE_URL = (
    "https://www.anaf.ro/anaf/internet/ANAF/"
    "asistenta_contribuabili/info_obligatii_fiscale/calendar_obligatii_fiscale/"
)
CALENDAR_URL_PREFIX = (
    "https://static.anaf.ro/static/10/Anaf/AsistentaContribuabili_r/Calendar/"
)

# Map spaced month names to canonical form
MONTH_NAMES = {
    "IANUARIE": "ianuarie",
    "FEBRUARIE": "februarie",
    "MARTIE": "martie",
    "APRILIE": "aprilie",
    "MAI": "mai",
    "IUNIE": "iunie",
    "IULIE": "iulie",
    "AUGUST": "august",
    "SEPTEMBRIE": "septembrie",
    "OCTOMBRIE": "octombrie",
    "NOIEMBRIE": "noiembrie",
    "DECEMBRIE": "decembrie",
}

MONTH_NUMBERS = {
    "ianuarie": 1, "februarie": 2, "martie": 3, "aprilie": 4,
    "mai": 5, "iunie": 6, "iulie": 7, "august": 8,
    "septembrie": 9, "octombrie": 10, "noiembrie": 11, "decembrie": 12,
}


class CalendarParser(BaseParser):
    name = "calendar"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0 (anaf-parser)"})

    def run(self):
        self._archive_old_output()

        print("Fetching ANAF calendar page...")
        calendar_url, year = self._find_calendar_url()
        print(f"  Found calendar for {year}: {calendar_url}")

        print("Parsing calendar...")
        soup = self._fetch_html(calendar_url)

        # The URL year may differ from the actual content year; trust the page title
        title = soup.find("title")
        if title:
            m = re.search(r"(\d{4})", title.get_text())
            if m:
                year = int(m.group(1))

        months = self._parse_calendar(soup, year)

        output = {"an": year, "luni": months}
        self.save_json(output, f"calendar_{year}.json")

        total = sum(len(m["obligatii"]) for m in months)
        print(f"\nDone! {len(months)} months, {total} obligations.")

    def _archive_old_output(self):
        if not self.output_dir.exists():
            return
        has_files = any(p for p in self.output_dir.iterdir() if p.name != "old")
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

    def _find_calendar_url(self):
        """Find the current year's calendar HTM URL from the ANAF page."""
        resp = self.session.get(ANAF_PAGE_URL)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        for link in soup.find_all("a", href=True):
            href = link["href"]
            m = re.search(r"Calendar_obligatii_fiscale_(\d{4})\.htm", href)
            if m:
                year = int(m.group(1))
                url = href if href.startswith("http") else CALENDAR_URL_PREFIX + href.split("/")[-1]
                return url, year

        raise RuntimeError("Could not find calendar URL on ANAF page")

    def _fetch_html(self, url):
        resp = self.session.get(url)
        resp.raise_for_status()
        resp.encoding = "utf-8"
        return BeautifulSoup(resp.text, "lxml")

    def _parse_calendar(self, soup, year):
        """Parse the calendar HTML into structured month data."""
        months = []

        # Each month is an accordion header followed by a panel div with a table
        for header in soup.find_all("p", class_="stilTitluri"):
            # Month name is spaced out: "I A N U A R I E"
            raw_name = header.get_text(strip=True)
            month_name = self._normalize_month(raw_name)
            if not month_name:
                continue

            # The table is in the next sibling div.panel
            panel = header.find_next_sibling("div", class_="panel")
            if not panel:
                continue

            table = panel.find("table")
            if not table:
                continue

            obligations = self._parse_month_table(table, year)
            months.append({"luna": month_name, "obligatii": obligations})

        return months

    @staticmethod
    def _normalize_month(spaced_name):
        """Convert 'I A N U A R I E' to 'ianuarie'."""
        collapsed = spaced_name.replace(" ", "").upper()
        return MONTH_NAMES.get(collapsed, "")

    def _parse_month_table(self, table, year):
        """Parse a month's table rows into obligation dicts."""
        obligations = []

        for row in table.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) < 4:
                continue
            # Skip header rows
            if cells[0].get("class") and "capTabel" in cells[0].get("class", []):
                continue

            termen = cells[0].get_text(strip=True)
            obligatie_html = cells[1]
            contribuabili = cells[2].get_text(" ", strip=True)
            baza_legala = cells[3].get_text(" ", strip=True)

            # Extract forms from the obligation cell
            formulare = self._extract_forms(obligatie_html)
            obligatie_text = obligatie_html.get_text(" ", strip=True)

            obligations.append(
                {
                    "termen": termen,
                    "data": self._extract_date(termen, year),
                    "obligatie": obligatie_text,
                    "formulare": formulare,
                    "contribuabili": contribuabili,
                    "baza_legala": baza_legala,
                }
            )

        return obligations

    @staticmethod
    def _extract_date(termen, year):
        """Try to extract a YYYY-MM-DD date from a termen string.

        Only matches when the termen starts with a day-of-week name
        followed by the date, e.g. 'luni 12 ianuarie'.
        Returns empty string if no date can be extracted.
        """
        m = re.match(
            r"(?:luni|marți|marţi|miercuri|joi|vineri|sâmbătă|sâmbata|"
            r"duminică|duminica)\s+(\d{1,2})\s+"
            r"(ianuarie|februarie|martie|aprilie|mai|iunie"
            r"|iulie|august|septembrie|octombrie|noiembrie|decembrie)",
            termen.lower().strip(),
        )
        if not m:
            return ""
        day = int(m.group(1))
        month = MONTH_NUMBERS.get(m.group(2), 0)
        if not month:
            return ""
        return f"{year}-{month:02d}-{day:02d}"

    @staticmethod
    def _extract_forms(cell):
        """Extract form references (code, name, URL) from an obligation cell."""
        forms = []
        for link in cell.find_all("a", href=True):
            url = link["href"]
            text = link.get_text(strip=True)

            # Try to extract form code from text like "Formularul 010" or "Formularul electronic 700"
            m = re.search(r"Formularul\s+(?:electronic\s+)?(\w+)", text)
            cod = m.group(1) if m else ""

            forms.append({"cod": cod, "denumire": text, "url": url})
        return forms
