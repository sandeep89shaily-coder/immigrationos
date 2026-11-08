"""Controlled history correction linked to one reviewed client timeline explanation.

Only a consultant can apply a correction, after an actual reviewed reply.
An immutable ledger freezes both versions. No CaseFact is verified.
"""
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.access import OrgAccess, allow, get_org_access
from app.applicant_history import ADAPTERS, _validated_details
from app.applicant_history_models import ApplicantHistory
from app.db import get_db
from app.history_timeline_audit import KINDS, audit_history_timeline
from app.main import record_event
from app.schemas import Role
from app.timeline_clarification_models import (
    TimelineClarification, TimelineClarificationReply, TimelineClarificationDecision)
from app.timeline_clarifications import _lock, _case
from app.timeline_history_correction_models import TimelineHistoryCorrection

router = APIRouter(
    prefix="/api/v1/orgs/{org_id}/cases/{case_id}/timeline-clarifications",
    tags=["timeline-history-corrections"])
REVIEWERS = {Role.owner, Role.admin, Role.consultant}


class ApplyCorrection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: str = Field(pattern=r"^(create|update)$")
    record_id: UUID | None = None
    expected_version: int | None = Field(default=None, ge=1)
    details: dict = Field(min_length=2, max_length=12)
    correction_reason: str = Field(min_length=12, max_length=600)

    @model_validator(mode="after")
    def operation_parameters(self):
        if self.operation == "update":
            if self.record_id is None or self.expected_version is None:
                raise ValueError("Record ID and current version required for update")
        elif self.record_id is not None or self.expected_version is not None:
            raise ValueError("New records must not specify an existing record ID/version")
        return self


@router.get("/history-corrections")
def list_corrections(org_id: UUID, case_id: UUID, response: Response,
                     db: Session = Depends(get_db),
                     access: OrgAccess = Depends(get_org_access)):
    allow(access, REVIEWERS | {Role.assistant})
    _case(db, org_id, case_id)
    rows = db.scalars(select(TimelineHistoryCorrection).where(
        TimelineHistoryCorrection.org_id == org_id,
        TimelineHistoryCorrection.case_id == case_id
    ).order_by(TimelineHistoryCorrection.created_at.desc(),
               TimelineHistoryCorrection.id.desc()).limit(100)).all()
    response.headers["Cache-Control"] = "no-store"
    return {"corrections": [{
        "id": str(row.id), "request_id": str(row.request_id),
        "record_id": str(row.record_id), "operation": row.operation,
        "kind": row.kind, "prior_version": row.prior_version,
        "new_version": row.new_version, "prior_details": row.prior_details,
        "new_details": row.new_details, "correction_reason": row.correction_reason,
        "created_by_sub": row.created_by_sub, "created_at": row.created_at
    } for row in rows], "verified_evidence": False, "official_form_ready": False}


@router.post("/{request_id}/history-correction", status_code=201)
def apply_correction(org_id: UUID, case_id: UUID, request_id: UUID,
                     payload: ApplyCorrection, db: Session = Depends(get_db),
                     access: OrgAccess = Depends(get_org_access)):
    allow(access, REVIEWERS)
    _lock(db, org_id, case_id)
    case = _case(db, org_id, case_id)
    if case.status == "closed":
        raise HTTPException(409, "Closed cases cannot apply corrections")
    request = db.scalar(select(TimelineClarification).where(
        TimelineClarification.org_id == org_id,
        TimelineClarification.case_id == case_id,
        TimelineClarification.id == request_id))
    if request is None:
        raise HTTPException(404, "Clarification not found")
    reply = db.scalar(select(TimelineClarificationReply).where(
        TimelineClarificationReply.org_id == org_id,
        TimelineClarificationReply.case_id == case_id,
        TimelineClarificationReply.request_id == request_id))
    review = db.scalar(select(TimelineClarificationDecision).where(
        TimelineClarificationDecision.org_id == org_id,
        TimelineClarificationDecision.case_id == case_id,
        TimelineClarificationDecision.request_id == request_id))
    if reply is None or review is None or review.decision != "reviewed":
        raise HTTPException(409, "An answered, reviewed clarification is required")
    if db.scalar(select(TimelineHistoryCorrection.id).where(
        TimelineHistoryCorrection.org_id == org_id,
        TimelineHistoryCorrection.request_id == request_id)) is not None:
        raise HTTPException(409, "Correction already linked to this clarification")
    if request.kind not in KINDS:
        raise HTTPException(409, "Unsupported clarification history category")

    history = db.scalars(select(ApplicantHistory).where(
        ApplicantHistory.org_id == org_id,
        ApplicantHistory.client_id == case.client_id,
        ApplicantHistory.kind.in_(KINDS))).all()
    audit = audit_history_timeline(
        records=history, org_id=org_id, client_id=case.client_id,
        start=date.fromisoformat(request.window_start),
        end=date.fromisoformat(request.window_end))
    if audit["snapshot_sha256"] != request.snapshot_sha256:
        raise HTTPException(409, "History changed since clarification was requested; re-audit")
    flag = next((f for f in audit["categories"][request.kind]["flags"]
                 if f["flag_sha256"] == request.flag_sha256), None)
    if flag is None:
        raise HTTPException(409, "Original timeline finding is no longer present")
    if payload.operation == "create" and flag["type"] != "uncovered_period_for_review":
        raise HTTPException(409, "Only uncovered periods permit new linked history records")
    if payload.operation == "update" and str(payload.record_id) not in flag["record_ids"]:
        raise HTTPException(409, "Correction target must be a record in the flagged period")

    updated = _validated_details(ADAPTERS[request.kind], payload.details)
    if payload.operation == "create":
        new_start = date.fromisoformat(updated["start_date"])
        new_end = date.fromisoformat(updated["end_date"]) if updated.get("end_date") else None
        if new_end is None or new_end < date.fromisoformat(flag["start_date"]) or (
            new_start > date.fromisoformat(flag["end_date"])):
            raise HTTPException(422, "New history interval must overlap the flagged gap and have an end date")
        duplicates = [r for r in history if r.kind == request.kind and r.details == updated]
        if duplicates:
            raise HTTPException(409, "Identical history record already exists")
        row = ApplicantHistory(org_id=org_id, client_id=case.client_id,
                               kind=request.kind, details=updated,
                               updated_by_sub=access.principal.sub)
        db.add(row)
        db.flush()
        prior_details = None
        previous_version = None
    else:
        row = db.scalar(select(ApplicantHistory).where(
            ApplicantHistory.org_id == org_id,
            ApplicantHistory.client_id == case.client_id,
            ApplicantHistory.id == payload.record_id,
            ApplicantHistory.kind == request.kind).with_for_update())
        if row is None:
            raise HTTPException(404, "Flagged applicant history record not found")
        if row.version != payload.expected_version:
            raise HTTPException(409, "History changed; reload before correction")
        if row.details == updated:
            raise HTTPException(409, "Proposed correction does not change history")
        prior_details = dict(row.details)
        previous_version = row.version
        row.details = updated
        row.version += 1
        row.updated_by_sub = access.principal.sub
        db.flush()
    ledger = TimelineHistoryCorrection(
        org_id=org_id, case_id=case_id, client_id=case.client_id,
        request_id=request.id, reply_id=reply.id, decision_id=review.id,
        record_id=row.id, operation=payload.operation, kind=request.kind,
        prior_version=previous_version, new_version=row.version,
        prior_details=prior_details, new_details=updated,
        correction_reason=payload.correction_reason.strip(),
        created_by_sub=access.principal.sub)
    db.add(ledger)
    db.flush()
    record_event(db, access, "timeline.history_corrected", "timeline_history_correction",
                 ledger.id, {"request_id": str(request.id), "record_id": str(row.id),
                             "operation": payload.operation,
                             "prior_version": previous_version, "new_version": row.version})
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "History correction already recorded or conflicting") from None
    return {"correction_id": str(ledger.id), "record_id": str(row.id),
            "prior_version": previous_version, "new_version": row.version,
            "correction_reason_recorded": True,
            "verified_evidence": False, "official_form_ready": False}
