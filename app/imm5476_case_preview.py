"""IMM5476 (11-2025) evidence-backed, READ-ONLY case preparation preview.

Only the observed, limited paid-CICC appointment experiment is mapped.
This route NEVER produces XDP/PDF, signs, enables autofill or submits a case.
It cannot be a general IMM5476 completeness or legal-sufficiency decision.
"""
from __future__ import annotations

from datetime import date
from hashlib import sha256
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.access import OrgAccess, READ_ROLES, allow, get_org_access
from app.db import get_db
from app.form_mapping import FormMappingBlocked, resolve_verified_form_fields
from app.form_workflow_profiles import PDF_URL, REVIEWED_ON, VERSION
from app.imm5476_official_poc import SOURCE_SHA256
from app.imm5476_paid_cicc_poc import TEXT_PATHS, full_pdf_name
from app.models import Case, CaseDocument, CaseFact, CaseIssue
from app.portal_models import PortalSubmission

router = APIRouter(
    prefix="/api/v1/orgs/{org_id}/cases/{case_id}/ircc/IMM5476",
    tags=["imm5476-evidence-preparation"],
)

MAPPING_VERSION = "imm5476-11-2025-paid-cicc-observed21-v1"

# Canonical case facts, NOT arbitrary applicant-profile answers. All 21
# observed PDF fields must have independently verified, case-linked evidence
# before the experimental subset can be considered resolved.
CANONICAL_FIELDS: dict[str, str] = {
    "applicant_family": "identity.family_name",
    "applicant_given": "identity.given_name",
    "applicant_dob": "identity.date_of_birth",
    "applicant_email": "contact.email",
    "application_type": "application.description",
    "application_number": "application.application_number",
    "uci": "identity.uci",
    "representative_family": "representative.family_name",
    "representative_given": "representative.given_name",
    "cicc_membership": "representative.cicc_membership",
    "organization": "representative.organization",
    "unit": "representative.address.unit",
    "street_no": "representative.address.street_number",
    "street_name": "representative.address.street_name",
    "city": "representative.address.city",
    "province": "representative.address.province",
    "country": "representative.address.country",
    "postal_code": "representative.address.postal_code",
    "phone_country_code": "representative.contact.phone_country_code",
    "phone_number": "representative.contact.phone_number",
    "representative_email": "representative.contact.email",
}
assert set(CANONICAL_FIELDS) == set(TEXT_PATHS) and len(CANONICAL_FIELDS) == 21


def scan_status_by_document(db: Session, org_id: UUID, case_id: UUID) -> dict[UUID, str]:
    rows = db.scalars(select(PortalSubmission).where(
        PortalSubmission.org_id == org_id,
        PortalSubmission.case_id == case_id)).all()
    return {row.document_id: row.scan_status for row in rows}


def _field_status(
    candidates: list[CaseFact],
    documents: dict[UUID, CaseDocument],
    scan_status: dict[UUID, str],
) -> dict:
    # A rejected suggestion is not an active fact. All other candidate values
    # must be reconciled, even when some have not yet been reviewed.
    live = [f for f in candidates if f.review_status != "rejected"]
    field = {
        "status": "missing_evidence",
        "value": None,
        "evidence_ids": [],
        "document_ids": [],
        "source_hashes": [],
    }
    if not live:
        return field
    values = {f.value.strip() for f in live if f.value and f.value.strip()}
    if len(values) > 1:
        field["status"] = "conflicting_evidence"
    elif any(f.review_status != "verified" or not f.reviewed_by_sub for f in live):
        field["status"] = "unreviewed_evidence"
    elif not values or any(not f.value or not f.value.strip() or len(f.value.strip()) > 1000 for f in live):
        field["status"] = "invalid_evidence_value"
    elif any(f.document_id is None or f.document_id not in documents for f in live):
        field["status"] = "missing_case_document"
    elif any(scan_status.get(f.document_id) != "cleared" for f in live):
        field["status"] = "source_scan_not_cleared"
    else:
        field.update({
            "status": "verified_source_value",
            "value": next(iter(values)),
            "evidence_ids": sorted(str(f.id) for f in live),
            "document_ids": sorted({str(f.document_id) for f in live}),
            "source_hashes": sorted({documents[f.document_id].sha256 for f in live}),
        })
    return field


def build_preview(
    *, org_id: UUID, case: Case, facts: list[CaseFact],
    documents: list[CaseDocument], scan_status: dict[UUID, str],
    open_issue_count: int, today: date | None = None,
) -> dict:
    if case.org_id != org_id:
        raise ValueError("Cross-organization case context")
    today = today or date.today()
    docs = {d.id: d for d in documents
            if d.org_id == org_id and d.case_id == case.id}
    scope_facts = [f for f in facts
                   if f.org_id == org_id and f.case_id == case.id]
    fields = []
    for key, canonical_path in CANONICAL_FIELDS.items():
        matched = [f for f in scope_facts if f.field_path == canonical_path]
        state = _field_status(matched, docs, scan_status)
        fields.append({
            "key": key,
            "canonical_path": canonical_path,
            # Stable PDF field identifier is only informational on this
            # internal preview. No XDP or PDF export route is connected.
            "observed_pdf_field": full_pdf_name(TEXT_PATHS[key]),
            **state,
        })
    all_fields_verified = all(row["status"] == "verified_source_value"
                              for row in fields)
    source_fingerprint = None
    if all_fields_verified:
        # A second, mature gate verifies tenant/case isolation, review,
        # document scan and provenance before claiming subset readiness.
        try:
            packet = resolve_verified_form_fields(
                org_id=org_id, case_id=case.id,
                field_to_canonical={
                    full_pdf_name(TEXT_PATHS[key]): canonical
                    for key, canonical in CANONICAL_FIELDS.items()
                },
                facts=(f for f in scope_facts if f.review_status != "rejected"),
                documents=docs.values(),
                scan_status_by_document=scan_status,
            )
            source_fingerprint = packet.source_sha256
        except FormMappingBlocked:
            all_fields_verified = False
    blocked = []
    if case.status == "closed":
        blocked.append("case_closed")
    if open_issue_count:
        blocked.append("open_evidence_issues")
    if (today - date.fromisoformat(REVIEWED_ON)).days > 30:
        blocked.append("source_review_stale")
    if not all_fields_verified:
        blocked.append("observed_fields_unresolved")
    # The known experiment has 21 text and 2 radio controls; it omits
    # declarations, variants, supplementary fields and professional review.
    blocked.extend(["complete_form_mapping_unverified",
                    "commercial_pdf_engine_licence_unverified",
                    "professional_signature_review_required"])
    report = {
        "form_code": "IMM5476",
        "revision": VERSION,
        "official_template_sha256": SOURCE_SHA256,
        "official_pdf_url": PDF_URL,
        "observed_on": REVIEWED_ON,
        "mapping_version": MAPPING_VERSION,
        "operation": "appoint",
        "representative_type": "paid_cicc",
        "case_id": str(case.id),
        "fields": fields,
        "observed_text_fields": 21,
        "verified_text_fields": sum(f["status"] == "verified_source_value" for f in fields),
        "observed_radio_choices": ["appoint", "paid_cicc"],
        "verified_observed_subset": all_fields_verified,
        "verified_source_fingerprint": source_fingerprint,
        "open_evidence_issues": open_issue_count,
        "blockers": sorted(set(blocked)),
        "pdf_export_available": False,
        "official_pdf_autofill_supported": False,
        "official_ircc_validation_verified": False,
        "submission_supported": False,
        "warning": (
            "Internal review-only observed 21-field subset of the IMM5476 paid-CICC "
            "appointment scenario. Not full form coverage, an electronic signature, "
            "a legal determination, a PDF export or permission for client submissions."
        ),
    }
    report["snapshot_sha256"] = sha256(json.dumps(
        report, ensure_ascii=False, sort_keys=True,
        separators=(",", ":")).encode("utf-8")).hexdigest()
    return report


@router.get("/preparation")
def imm5476_case_preview(
    org_id: UUID, case_id: UUID, response: Response,
    operation: str = Query("appoint", min_length=4, max_length=32),
    representative_type: str = Query("paid_cicc", min_length=4, max_length=32),
    db: Session = Depends(get_db),
    access: OrgAccess = Depends(get_org_access),
):
    allow(access, READ_ROLES)
    if operation != "appoint" or representative_type != "paid_cicc":
        raise HTTPException(
            422, "Only the observed appoint-paid-CICC scenario is mapped")
    case = db.scalar(select(Case).where(Case.org_id == org_id, Case.id == case_id))
    if case is None:
        raise HTTPException(404, "Matter not found")
    facts = db.scalars(select(CaseFact).where(
        CaseFact.org_id == org_id, CaseFact.case_id == case_id)).all()
    docs = db.scalars(select(CaseDocument).where(
        CaseDocument.org_id == org_id, CaseDocument.case_id == case_id)).all()
    issues = db.scalars(select(CaseIssue).where(
        CaseIssue.org_id == org_id, CaseIssue.case_id == case_id,
        CaseIssue.status == "open")).all()
    response.headers["Cache-Control"] = "no-store"
    return build_preview(
        org_id=org_id, case=case, facts=facts, documents=docs,
        scan_status=scan_status_by_document(db, org_id, case_id),
        open_issue_count=len(issues))
