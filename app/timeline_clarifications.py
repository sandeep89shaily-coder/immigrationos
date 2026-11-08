"""Case-specific timeline clarification workflow.

Requests are anchored to the actual audit findings and source fingerprint.
Client answers are immutable, not edits or evidence. Consultant decisions
are likewise immutable and cannot declare IRCC completeness.
"""
from datetime import date
from hashlib import sha256
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.access import OrgAccess, allow, get_org_access
from app.applicant_history_models import ApplicantHistory
from app.auth import Principal, get_principal
from app.db import get_db
from app.history_timeline_audit import KINDS, MAX_WINDOW_DAYS, audit_history_timeline
from app.main import record_event
from app.models import Case
from app.portal import active_grant, db_verified_email
from app.schemas import Role
from app.timeline_clarification_models import (
    TimelineClarification, TimelineClarificationReply, TimelineClarificationDecision,
)

staff = APIRouter(prefix="/api/v1/orgs/{org_id}/cases/{case_id}/timeline-clarifications",
                  tags=["staff-timeline-clarifications"])
client = APIRouter(prefix="/api/v1/client/cases/{case_id}/timeline-clarifications",
                   tags=["client-timeline-clarifications"])
REVIEWERS = {Role.owner, Role.admin, Role.consultant}
READERS = REVIEWERS | {Role.assistant}


class CreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start_date: date
    end_date: date
    kind: str
    flag_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    question: str = Field(min_length=12, max_length=600)


class Reply(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str = Field(min_length=10, max_length=1600)


class Decision(BaseModel):
    decision: str = Field(pattern=r"^(reviewed|needs_more_information)$")


def flag_digest(kind: str, flag: dict) -> str:
    return sha256(json.dumps({"kind": kind, "flag": {k: v for k, v in flag.items() if k != "flag_sha256"}},
                sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _lock(db, org, case):
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 1))"),
                   {"key": "timeline:" + str(org) + ":" + str(case)})


def _case(db, org, case_id):
    row = db.scalar(select(Case).where(Case.org_id == org, Case.id == case_id))
    if row is None:
        raise HTTPException(404, "Case not available")
    return row


def _requests(db, org, case_id):
    return db.scalars(select(TimelineClarification).where(
        TimelineClarification.org_id == org,
        TimelineClarification.case_id == case_id,
    ).order_by(TimelineClarification.created_at.desc(),
               TimelineClarification.id.desc()).limit(100)).all()


def _views(db, rows, *, client_mode=False):
    ids = [x.id for x in rows]
    replies = db.scalars(select(TimelineClarificationReply).where(
        TimelineClarificationReply.request_id.in_(ids))).all() if ids else []
    decisions = db.scalars(select(TimelineClarificationDecision).where(
        TimelineClarificationDecision.request_id.in_(ids))).all() if ids else []
    by_reply = {r.request_id: r for r in replies}
    by_decision = {d.request_id: d for d in decisions}
    out = []
    for row in rows:
        reply = by_reply.get(row.id)
        review = by_decision.get(row.id)
        out.append({
            "id": str(row.id), "kind": row.kind, "flag_type": row.flag_type,
            "question": row.question, "window_start": row.window_start,
            "window_end": row.window_end,
            "created_at": row.created_at,
            "has_reply": reply is not None,
            "reply": None if client_mode else reply.answer if reply else None,
            "decision": review.decision if review else None,
            "status": ("awaiting_client" if reply is None else
                       "awaiting_staff" if review is None else review.decision),
            "source_snapshot_sha256": row.snapshot_sha256,
            "official_form_ready": False,
        })
    return out


@staff.get("")
def list_staff(org_id: UUID, case_id: UUID, response: Response,
               db: Session = Depends(get_db),
               access: OrgAccess = Depends(get_org_access)):
    allow(access, READERS)
    _case(db, org_id, case_id)
    response.headers["Cache-Control"] = "no-store"
    return {"requests": _views(db, _requests(db, org_id, case_id)),
            "official_form_ready": False}


@client.get("")
def list_client(case_id: UUID, response: Response,
                db: Session = Depends(get_db),
                principal: Principal = Depends(get_principal)):
    db_verified_email(db, principal)
    grant = active_grant(db, principal, case_id)
    _case(db, grant.org_id, case_id)
    response.headers["Cache-Control"] = "no-store"
    return {"requests": _views(db, _requests(db, grant.org_id, case_id),
                                client_mode=True),
            "official_form_ready": False}


@staff.post("", status_code=201)
def create_request(org_id: UUID, case_id: UUID, payload: CreateRequest,
                   db: Session = Depends(get_db),
                   access: OrgAccess = Depends(get_org_access)):
    allow(access, REVIEWERS)
    _lock(db, org_id, case_id)
    case = _case(db, org_id, case_id)
    if case.status == "closed":
        raise HTTPException(409, "Closed case cannot request clarification")
    if payload.kind not in KINDS or payload.end_date < payload.start_date or (
        payload.end_date - payload.start_date).days > MAX_WINDOW_DAYS:
        raise HTTPException(422, "Invalid timeline window or category")
    rows = db.scalars(select(ApplicantHistory).where(
        ApplicantHistory.org_id == org_id,
        ApplicantHistory.client_id == case.client_id,
        ApplicantHistory.kind.in_(KINDS))).all()
    audit = audit_history_timeline(records=rows, client_id=case.client_id,
                                   org_id=org_id, start=payload.start_date,
                                   end=payload.end_date)
    if audit["snapshot_sha256"] != payload.snapshot_sha256:
        raise HTTPException(409, "History changed; refresh timeline audit")
    flag = next((f for f in audit["categories"][payload.kind]["flags"]
                 if flag_digest(payload.kind, f) == payload.flag_sha256), None)
    if flag is None:
        raise HTTPException(409, "Flag no longer exists in current timeline")
    existing = db.scalars(select(TimelineClarification).where(
        TimelineClarification.org_id == org_id,
        TimelineClarification.case_id == case_id,
        TimelineClarification.snapshot_sha256 == payload.snapshot_sha256,
        TimelineClarification.flag_sha256 == payload.flag_sha256)).all()
    if existing:
        raise HTTPException(409, "Clarification already requested for this flag")
    item = TimelineClarification(
        org_id=org_id, case_id=case_id, kind=payload.kind,
        flag_type=flag["type"], flag_sha256=payload.flag_sha256,
        snapshot_sha256=payload.snapshot_sha256,
        window_start=payload.start_date.isoformat(),
        window_end=payload.end_date.isoformat(), question=payload.question.strip(),
        created_by_sub=access.principal.sub)
    db.add(item)
    db.flush()
    record_event(db, access, "timeline.clarification_requested",
                 "timeline_clarification", item.id,
                 {"kind": item.kind, "flag_type": item.flag_type})
    db.commit()
    return {"id": str(item.id), "status": "awaiting_client",
            "official_form_ready": False}


@client.post("/{request_id}/reply", status_code=201)
def client_reply(case_id: UUID, request_id: UUID, payload: Reply,
                 db: Session = Depends(get_db),
                 principal: Principal = Depends(get_principal)):
    db_verified_email(db, principal)
    grant = active_grant(db, principal, case_id)
    _lock(db, grant.org_id, case_id)
    case = _case(db, grant.org_id, case_id)
    if case.status == "closed":
        raise HTTPException(409, "Closed case cannot accept clarifications")
    req = db.scalar(select(TimelineClarification).where(
        TimelineClarification.org_id == grant.org_id,
        TimelineClarification.case_id == case_id,
        TimelineClarification.id == request_id))
    if req is None:
        raise HTTPException(404, "Clarification not found")
    previous = db.scalar(select(TimelineClarificationReply.id).where(
        TimelineClarificationReply.org_id == grant.org_id,
        TimelineClarificationReply.case_id == case_id,
        TimelineClarificationReply.request_id == request_id))
    if previous:
        raise HTTPException(409, "Already replied; ask the consultant for a new request")
    reply = TimelineClarificationReply(
        org_id=grant.org_id, case_id=case_id, request_id=request_id,
        answer=payload.answer.strip(), answered_by_sub=principal.sub)
    db.add(reply)
    db.flush()
    record_event(db, OrgAccess(grant.org_id, principal, Role.viewer),
                 "portal.timeline_clarification_replied",
                 "timeline_clarification_reply", reply.id,
                 {"request_id": str(request_id)})
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Clarification already answered") from None
    return {"id": str(reply.id), "status": "awaiting_staff",
            "master_history_updated": False, "verified_evidence": False}


@staff.post("/{request_id}/decide", status_code=201)
def staff_decide(org_id: UUID, case_id: UUID, request_id: UUID,
                 payload: Decision, db: Session = Depends(get_db),
                 access: OrgAccess = Depends(get_org_access)):
    allow(access, REVIEWERS)
    _lock(db, org_id, case_id)
    case = _case(db, org_id, case_id)
    if case.status == "closed":
        raise HTTPException(409, "Closed case cannot record review")
    req = db.scalar(select(TimelineClarification).where(
        TimelineClarification.org_id == org_id,
        TimelineClarification.case_id == case_id,
        TimelineClarification.id == request_id))
    if req is None:
        raise HTTPException(404, "Clarification not found")
    reply = db.scalar(select(TimelineClarificationReply.id).where(
        TimelineClarificationReply.org_id == org_id,
        TimelineClarificationReply.case_id == case_id,
        TimelineClarificationReply.request_id == request_id))
    if reply is None:
        raise HTTPException(409, "Client has not replied")
    prior = db.scalar(select(TimelineClarificationDecision.id).where(
        TimelineClarificationDecision.org_id == org_id,
        TimelineClarificationDecision.case_id == case_id,
        TimelineClarificationDecision.request_id == request_id))
    if prior:
        raise HTTPException(409, "Clarification already reviewed")
    decision = TimelineClarificationDecision(
        org_id=org_id, case_id=case_id, request_id=request_id,
        decision=payload.decision, reviewed_by_sub=access.principal.sub)
    db.add(decision)
    db.flush()
    record_event(db, access, "timeline.clarification_reviewed",
                 "timeline_clarification", request_id,
                 {"decision": payload.decision})
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Already reviewed") from None
    return {"decision": decision.decision, "master_history_updated": False,
            "verified_evidence": False, "official_form_ready": False}
