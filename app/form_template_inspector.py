"""Read-only PDF form structure inspection for the RCIC form factory.

This module never fills, stores, signs, validates or submits official IRCC
forms. It accepts only blank, locally supplied template bytes; the output is
a technical *candidate* classification, never approval to use a form.
"""
from collections import Counter
from hashlib import sha256
from io import BytesIO
import re

from pypdf import PdfReader

MAX_TEMPLATE_BYTES = 12 * 1024 * 1024
MAX_PAGES = 40
MAX_FIELDS = 1000
MAX_ANNOTATIONS = 1500
FIELD_TYPES = {"/Tx": "text", "/Btn": "button", "/Ch": "choice", "/Sig": "signature"}


class TemplateInspectionError(ValueError):
    """Invalid or unsafe template input; detail must not contain PDF contents."""


def _plain(value):
    return value.get_object() if hasattr(value, "get_object") else value


def _existing_value(field):
    value = field.get("/V")
    if value is None:
        return False
    # /Off means an unchecked PDF checkbox, not personal information.
    return str(_plain(value)) not in ("", "/Off")


def inspect_pdf_template(raw: bytes) -> dict:
    """Classify a blank form's field structure without modifying the PDF.

    Unknown/dynamic types remain blocked; even a static AcroForm *candidate*
    cannot be released before a pinned reviewed mapping and offline QA.
    """
    if not isinstance(raw, bytes) or not raw.startswith(b"%PDF-"):
        raise TemplateInspectionError("An unmodified PDF file is required")
    if len(raw) > MAX_TEMPLATE_BYTES or len(raw) < 100:
        raise TemplateInspectionError("Template exceeds inspection size limits or is truncated")
    try:
        reader = PdfReader(BytesIO(raw), strict=True)
        if reader.is_encrypted:
            raise TemplateInspectionError("Encrypted forms are not accepted for inspection")
        if not 0 < len(reader.pages) <= MAX_PAGES:
            raise TemplateInspectionError("Template page count outside inspection limits")
        root = _plain(reader.trailer["/Root"])
        acro = _plain(root.get("/AcroForm")) if root.get("/AcroForm") else None
        flags: list[str] = []
        if acro is None:
            flags.append("no_acroform")
        else:
            if "/XFA" in acro:
                flags.append("xfa_present")
            if "/AA" in acro:
                flags.append("acroform_additional_actions")
        if "/OpenAction" in root or "/AA" in root:
            flags.append("document_actions")
        if "/Perms" in root:
            flags.append("document_permissions_or_signatures")
        names = _plain(root.get("/Names")) if root.get("/Names") else None
        if names:
            if "/JavaScript" in names:
                flags.append("embedded_javascript")
            if "/EmbeddedFiles" in names:
                flags.append("embedded_files")
        annots = 0
        for page in reader.pages:
            if "/AA" in page:
                flags.append("page_actions")
            for annotation_ref in page.get("/Annots", []):
                annots += 1
                if annots > MAX_ANNOTATIONS:
                    raise TemplateInspectionError("Too many annotations to inspect safely")
                annotation = _plain(annotation_ref)
                if "/AA" in annotation or "/A" in annotation:
                    flags.append("annotation_actions")
                if annotation.get("/FT") == "/Sig":
                    flags.append("signature_widgets")
        fields = reader.get_fields() or {}
        if len(fields) > MAX_FIELDS:
            raise TemplateInspectionError("Template field count exceeds inspection limit")
        type_counts = Counter()
        field_names = []
        populated = False
        unknown_types = False
        for field_name, field in fields.items():
            name = str(field_name)
            if not name or len(name) > 180 or any(ord(ch) < 32 for ch in name):
                flags.append("unusual_field_names")
                continue
            field_names.append(name)
            field = _plain(field)
            kind = str(field.get("/FT", "unknown"))
            type_counts[FIELD_TYPES.get(kind, "unknown")] += 1
            if kind not in FIELD_TYPES:
                unknown_types = True
            if _existing_value(field):
                populated = True
            if "/AA" in field or "/A" in field:
                flags.append("field_actions")
        if populated:
            flags.append("populated_fields_present")
        if unknown_types:
            flags.append("unrecognized_field_types")
        if any(name.startswith("signature") for name in field_names):
            flags.append("signature_fields_require_review")

        flags = sorted(set(flags))
        if "xfa_present" in flags:
            classification = "xfa_or_hybrid_requires_adobe_workflow"
        elif "embedded_javascript" in flags or any("actions" in x for x in flags):
            classification = "active_content_requires_manual_review"
        elif "populated_fields_present" in flags:
            classification = "nonblank_template_rejected"
        elif acro is None or not fields:
            classification = "nonfillable_pdf_requires_manual_review"
        elif "unrecognized_field_types" in flags or "unusual_field_names" in flags:
            classification = "unsupported_field_structure"
        else:
            classification = "static_acroform_candidate"

        # All classifications remain review-only: barcode/signature rules
        # cannot be derived safely from a PDF's field dictionary alone.
        return {
            "file_sha256": sha256(raw).hexdigest(),
            "size_bytes": len(raw),
            "pages": len(reader.pages),
            "field_count": len(fields),
            "field_type_counts": dict(sorted(type_counts.items())),
            "field_names": sorted(field_names),
            "indicators": flags,
            "classification": classification,
            "candidate_for_static_adapter": classification == "static_acroform_candidate",
            "requires_official_form_version_review": True,
            "requires_barcode_and_signature_review": True,
            "independently_validated": False,
            "official_pdf_autofill_supported": False,
            "submission_supported": False,
            "warning": (
                "Technical inspection only. An empty/ordinary AcroForm is NOT "
                "proof that IRCC accepts generic PDF filling. Confirm version, "
                "form instructions, all fields, barcode/signature workflows, "
                "and Adobe validation independently."
            ),
        }
    except TemplateInspectionError:
        raise
    except Exception as exc:
        # Never reflect possible client/personal content in errors or logs.
        raise TemplateInspectionError("PDF structure is not safely inspectable") from exc
