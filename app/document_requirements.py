"""Case document requirements with source-pinned professional decisions.

The checklist is intentionally non-exhaustive. An accepted file is only an
operational evidence review, never proof that IRCC accepts the document.
"""
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.access import OrgAccess, READ_ROLES, allow, get_org_access
from app.db import get_db
from app.evidence_matrix import REQUIREMENTS, TEMPLATE_VERSION, _matrix
from app.main import record_event
from app.models import Case, CaseDocument
from app.package_models import CaseApplicationPackage
from app.portal_models import PortalSubmission
from app.requirement_models import RequirementDecision, RequirementDocumentReview
from app.schemas import Role

router = APIRouter(prefix="/api/v1/orgs/{org_id}/cases/{case_id}/requirements",
                   tags=["document-requirements"])
REVIEWERS = {Role.owner, Role.admin, Role.consultant}
BY_KEY = {r.key: r for r in REQUIREMENTS}
OBSERVED = date(2026, 11, 6)


class ApplicabilityInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: str = Field(pattern=r"^(required|not_applicable)$")
    reason: str = Field(min_length=25, max_length=900)
    confirmed_current_source: bool
    expected_revision: int = Field(ge=0)


class DocumentReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_id: UUID
    decision: str = Field(pattern=r"^(accepted|rejected)$")
    reason: str = Field(min_length=25, max_length=900)
    inspected_original_document: bool


def _context(db, org_id, case_id):
    case = db.scalar(select(Case).where(Case.org_id == org_id, Case.id == case_id))
    if case is None:
        raise HTTPException(404, "Case unavailable")
    pkg = db.scalar(select(CaseApplicationPackage).where(
        CaseApplicationPackage.org_id == org_id, CaseApplicationPackage.case_id == case_id))
    if pkg is None:
        raise HTTPException(409, "Initialize the application package first")
    return case, pkg


def _key(key):
    requirement = BY_KEY.get(key)
    if requirement is None:
        raise HTTPException(404, "Requirement not found")
    return requirement


def _latest_decisions(db, org_id, case_id):
    records = db.scalars(select(RequirementDecision).where(
        RequirementDecision.org_id == org_id, RequirementDecision.case_id == case_id
    ).order_by(RequirementDecision.revision.desc(), RequirementDecision.id.desc())).all()
    return {x.requirement_key: x for x in records[::-1]}


def _read(db, org_id, case_id):
    case, pkg = _context(db, org_id, case_id)
    matrix = _matrix(db, org_id, case_id, pkg.filing_context)
    decisions = _latest_decisions(db, org_id, case_id)
    doc_reviews = db.scalars(select(RequirementDocumentReview).where(
        RequirementDocumentReview.org_id == org_id,
        RequirementDocumentReview.case_id == case_id)).all()
    reviews_by_key = {}
    for item in doc_reviews:
        reviews_by_key.setdefault(item.requirement_key, []).append(item)
    rows = []
    for req in matrix["requirements"]:
        key = req["key"]
        policy = decisions.get(key)
        state = policy.decision if policy else ("review_required" if req["kind"] == "conditional_document" else "required")
        accepted = [r for r in reviews_by_key.get(key, []) if r.decision == "accepted"]
        rejected = [r for r in reviews_by_key.get(key, []) if r.decision == "rejected"]
        # Reviewed document must still be present in the existing matrix's
        # scan-eligible list. Quarantined items never become "cleared".
        eligible = set(req["document_ids"])
        accepted = [r for r in accepted if str(r.document_id) in eligible]
        if state == "not_applicable":
            status = "professionally_marked_not_applicable"
        elif state == "review_required":
            status = "applicability_review_required"
        elif req["kind"] == "verified_facts":
            status = req["status"]
        elif accepted:
            status = "staff_reviewed_document"
        elif req["status"] in ("quarantined", "rejected_upload"):
            status = req["status"]
        elif rejected:
            status = "document_rejected"
        else:
            status = req["status"]
        rows.append({**req, "applicability": state,
                     "applicability_revision": policy.revision if policy else 0,
                     "decision_reason": policy.reason if policy else None,
                     "decision_reviewer": policy.reviewed_by_sub if policy else None,
                     "reviewed_document_ids": sorted(str(r.document_id) for r in accepted),
                     "rejected_document_ids": sorted(str(r.document_id) for r in rejected),
                     "status": status})
    unresolved = [r["key"] for r in rows if r["status"] not in
                  ("professionally_marked_not_applicable", "staff_reviewed_document", "facts_verified")]
    return {"case_id": str(case_id), "filing_context": pkg.filing_context,
            "template_version": TEMPLATE_VERSION,
            "source_observed_on": OBSERVED.isoformat(),
            "source_recheck_required": (date.today() - OBSERVED).days > 30,
            "requirements": rows, "unresolved_requirements": unresolved,
            "document_worklist_complete": not unresolved,
            "professional_eligibility_verified": False,
            "official_application_ready": False, "submission_supported": False,
            "warning": "This is a non-exhaustive source-anchored preparation worklist. Staff reviews are not IRCC document acceptance or an eligibility decision."}


@router.get("")
def read_requirements(org_id: UUID, case_id: UUID, db: Session = Depends(get_db),
                      access: OrgAccess = Depends(get_org_access)):
    allow(access, READ_ROLES)
    return _read(db, org_id, case_id)


@router.post("/{key}/applicability", status_code=201)
def decide_applicability(org_id: UUID, case_id: UUID, key: str, payload: ApplicabilityInput,
                         db: Session = Depends(get_db),
                         access: OrgAccess = Depends(get_org_access)):
    allow(access, REVIEWERS)
    case, pkg = _context(db, org_id, case_id)
    if case.status == "closed":
        raise HTTPException(409, "Closed cases are read-only")
    requirement = _key(key)
    if requirement.kind != "conditional_document":
        raise HTTPException(409, "Only conditional requirements have applicability decisions")
    if payload.confirmed_current_source is not True:
        raise HTTPException(422, "Confirm current official source before recording applicability")
    previous = db.scalar(select(RequirementDecision).where(
        RequirementDecision.org_id == org_id, RequirementDecision.case_id == case_id,
        RequirementDecision.requirement_key == key
    ).order_by(RequirementDecision.revision.desc()).limit(1))
    latest = previous.revision if previous else 0
    if payload.expected_revision != latest:
        raise HTTPException(409, "Applicability has changed; refresh the worklist")
    row = RequirementDecision(
        org_id=org_id, case_id=case_id, requirement_key=key,
        revision=latest + 1, decision=payload.decision, reason=payload.reason.strip(),
        source_url=requirement.source_url, source_template_version=TEMPLATE_VERSION,
        source_observed_on=OBSERVED, reviewed_by_sub=access.principal.sub)
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Concurrent applicability update; refresh") from None
    record_event(db, access, "requirement.applicability_reviewed", "case", case_id,
                 {"requirement_key": key, "revision": row.revision, "decision": row.decision})
    db.commit()
    return {"key": key, "revision": row.revision, "decision": row.decision,
            "source_url": row.source_url, "source_observed_on": row.source_observed_on.isoformat(),
            "official_application_ready": False}


@router.post("/{key}/documents/review", status_code=201)
def review_requirement_document(org_id: UUID, case_id: UUID, key: str, payload: DocumentReviewInput,
                                db: Session = Depends(get_db),
                                access: OrgAccess = Depends(get_org_access)):
    allow(access, REVIEWERS)
    case, pkg = _context(db, org_id, case_id)
    if case.status == "closed":
        raise HTTPException(409, "Closed cases are read-only")
    requirement = _key(key)
    if requirement.kind == "verified_facts":
        raise HTTPException(409, "This requirement uses verified facts, not a document review")
    if payload.inspected_original_document is not True:
        raise HTTPException(422, "Document must be independently inspected")
    document = db.scalar(select(CaseDocument).where(
        CaseDocument.org_id == org_id, CaseDocument.case_id == case_id,
        CaseDocument.id == payload.document_id))
    if document is None:
        raise HTTPException(404, "Document not part of this case")
    if document.document_type not in requirement.document_types:
        raise HTTPException(409, "Document type does not satisfy this requirement slot")
    portal = db.scalar(select(PortalSubmission).where(
        PortalSubmission.org_id == org_id, PortalSubmission.case_id == case_id,
        PortalSubmission.document_id == document.id))
    if portal and portal.scan_status != "cleared":
        raise HTTPException(423, "Document has not passed the malware scan")
    previous = db.scalar(select(RequirementDocumentReview).where(
        RequirementDocumentReview.org_id == org_id,
        RequirementDocumentReview.case_id == case_id,
        RequirementDocumentReview.requirement_key == key,
        RequirementDocumentReview.document_id == document.id))
    if previous is not None:
        raise HTTPException(409, "This document has already been reviewed for this requirement")
    row = RequirementDocumentReview(
        org_id=org_id, case_id=case_id, requirement_key=key,
        document_id=document.id, document_sha256=document.sha256,
        decision=payload.decision, reason=payload.reason.strip(),
        source_template_version=TEMPLATE_VERSION, reviewed_by_sub=access.principal.sub)
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Concurrent document review; refresh") from None
    record_event(db, access, "requirement.document_reviewed", "case", case_id,
                 {"requirement_key": key, "document_id": str(document.id), "decision": row.decision})
    db.commit()
    return {"key": key, "document_id": str(document.id), "decision": row.decision,
            "document_sha256": row.document_sha256, "official_application_ready": False}
