"""Read-only discovery of the official IRCC form/checklist index.

Discovery != mapped != generated != independently validated. This module
does not download applicant documents, store form PDFs, or make a form usable.
"""
from datetime import date
from html.parser import HTMLParser
import hashlib
import json
import re
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

INDEX_URL = "https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides.html"
GOVERNMENT_HOSTS = frozenset(("www.canada.ca", "canada.ca", "ircc.canada.ca", "www.ircc.canada.ca"))
MAX_INDEX_BYTES = 6_000_000
CODE_RE = re.compile(r"^[A-Z]{2,5}\s+\d{4}(?:\s+[A-Z0-9]+){0,2}$")
MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


class CatalogError(ValueError):
    pass


def verified_source_url(href: str) -> str:
    """Reject unsupported schemes, hosts, misleading hostnames and credentials."""
    target = urljoin(INDEX_URL, href.strip())
    parts = urlsplit(target)
    if (parts.scheme != "https" or parts.hostname not in GOVERNMENT_HOSTS or
            parts.username or parts.password or not parts.path or parts.fragment):
        raise CatalogError("Catalog links must use an approved HTTPS government host")
    return target


class _IndexTableParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self.depth = 0
        self.rows = []
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            if self.depth == 0:
                self.rows = []
            self.depth += 1
        if not self.depth:
            return
        if tag == "tr" and self.row is None:
            self.row = []
        elif tag in ("td", "th") and self.row is not None and self.cell is None:
            self.cell = {"text": [], "href": None}
        elif tag == "a" and self.cell is not None:
            link = dict(attrs).get("href")
            if link and self.cell["href"] is None:
                self.cell["href"] = link

    def handle_data(self, data):
        if self.cell is not None:
            self.cell["text"].append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None and self.row is not None:
            normalized = " ".join("".join(self.cell["text"]).split())
            self.row.append((normalized, self.cell["href"]))
            self.cell = None
        elif tag == "tr" and self.row is not None and self.depth == 1:
            if self.row:
                self.rows.append(self.row)
            self.row = None
        elif tag == "table" and self.depth:
            self.depth -= 1
            if self.depth == 0:
                self.tables.append(self.rows)
                self.rows = []


def parse_ircc_index(html: str) -> list[dict]:
    """Extract dated rows from the actual form-number table, not navigation links."""
    parser = _IndexTableParser()
    parser.feed(html)
    candidates = []
    for rows in parser.tables:
        if not rows:
            continue
        header = [cell[0].casefold() for cell in rows[0]]
        if (len(header) >= 3 and "form number" in header[0] and
                "form title" in header[1] and "date modified" in header[2]):
            candidates.append(rows[1:])
    if len(candidates) != 1:
        raise CatalogError("Expected exactly one official IRCC form-index table")
    discovered = {}
    for row in candidates[0]:
        if len(row) < 3:
            raise CatalogError("Unexpected short form-index row")
        code, title, modified = row[0][0], row[1][0], row[2][0]
        if not CODE_RE.fullmatch(code) or not title or not MONTH_RE.fullmatch(modified):
            raise CatalogError("Invalid form code, title or modification date in official index")
        try:
            date.fromisoformat(modified + "-01")
        except ValueError:
            raise CatalogError("Invalid modification month in official form index") from None
        if not row[1][1]:
            raise CatalogError("Missing government source URL in IRCC index")
        source_url = verified_source_url(row[1][1])
        record = {
            "code": code, "title": title, "modified_month": modified,
            "source_url": source_url,
            "category": ("checklist" if "checklist" in title.casefold() else "form_or_instruction"),
            "catalog_status": "discovered_unreviewed",
            "field_mapping_supported": False,
            "official_pdf_generation_supported": False,
            "independently_validated": False,
        }
        if code in discovered:
            raise CatalogError("Duplicate form number in IRCC index: " + code)
        discovered[code] = record
    if not discovered:
        raise CatalogError("IRCC index contained no forms")
    return sorted(discovered.values(), key=lambda item: item["code"])


def snapshot_document(records: list[dict], observation_date: str) -> dict:
    parsed = date.fromisoformat(observation_date)
    if parsed.isoformat() != observation_date or not records:
        raise CatalogError("Valid observation date and nonempty catalog required")
    payload = json.dumps(records, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return {
        "source": INDEX_URL, "observed_on": observation_date,
        "catalog_entries": len(records),
        "source_table_sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        "scope": "official_IRCC_index_discovery_only",
        "review_state": "unreviewed",
        "generated_or_validated_form_count": 0,
        "records": records,
    }


def fetch_official_catalog(timeout_seconds: int = 25) -> tuple[list[dict], int]:
    """A single allowlisted government fetch. Never accepts a user-supplied URL."""
    request = Request(INDEX_URL, headers={
        "User-Agent": "ImmigrationOS-FormCatalogResearch/0.1 (+manual-review; no applicant data)",
        "Accept": "text/html",
    })
    with urlopen(request, timeout=timeout_seconds) as response:
        verified_source_url(response.geturl())
        content_type = response.headers.get_content_type()
        if content_type != "text/html":
            raise CatalogError("Unexpected official index content type")
        data = response.read(MAX_INDEX_BYTES + 1)
    if len(data) > MAX_INDEX_BYTES:
        raise CatalogError("Official form index exceeded size limit")
    return parse_ircc_index(data.decode("utf-8")), len(data)
