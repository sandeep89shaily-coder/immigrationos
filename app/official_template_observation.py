"""Observe the *public blank* IMM 5476 template without storing or approving it.

Research-only monitoring: pinning requires an independent RCIC + technical
release review. No client uploads, form filling, or automated publication.
"""
from datetime import datetime, timezone
from hashlib import sha256
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from app.form_template_inspector import (
    MAX_TEMPLATE_BYTES, TemplateInspectionError, inspect_pdf_template,
)
from app.form_workflow_profiles import PDF_URL as IMM5476_URL, VERSION as IMM5476_REVISION

OFFICIAL_HOSTS = frozenset({"www.canada.ca", "canada.ca"})


class OfficialTemplateObservationError(ValueError):
    pass


def download_published_blank(timeout: int = 18) -> bytes:
    """Only download the hard-coded public government PDF; never arbitrary URLs."""
    request = Request(IMM5476_URL, headers={
        "User-Agent": "ImmigrationOS-BlankFormResearch/0.1",
        "Accept": "application/pdf",
    })
    try:
        with urlopen(request, timeout=timeout) as response:
            target = urlsplit(response.geturl())
            if (target.scheme != "https" or target.hostname not in OFFICIAL_HOSTS
                    or target.username or target.password):
                raise OfficialTemplateObservationError("Unapproved source redirect")
            content_type = response.headers.get_content_type()
            if content_type not in ("application/pdf", "application/octet-stream"):
                raise OfficialTemplateObservationError("Official source did not return PDF content")
            raw = response.read(MAX_TEMPLATE_BYTES + 1)
    except OfficialTemplateObservationError:
        raise
    except (OSError, TimeoutError, ValueError) as exc:
        raise OfficialTemplateObservationError("Official PDF source was unavailable") from exc
    if len(raw) > MAX_TEMPLATE_BYTES or not raw.startswith(b"%PDF-"):
        raise OfficialTemplateObservationError("Official source PDF exceeded limits or was not a PDF")
    return raw


def observe_blank_template(raw: bytes, *, observed_at: datetime | None = None,
                           pinned_sha256: str | None = None) -> dict:
    """Never marks an official template as supported, irrespective of outcome."""
    try:
        report = inspect_pdf_template(raw)
    except TemplateInspectionError as exc:
        raise OfficialTemplateObservationError("Blank form technical inspection failed") from exc
    timestamp = (observed_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    current_hash = sha256(raw).hexdigest()
    if pinned_sha256 is not None:
        if len(pinned_sha256) != 64 or any(c not in "0123456789abcdef" for c in pinned_sha256):
            raise OfficialTemplateObservationError("Invalid pinned template SHA-256")
        compare_state = "same_bytes" if pinned_sha256 == current_hash else "changed_bytes"
    else:
        compare_state = "baseline_not_yet_approved"
    return {
        "form_code": "IMM5476",
        "claimed_official_revision": IMM5476_REVISION,
        "source_url": IMM5476_URL,
        "source_observed_at": timestamp.isoformat(),
        "revision_confirmed_by_pdf_review": False,
        "source_authenticity_independently_verified": False,
        "expected_baseline_sha256": pinned_sha256,
        "baseline_comparison": compare_state,
        "technical_inspection": report,
        "pdf_bytes_saved": False,
        "release_approved": False,
        "official_autofill_supported": False,
        "submission_supported": False,
        "warning": "Research-only observation. A matching PDF hash or static-form classification "
                   "does not satisfy current IRCC/Adobe, signature, mapping, licensing, or "
                   "professional release criteria.",
    }
