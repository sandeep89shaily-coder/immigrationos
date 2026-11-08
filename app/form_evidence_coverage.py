"""Reusable reviewed-evidence coverage for registry forms, not IRCC form completion.

Evaluates only the deliberately limited reviewed *internal* field subsets in
REGISTRY. No complete field inventory, dynamic sections, PDF or filing claim.
"""
from datetime import date
from decimal import Decimal, InvalidOperation
import re
from hashlib import sha256
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.access import OrgAccess, READ_ROLES, allow, get_org_access
from app.db import get_db
from app.imm5476_case_preview import _field_status, scan_status_by_document
from app.ircc_registry import REGISTRY, ObservedForm, source_metadata
from app.form_manifest import MANIFESTS, expand_manifest
from app.models import Case, CaseDocument, CaseFact, CaseIssue

router = APIRouter(prefix="/api/v1/orgs/{org_id}/ircc", tags=["ircc-reviewed-evidence-coverage"])

# Canonical keys for the small set of fields with separately checked syntax.
FORMAT_KEYS = {
    "identity.date_of_birth": "applicant_dob",
}
SCHEMA_VERSION = "internal-reviewed-subset-1"


DATE_PATHS = frozenset({
    "identity.passport_issue_date", "identity.passport_expiry_date",
    "education.program_start_date", "education.program_end_date",
    "identity.national_id_issue_date", "identity.national_id_expiry_date",
})
MONEY_PATHS = frozenset({"finance.tuition_cad", "finance.available_funds_cad"})


def validate_guided_value(path: str, state: dict) -> dict:
    """Fail closed for new guidance fields with locally checkable syntax.

    Real-world plausibility and documentary credibility remain human decisions.
    """
    if state["status"] != "verified_source_value":
        return state
    value = state["value"]
    plausible = True
    if path in {
        "identity.has_other_names", "identity.has_national_id",
        "history.has_previous_relationships", "history.has_foreign_residences",
    }:
        # "unsure" is an unresolved instruction-level declaration, never a
        # verified Boolean condition that can dismiss dependent questions.
        plausible = value in ("yes", "no")
    elif path in DATE_PATHS:
        try:
            plausible = date.fromisoformat(value).isoformat() == value
        except (TypeError, ValueError):
            plausible = False
    elif path in MONEY_PATHS:
        try:
            money = Decimal(value)
            plausible = (money.is_finite() and money >= 0
                         and money.as_tuple().exponent >= -2)
        except (InvalidOperation, TypeError):
            plausible = False
    elif path == "education.dli_number":
        # Do not falsely validate an institution's DLI status using this syntax.
        plausible = bool(re.fullmatch(r"[O0-9][A-Za-z0-9-]{2,40}", value))
    if not plausible:
        return {**state, "status": "invalid_evidence_value", "value": None,
                "evidence_ids": [], "document_ids": [], "source_hashes": []}
    return state


def reviewed_subset_report(*, source: ObservedForm, case: Case,
                           facts: list[CaseFact], documents: list[CaseDocument],
                           scan_status: dict[UUID, str], open_issue_count: int,
                           today: date | None = None) -> dict:
    """Evaluate each field independently; never substitute unsafe source values."""
    today = today or date.today()
    meta = source_metadata(source, today=today)
    scoped_documents = {d.id: d for d in documents
                        if d.org_id == case.org_id and d.case_id == case.id}
    scoped_facts = [f for f in facts
                    if f.org_id == case.org_id and f.case_id == case.id]
    manifest = MANIFESTS[source.code]
    if (manifest.form_revision != source.revision_label
            or manifest.filing_context != source.filing_context):
        raise ValueError("Manifest/source revision mismatch")
    # Only cleared, uniquely reviewed facts can determine conditional paths.
    # This initial live manifest has no condition rules or repeated sections.
    # A future conditional manifest must never assume unknown == false.
    verified_values = {}
    for section in manifest.sections:
        for field in section.fields:
            selected = [f for f in scoped_facts if f.field_path == field.canonical_path]
            state = validate_guided_value(
                field.canonical_path,
                _field_status(FORMAT_KEYS.get(field.canonical_path, field.canonical_path),
                              selected, scoped_documents, scan_status))
            if state["status"] == "verified_source_value":
                verified_values[field.canonical_path] = state["value"]
    expanded = expand_manifest(manifest, verified_values)
    fields = []
    for section in expanded:
        for field in section["fields"]:
            selected = [f for f in scoped_facts
                        if f.field_path == field["canonical_path"]]
            state = validate_guided_value(field["canonical_path"], _field_status(
                FORMAT_KEYS.get(field["canonical_path"], field["canonical_path"]),
                selected, scoped_documents, scan_status))
            if field["condition_state"] != "active":
                # Never reveal or count data from an inactive or unresolved branch.
                state = {"status": "inactive_condition" if
                         field["condition_state"] == "inactive" else "unresolved_condition",
                         "value": None, "evidence_ids": [], "document_ids": [],
                         "source_hashes": []}
            fields.append({
                "label": field["label"], "canonical_path": field["canonical_path"],
                "condition_state": field["condition_state"],
                "source_url": field["source_url"],
                "source_section": field["source_section"], **state})


    verified = sum(f["status"] == "verified_source_value" for f in fields)
    applicable = [f for f in fields if f["condition_state"] != "inactive"]
    unresolved_sections = any(x["state"].startswith("unresolved") for x in expanded)
    unsafe_states = {"conflicting_evidence", "unreviewed_evidence",
                     "invalid_evidence_value", "missing_case_document",
                     "source_scan_not_cleared"}
    blockers = []
    if case.status == "closed":
        blockers.append("case_closed")
    if open_issue_count:
        blockers.append("open_evidence_issues")
    if meta["source_recheck_required"]:
        blockers.append("source_review_stale")
    if any(f["status"] in unsafe_states for f in fields):
        blockers.append("unresolved_or_unsafe_evidence")
    if any(f["status"] == "unresolved_condition" for f in fields) or unresolved_sections:
        blockers.append("conditional_applicability_unresolved")
    if verified != len(applicable) or unresolved_sections:
        blockers.append("internal_preview_fields_unresolved")
    blockers += ["complete_form_mapping_unverified",
                 "official_pdf_validation_unverified",
                 "professional_form_review_required"]
    result = {
        **meta,
        "case_id": str(case.id),
        "schema_version": SCHEMA_VERSION,
        "manifest_version": manifest.manifest_version,
        "manifest_sha256": manifest.digest,
        "manifest_sections": expanded,
        "guided_source_field_count": sum(f["source_url"] is not None for f in fields),
        "fields": fields,
        "internal_preview_field_count": len(fields),
        "verified_preview_field_count": verified,
        "missing_preview_field_count": sum(
            f["status"] == "missing_evidence" for f in fields),
        "verified_internal_subset": verified == len(applicable) and not unresolved_sections
            and all(f["status"] != "unresolved_condition" for f in fields) and not (
            case.status == "closed" or open_issue_count
            or meta["source_recheck_required"]),
        "blockers": sorted(set(blockers)),
        "entire_official_form_complete": False,
        "pdf_export_available": False,
        "submission_supported": False,
        "warning": "Partial internal evidence inventory only; not a completed or validated IRCC form.",
    }
    result["snapshot_sha256"] = sha256(json.dumps(
        result, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")).hexdigest()
    return result


@router.get("/cases/{case_id}/forms/{form_code}/evidence-coverage")
def read_reviewed_evidence_coverage(
    org_id: UUID, case_id: UUID, form_code: str, response: Response,
    filing_context: str = Query(min_length=3, max_length=40),
    db: Session = Depends(get_db),
    access: OrgAccess = Depends(get_org_access),
):
    allow(access, READ_ROLES)
    case = db.scalar(select(Case).where(Case.org_id == org_id, Case.id == case_id))
    if case is None:
        raise HTTPException(404, "Matter not found")
    source = REGISTRY.get(form_code.upper())
    if source is None:
        raise HTTPException(404, "Form not in reviewed registry")
    if source.application_type != case.application_type or source.filing_context != filing_context:
        raise HTTPException(409, "Form context does not match this matter")
    facts = db.scalars(select(CaseFact).where(
        CaseFact.org_id == org_id, CaseFact.case_id == case_id)).all()
    documents = db.scalars(select(CaseDocument).where(
        CaseDocument.org_id == org_id, CaseDocument.case_id == case_id)).all()
    open_issues = db.scalars(select(CaseIssue).where(
        CaseIssue.org_id == org_id, CaseIssue.case_id == case_id,
        CaseIssue.status == "open")).all()
    response.headers["Cache-Control"] = "no-store"
    return reviewed_subset_report(
        source=source, case=case, facts=facts, documents=documents,
        scan_status=scan_status_by_document(db, org_id, case_id),
        open_issue_count=len(open_issues))
