"""Strictly gated STATIC AcroForm adapter — no official IRCC form is approved yet.

Some IRCC PDFs are XFA/JavaScript/barcode forms. Never silently flatten,
rewrite or "validate" those. Templates enter this adapter only after manual
field mapping, revision pinning, licensing review and independent validation.
"""
from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from typing import Mapping

from pypdf import PdfReader, PdfWriter
from pypdf.generic import DictionaryObject, NameObject


class PDFAdapterBlocked(ValueError):
    pass


@dataclass(frozen=True)
class StaticAcroFormApproval:
    form_code: str
    official_revision: str
    template_sha256: str
    approved_fields: frozenset[str]
    approved_for_static_fill: bool = False
    requires_barcode_validation: bool = True
    approval_record: str = ""

    def __post_init__(self):
        if (not self.form_code or not self.official_revision or
                len(self.template_sha256) != 64 or not self.approved_fields):
            raise PDFAdapterBlocked("A pinned revision, SHA-256 and mapping are required")


def _forbidden_dynamic_features(reader: PdfReader):
    root = reader.trailer["/Root"]
    if "/OpenAction" in root or "/AA" in root:
        raise PDFAdapterBlocked("Dynamic document actions are not supported")
    names = root.get("/Names")
    if names and "/JavaScript" in names.get_object():
        raise PDFAdapterBlocked("Embedded JavaScript is not supported")
    acro = root.get("/AcroForm")
    if acro is None:
        raise PDFAdapterBlocked("Template has no AcroForm fields")
    acro = acro.get_object()
    if "/XFA" in acro or "/AA" in acro:
        raise PDFAdapterBlocked("XFA/JavaScript form is not supported")
    for page in reader.pages:
        if "/AA" in page:
            raise PDFAdapterBlocked("Page actions are not supported")
        for annot_ref in page.get("/Annots", []):
            annot = annot_ref.get_object()
            if "/AA" in annot or "/A" in annot:
                raise PDFAdapterBlocked("Interactive annotation actions are not supported")


def fill_static_acroform(template_pdf: bytes, values: Mapping[str, str],
                         approval: StaticAcroFormApproval) -> bytes:
    """Fill strictly reviewed text fields; caller must supply human-verified data.

    This method does not assert that *any* IRCC template is presently supported.
    Does not flatten, sign, barcode-validate, submit, or claim official validity.
    """
    if not approval.approved_for_static_fill or approval.requires_barcode_validation:
        raise PDFAdapterBlocked("No approved static form adapter or barcode form is unsupported")
    if sha256(template_pdf).hexdigest() != approval.template_sha256:
        raise PDFAdapterBlocked("Form PDF revision/checksum mismatch")
    if not template_pdf.startswith(b"%PDF-") or len(template_pdf) > 15_000_000:
        raise PDFAdapterBlocked("Invalid or oversized PDF template")
    if not values or set(values) != set(approval.approved_fields):
        raise PDFAdapterBlocked("Only the exact reviewed field mapping may be populated")
    if any(not isinstance(v, str) or len(v) > 1000 for v in values.values()):
        raise PDFAdapterBlocked("Invalid field value type/length")
    try:
        reader = PdfReader(BytesIO(template_pdf), strict=True)
        if reader.is_encrypted:
            raise PDFAdapterBlocked("Encrypted templates are unsupported")
        _forbidden_dynamic_features(reader)
        existing = reader.get_fields() or {}
        if not set(values).issubset(existing):
            raise PDFAdapterBlocked("Approved PDF field names changed")
        for field in values:
            definition = existing[field]
            if str(definition.get("/FT", "")) != "/Tx":
                raise PDFAdapterBlocked("Only simple PDF text fields are supported")
        writer = PdfWriter()
        writer.append(reader)
        writer.update_page_form_field_values(None, dict(values), auto_regenerate=False)
        output = BytesIO()
        writer.write(output)
        result = output.getvalue()
        check = PdfReader(BytesIO(result), strict=True)
        actual = check.get_fields() or {}
        for key, requested in values.items():
            if str(actual[key].get("/V", "")) != requested:
                raise PDFAdapterBlocked("Post-fill round-trip validation failed")
        return result
    except PDFAdapterBlocked:
        raise
    except Exception as exc:
        raise PDFAdapterBlocked("Unsafe or unsupported PDF structure") from exc
