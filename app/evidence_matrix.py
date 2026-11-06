"""Conservative, source-linked study-permit evidence planning for RCIC practices.

This is an operational *request and review* workflow, not an exhaustive IRCC
checklist, legal eligibility engine, or permission to submit an application.
Requirements and exceptions vary by circumstances and filing location.
"""
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.access import OrgAccess, READ_ROLES, allow, get_org_access
from app.db import get_db
from app.main import record_event
from app.models import Case, CaseDocument, CaseFact, CaseIssue
from app.portal_models import DocumentRequest, PortalSubmission
from app.schemas import Role

router = APIRouter(prefix="/api/v1/orgs/{org_id}/cases/{case_id}/evidence", tags=["evidence-planning"])
INTAKE_ROLES = {Role.owner, Role.admin, Role.consultant, Role.assistant}
SOURCE_DOCUMENTS = "https://www.canada.ca/en/immigration-refugees-citizenship/services/study-canada/study-permit/get-documents.html"
SOURCE_PAL = "https://www.canada.ca/en/immigration-refugees-citizenship/services/study-canada/study-permit/get-documents/provincial-attestation-letter.html"
SOURCE_FUNDS = "https://www.canada.ca/en/immigration-refugees-citizenship/services/study-canada/study-permit/get-documents/financial-support.html"


@dataclass(frozen=True)
class EvidenceRequirement:
    key: str
    title: str
    kind: str  # document | verified_facts | conditional_document
    document_types: tuple[str, ...]
    fact_paths: tuple[str, ...]
    source_url: str
    guidance: str


# A small, explicitly non-exhaustive operational template. Additional country,
# province, personal, portal and legal requirements need RCIC review.
TEMPLATE_VERSION = "study-permit-planning-2026-11-06"
REQUIREMENTS = (
    EvidenceRequirement("identity_facts", "Verified applicant identity", "verified_facts", (),
                        ("identity.given_name", "identity.family_name", "identity.date_of_birth", "identity.passport_number"),
                        SOURCE_DOCUMENTS, "Verify extracted facts against original identity evidence."),
    EvidenceRequirement("passport", "Passport / travel document", "document", ("passport", "passport_copy", "travel_document"), (),
                        SOURCE_DOCUMENTS, "Request the passport identity page and check validity and identity details."),
    EvidenceRequirement("letter_of_acceptance", "Letter of acceptance or exception evidence", "conditional_document",
                        ("letter_of_acceptance", "loa", "loa_exception_evidence"), (), SOURCE_DOCUMENTS,
                        "Exceptions may apply. A professional must assess whether the LOA requirement applies."),
    EvidenceRequirement("financial_support", "Evidence of financial support", "document",
                        ("proof_of_funds", "bank_statement", "financial_support", "scholarship_letter"), (), SOURCE_FUNDS,
                        "Evidence types and required amounts vary; assess finances, family and application timing."),
    EvidenceRequirement("pal_tal", "PAL/TAL, CAQ or evidence supporting an exception", "conditional_document",
                        ("pal_tal", "caq", "pal_exception_evidence"), (), SOURCE_PAL,
                        "Do not assume an exemption. Determine whether PAL/TAL, CAQ or exception evidence applies."),
)


class RequestPlan(BaseModel):
    filing_context: str = Field(pattern=r"^(inside_canada|outside_canada)$")
    requirement_keys: list[str] = Field(default_factory=list, max_length=10)


def _case(db: Session, org_id: UUID, case_id: UUID, *, lock: bool = False) -> Case:
    query = select(Case).where(Case.org_id == org_id, Case.id == case_id)
    matter = db.scalar(query.with_for_update() if lock else query)
    if matter is None:
        raise HTTPException(404, "Matter not found")
    if matter.application_type != "study_permit":
        raise HTTPException(409, "Evidence planning template is only reviewed for study permits")
    return matter


def _matrix(db: Session, org_id: UUID, case_id: UUID, filing_context: str) -> dict:
    facts = db.scalars(select(CaseFact).where(CaseFact.org_id == org_id, CaseFact.case_id == case_id)).all()
    docs = db.scalars(select(CaseDocument).where(CaseDocument.org_id == org_id, CaseDocument.case_id == case_id)).all()
    requests = db.scalars(select(DocumentRequest).where(DocumentRequest.org_id == org_id,
                                                         DocumentRequest.case_id == case_id)).all()
    submissions = db.scalars(select(PortalSubmission).where(PortalSubmission.org_id == org_id,
                                                             PortalSubmission.case_id == case_id)).all()
    open_issues = db.scalars(select(CaseIssue).where(CaseIssue.org_id == org_id, CaseIssue.case_id == case_id,
                                                    CaseIssue.status == "open")).all()
    scan_by_document = {str(item.document_id): item.scan_status for item in submissions}
    rows = []
    for requirement in REQUIREMENTS:
        document_candidates = [d for d in docs if d.document_type in requirement.document_types]
        allowed = [d for d in document_candidates if scan_by_document.get(str(d.id), "staff_upload")
                   in ("staff_upload", "cleared")]
        quarantined = [d for d in document_candidates if scan_by_document.get(str(d.id)) == "quarantined"]
        rejected = [d for d in document_candidates if scan_by_document.get(str(d.id)) == "rejected"]
        existing_requests = [r for r in requests if r.document_type in requirement.document_types and r.status != "cancelled"]
        fact_details = []
        if requirement.kind == "verified_facts":
            for path in requirement.fact_paths:
                verified = [f for f in facts if f.field_path == path and f.review_status == "verified"]
                values = {f.value.strip() for f in verified if f.value.strip()}
                state = "verified" if len(values) == 1 else "conflict" if len(values) > 1 else "unverified"
                fact_details.append({"field_path": path, "state": state,
                                     "fact_ids": sorted(str(f.id) for f in verified)})
            status = "conflict" if any(x["state"] == "conflict" for x in fact_details) else (
                "facts_verified" if all(x["state"] == "verified" for x in fact_details) else "unverified")
        elif allowed:
            status = "received_for_review"
        elif quarantined:
            status = "quarantined"
        elif rejected:
            status = "rejected_upload"
        elif existing_requests:
            status = "requested"
        else:
            status = "missing"
        rows.append({
            "key": requirement.key, "title": requirement.title, "kind": requirement.kind,
            "status": status, "source_url": requirement.source_url, "guidance": requirement.guidance,
            "document_types": list(requirement.document_types), "fact_paths": list(requirement.fact_paths),
            "facts": fact_details, "document_ids": sorted(str(d.id) for d in allowed),
            "quarantined_document_count": len(quarantined), "rejected_document_count": len(rejected),
            "active_request_ids": sorted(str(r.id) for r in existing_requests),
            "requires_professional_applicability_review": requirement.kind == "conditional_document",
        })
    return {
        "case_id": str(case_id), "filing_context": filing_context, "template_version": TEMPLATE_VERSION,
        "source_observed_on": date(2026, 11, 6).isoformat(),
        "source_recheck_required": (date.today() - date(2026, 11, 6)).days > 30,
        "requirements": rows, "open_evidence_issue_count": len(open_issues),
        "unresolved_case_issues": sorted(str(issue.id) for issue in open_issues),
        "release_status": "review_only_no_ircc_submission",
        "professional_review_required": True,
        "warning": "Non-exhaustive operational checklist only. Local instructions, exceptions, current law, "
                   "program conditions and official portal requirements must be checked by an authorized representative. "
                   "Document receipt and fact verification are not an immigration eligibility determination.",
    }


@router.get("/matrix")
def evidence_matrix(org_id: UUID, case_id: UUID,
                    filing_context: str = Query(pattern=r"^(inside_canada|outside_canada)$"),
                    db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    allow(access, READ_ROLES)
    _case(db, org_id, case_id)
    return _matrix(db, org_id, case_id, filing_context)


@router.post("/request-missing")
def request_missing(org_id: UUID, case_id: UUID, payload: RequestPlan,
                    db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    """Create document requests with case-level locking; safe to retry sequentially.

    No automatic messages are sent to clients. Staff must review and deliver
    requests. Conditional requirements stay subject to professional review.
    """
    allow(access, INTAKE_ROLES)
    matter = _case(db, org_id, case_id, lock=True)
    if matter.status == "closed":
        raise HTTPException(409, "Closed cases are read-only")
    matrix = _matrix(db, org_id, case_id, payload.filing_context)
    by_key = {r["key"]: r for r in matrix["requirements"]}
    selected = payload.requirement_keys or [r["key"] for r in matrix["requirements"] if r["status"] == "missing"]
    if len(set(selected)) != len(selected):
        raise HTTPException(422, "Duplicate requirement keys")
    if any(key not in by_key for key in selected):
        raise HTTPException(422, "Unknown requirement key")
    # A reviewed not-applicable decision must also block draft client requests.
    from app.requirement_models import RequirementDecision
    latest_decisions = db.scalars(select(RequirementDecision).where(
        RequirementDecision.org_id == org_id,
        RequirementDecision.case_id == case_id
    ).order_by(RequirementDecision.revision.desc())).all()
    applicability = {}
    for decision in latest_decisions:
        applicability.setdefault(decision.requirement_key, decision.decision)
    created, skipped = [], []
    for key in selected:
        if applicability.get(key) == 'not_applicable':
            skipped.append({'requirement_key': key, 'reason': 'Professional applicability decision: not applicable'})
            continue
        item = by_key[key]
        if item["kind"] == "verified_facts" or item["status"] != "missing":
            skipped.append({"requirement_key": key, "reason": "Not a missing document requirement"})
            continue
        requirement = next(r for r in REQUIREMENTS if r.key == key)
        request = DocumentRequest(
            org_id=org_id, case_id=case_id, title=requirement.title,
            instructions=requirement.guidance + " Do not provide unrelated personal documents.",
            document_type=requirement.document_types[0], status="open",
            created_by_sub=access.principal.sub,
        )
        db.add(request)
        db.flush()
        record_event(db, access, "evidence.document_request_created", "document_request", request.id,
                     {"requirement_key": key, "template_version": TEMPLATE_VERSION})
        created.append({"requirement_key": key, "request_id": str(request.id)})
    db.commit()
    return {"case_id": str(case_id), "created": created, "skipped": skipped,
            "no_client_message_sent": True, "professional_review_required": True}
