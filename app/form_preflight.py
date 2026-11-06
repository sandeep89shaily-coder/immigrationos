"""Internal IRCC field preflight with source-bound, expiring human acknowledgements.

This is not an IRCC form, eligibility opinion, professional licensure verification,
or submission approval. Only a reviewed subset of mapped fields is considered.
No client data is copied into the audit event; only a salted snapshot digest.
"""
from datetime import date
import hashlib
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.access import OrgAccess, READ_ROLES, allow, get_org_access
from app.db import get_db, set_db_context
from app.ircc_registry import REGISTRY, ObservedForm, source_metadata
from app.models import AuditEvent, Case, CaseDocument, CaseFact, CaseIssue, CaseTask
from app.portal_models import PortalSubmission
from app.schemas import Role

router = APIRouter(prefix="/api/v1/orgs/{org_id}/ircc", tags=["ircc-internal-preflight"])
REVIEW_ROLES = {Role.owner, Role.admin, Role.consultant}
PREFLIGHT_SCHEMA_VERSION = "evidence-preflight-1"
ACK_ACTION = "form.internal_preflight_acknowledged"


class AcknowledgeInput(BaseModel):
    snapshot_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


def _case_source(db: Session, org_id: UUID, case_id: UUID,
                 form_code: str, filing_context: str, lock: bool = False):
    query = select(Case).where(Case.org_id == org_id, Case.id == case_id)
    case = db.scalar(query.with_for_update() if lock else query)
    if case is None:
        raise HTTPException(status_code=404, detail="Matter not found")
    source = REGISTRY.get(form_code.upper())
    if source is None:
        raise HTTPException(status_code=404, detail="Form not in reviewed registry")
    if (source.application_type != case.application_type or
            source.filing_context != filing_context):
        raise HTTPException(status_code=409, detail="Form context does not match this matter")
    return case, source


def _snapshot(db: Session, case: Case, source: ObservedForm,
              today: date | None = None) -> dict:
    """Generate a deterministic internal snapshot without claiming full form coverage."""
    org_id, case_id = case.org_id, case.id
    facts = db.scalars(select(CaseFact).where(
        CaseFact.org_id == org_id, CaseFact.case_id == case_id)).all()
    documents = db.scalars(select(CaseDocument).where(
        CaseDocument.org_id == org_id, CaseDocument.case_id == case_id)).all()
    submissions = db.scalars(select(PortalSubmission).where(
        PortalSubmission.org_id == org_id, PortalSubmission.case_id == case_id)).all()
    issues = db.scalars(select(CaseIssue).where(
        CaseIssue.org_id == org_id, CaseIssue.case_id == case_id)).all()
    tasks = db.scalars(select(CaseTask).where(
        CaseTask.org_id == org_id, CaseTask.case_id == case_id)).all()

    doc_by_id = {doc.id: doc for doc in documents}
    scan_by_id = {item.document_id: item.scan_status for item in submissions}
    blocked_docs = {id_ for id_, scan in scan_by_id.items() if scan != "cleared"}
    meta = source_metadata(source, today=today)
    blockers = []

    if case.status == "closed":
        blockers.append("This matter is closed")
    if meta["source_recheck_required"]:
        blockers.append("Official form-source observation is older than 30 days")
    if not documents:
        blockers.append("No supporting documents have been uploaded")
    if blocked_docs:
        blockers.append("A client-uploaded document remains quarantined or rejected")
    if any(item.status == "open" for item in issues):
        blockers.append("Unresolved evidence issues require review")
    if any(item.status == "open" for item in tasks):
        blockers.append("Open case tasks require review")
    if any(f.review_status == "pending" for f in facts):
        blockers.append("Unreviewed factual claims remain")
    if any(f.review_status == "verified" and not f.reviewed_by_sub for f in facts):
        blockers.append("A verified fact has no recorded human reviewer")
    if any(f.document_id is not None and f.document_id not in doc_by_id for f in facts):
        blockers.append("A fact points to a document outside this matter")
    if any(f.review_status == "verified" and f.document_id is None and
           f.field_path in {path for _, path in source.preview_fields} for f in facts):
        blockers.append("A verified mapped fact lacks a linked supporting document")

    eligible = {}
    for fact in facts:
        if fact.review_status != "verified" or not fact.reviewed_by_sub:
            continue
        if fact.document_id is None or (fact.document_id not in doc_by_id or
                                        fact.document_id in blocked_docs):
            continue
        eligible.setdefault(fact.field_path, []).append(fact)

    fields = []
    for label, path in source.preview_fields:
        candidates = eligible.get(path, [])
        distinct = {item.value.strip() for item in candidates}
        field_status = ("verified" if len(distinct) == 1 else
                        "ambiguous" if len(distinct) > 1 else "missing")
        if field_status != "verified":
            blockers.append(f"Required internal preview field {path}: {field_status}")
        fields.append({
            "label": label, "canonical_path": path,
            "value": next(iter(distinct)) if len(distinct) == 1 else None,
            "status": field_status,
            "fact_ids": sorted(str(f.id) for f in candidates),
            "document_ids": sorted({str(f.document_id) for f in candidates if f.document_id}),
        })

    # Invalidate an acknowledgement after ANY case fact/document/issue/task change,
    # including facts not currently covered by the partial form field registry.
    canonical_state = {
        "schema": PREFLIGHT_SCHEMA_VERSION,
        "case_id": str(case_id), "case_status": case.status,
        "source": source.code, "revision": source.revision_label,
        "source_observed_on": source.last_checked.isoformat(),
        "filing_context": source.filing_context,
        "facts": sorted([{
            "id": str(f.id), "path": f.field_path, "value": f.value,
            "status": f.review_status, "reviewer": f.reviewed_by_sub,
            "document_id": str(f.document_id) if f.document_id else None,
        } for f in facts], key=lambda x: x["id"]),
        "documents": sorted([{
            "id": str(d.id), "sha256": d.sha256,
            "scan": scan_by_id.get(d.id, "staff_upload_not_portal_scanned"),
        } for d in documents], key=lambda x: x["id"]),
        "issues": sorted([{"id": str(i.id), "status": i.status} for i in issues],
                         key=lambda x: x["id"]),
        "tasks": sorted([{"id": str(t.id), "status": t.status} for t in tasks],
                        key=lambda x: x["id"]),
    }
    # The case UUID makes the digest case-specific, avoiding reuse across matters.
    snapshot_sha256 = hashlib.sha256(json.dumps(
        canonical_state, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    return {
        **meta,
        "case_id": str(case_id),
        "snapshot_schema": PREFLIGHT_SCHEMA_VERSION,
        "snapshot_sha256": snapshot_sha256,
        "internal_preflight_status": "blocked" if blockers else "reviewable",
        "blockers": blockers,
        "fields": fields,
        "acknowledgement": "not_acknowledged",
        "release_status": "blocked_no_validated_ircc_pdf_adapter",
        "official_pdf_generation_supported": False,
        "submission_supported": False,
        "disclaimer": (
            "Internal review of a deliberately incomplete set of fields only. "
            "Acknowledgement does not establish immigration eligibility, complete "
            "form validation, authorized professional status or IRCC submission readiness."
        ),
    }


def _latest_ack(db: Session, org_id: UUID, case_id: UUID,
                code: str, filing_context: str):
    events = db.scalars(select(AuditEvent).where(
        AuditEvent.org_id == org_id, AuditEvent.resource_type == "case",
        AuditEvent.resource_id == case_id, AuditEvent.action == ACK_ACTION,
    ).order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc()).limit(300)).all()
    return next((event for event in events if
                 event.details.get("form_code") == code and
                 event.details.get("filing_context") == filing_context), None)


def _with_ack(db: Session, org_id: UUID, case_id: UUID, payload: dict) -> dict:
    last = _latest_ack(db, org_id, case_id, payload["code"], payload["filing_context"])
    if last is not None:
        payload["acknowledgement"] = (
            "current" if last.details.get("snapshot_sha256") == payload["snapshot_sha256"]
            and payload["internal_preflight_status"] == "reviewable" else "stale")
        payload["acknowledged_at"] = last.occurred_at.isoformat()
        payload["acknowledged_by_sub"] = last.actor_sub
    return payload


@router.get("/cases/{case_id}/forms/{form_code}/preflight")
def read_preflight(org_id: UUID, case_id: UUID, form_code: str,
                   filing_context: str = Query(min_length=3, max_length=40),
                   db: Session = Depends(get_db),
                   access: OrgAccess = Depends(get_org_access)):
    allow(access, READ_ROLES)
    case, source = _case_source(db, org_id, case_id, form_code, filing_context)
    return _with_ack(db, org_id, case_id, _snapshot(db, case, source))


@router.post("/cases/{case_id}/forms/{form_code}/preflight/acknowledge")
def acknowledge_preflight(org_id: UUID, case_id: UUID, form_code: str,
                          payload: AcknowledgeInput,
                          filing_context: str = Query(min_length=3, max_length=40),
                          db: Session = Depends(get_db),
                          access: OrgAccess = Depends(get_org_access)):
    allow(access, REVIEW_ROLES)
    # Locks case row during snapshot generation and audit insertion.
    case, source = _case_source(db, org_id, case_id, form_code, filing_context, lock=True)
    result = _snapshot(db, case, source)
    if payload.snapshot_sha256 != result["snapshot_sha256"]:
        raise HTTPException(status_code=409, detail="The reviewed evidence snapshot has changed")
    if result["internal_preflight_status"] != "reviewable":
        raise HTTPException(status_code=409, detail="Internal preflight blockers must be resolved")
    current = _latest_ack(db, org_id, case_id, source.code, source.filing_context)
    if current and current.details.get("snapshot_sha256") == result["snapshot_sha256"]:
        return _with_ack(db, org_id, case_id, result)

    from app.main import record_event
    record_event(db, access, ACK_ACTION, "case", case_id, {
        "form_code": source.code,
        "filing_context": source.filing_context,
        "snapshot_sha256": result["snapshot_sha256"],
        "schema": PREFLIGHT_SCHEMA_VERSION,
    })
    db.commit()
    # PostgreSQL set_config(..., true) only applies to the previous transaction.
    # A new SELECT after commit MUST restore the principal + tenant context,
    # otherwise RLS will silently hide the just-inserted acknowledgement.
    set_db_context(db, access.principal.sub, org_id)
    return _with_ack(db, org_id, case_id, result)
