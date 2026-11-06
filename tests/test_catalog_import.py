from datetime import date
import pytest

from app.catalog_import import (CatalogError, INDEX_URL, parse_ircc_index,
                                snapshot_document, verified_source_url)


FIXTURE = """<html><table><tr><th>Other</th></tr><tr><td>irrelevant</td></tr></table>
<table><thead><tr><th>Form number</th><th>Form title</th><th>Date modified</th></tr></thead>
<tbody><tr><td>IMM 0008</td><td><a href="/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm0008.html">Generic Application Form for Canada</a></td><td>2026-11</td></tr>
<tr><td>IMM 0008 SCH2</td><td><a href="https://www.canada.ca/en/immigration-refugees-citizenship/services/application/schedule2.html">Schedule 2: Refugees Outside Canada</a></td><td>2024-11</td></tr>
<tr><td>CIT 0002</td><td><a href="https://ircc.canada.ca/cit/cit0002.html">Citizenship — Adults</a></td><td>2026-02</td></tr></tbody></table></html>"""


def test_discovers_only_official_form_table_and_preserves_variants():
    rows = parse_ircc_index(FIXTURE)
    assert len(rows) == 3
    assert [x["code"] for x in rows] == ["CIT 0002", "IMM 0008", "IMM 0008 SCH2"]
    assert rows[1]["modified_month"] == "2026-11"
    assert rows[0]["source_url"].startswith("https://ircc.canada.ca/")
    assert all(not r["official_pdf_generation_supported"] for r in rows)
    assert all(not r["field_mapping_supported"] for r in rows)
    snap = snapshot_document(rows, "2026-11-06")
    assert snap["catalog_entries"] == 3
    assert snap["generated_or_validated_form_count"] == 0
    assert len(snap["source_table_sha256"]) == 64


@pytest.mark.parametrize("link", [
    "http://www.canada.ca/forms/imm0008.html",
    "https://www.canada.ca.attacker.example/forms.pdf",
    "https://example.com/imm0008.pdf",
    "javascript:alert(1)",
    "https://user:pass@www.canada.ca/forms.pdf",
])
def test_rejects_untrusted_form_links(link):
    with pytest.raises(CatalogError):
        verified_source_url(link)


def test_never_silently_accepts_missing_or_changed_table():
    with pytest.raises(CatalogError):
        parse_ircc_index("<html><table><tr><th>Forms</th></tr></table></html>")
    with pytest.raises(CatalogError):
        parse_ircc_index(FIXTURE + FIXTURE)


def test_duplicate_form_id_fails_closed():
    repeated = FIXTURE.replace("</tbody>", """<tr><td>IMM 0008</td>
       <td><a href="https://www.canada.ca/imm8b.html">Duplicate</a></td><td>2026-11</td></tr>
       </tbody>""")
    with pytest.raises(CatalogError, match="Duplicate"):
        parse_ircc_index(repeated)


def test_malformed_modified_date_fails_closed():
    with pytest.raises(CatalogError):
        parse_ircc_index(FIXTURE.replace("2026-11</td>", "2026-13</td>", 1))
    with pytest.raises(ValueError):
        snapshot_document(parse_ircc_index(FIXTURE), "tomorrow")


def test_checklist_kind_and_no_automatic_approval():
    source = FIXTURE.replace("Generic Application Form for Canada", "Document Checklist: Visitor")
    rows = parse_ircc_index(source)
    assert any(x["category"] == "checklist" for x in rows)
    assert all(not x["independently_validated"] for x in rows)
