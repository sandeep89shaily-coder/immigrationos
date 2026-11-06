"""Assigned, source-neutral prospect follow-ups and a visible overdue queue.

These are internal human tasks. A due date is never inferred from an IRCC
deadline and this module does not send email, SMS, or push reminders.
"""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.access import OrgAccess, READ_ROLES, allow, get_org_access
from app.crm import INTAKE, _event, _prospect
from app.crm_models import ProspectFollowUp
from app.db import get_db

router = APIRouter(prefix="/api/v1/orgs/{org_id}/crm", tags=["rcic-follow-ups"])


def now():
    return datetime.now(timezone.utc)


class CreateFollowUp(BaseModel):
    title: str = Field(min_length=4, max_length=180)
    due_at: datetime
    priority: str = Field(default="normal", pattern=r"^(normal|urgent)$")

    @model_validator(mode="after")
    def validate_due(self):
        self.title = self.title.strip()
        if len(self.title) < 4:
            raise ValueError("Follow-up title must not be blank")
        if self.due_at.tzinfo is None:
            raise ValueError("Follow-up due time requires explicit timezone offset")
        self.due_at = self.due_at.astimezone(timezone.utc)
        if not now() < self.due_at <= now() + timedelta(days=366*3):
            raise ValueError("Follow-up must be in the future, within three years")
        return self


def item(row: ProspectFollowUp) -> dict:
    # SQLite test timestamps may lose tzinfo; saved application dates are UTC.
    due_utc = (row.due_at.replace(tzinfo=timezone.utc) if row.due_at.tzinfo is None
               else row.due_at.astimezone(timezone.utc))
    return {
        "id": str(row.id), "prospect_id": str(row.prospect_id),
        "title": row.title, "status": row.status, "priority": row.priority,
        "due_at": row.due_at,
        "overdue": row.status == "open" and due_utc < now(),
        "assigned_to_sub": row.assigned_to_sub, "created_at": row.created_at,
        "completed_at": row.completed_at, "cancelled_at": row.cancelled_at,
        "delivery_mode": "internal_queue_only", "message_sent": False,
    }


@router.get("/follow-ups")
def list_firm_followups(
    org_id: UUID,
    status: str = Query("open", pattern=r"^(open|completed|cancelled|all)$"),
    overdue_only: bool = False,
    db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)
):
    allow(access, READ_ROLES)
    stmt = select(ProspectFollowUp).where(ProspectFollowUp.org_id == org_id)
    if status != "all":
        stmt = stmt.where(ProspectFollowUp.status == status)
    if overdue_only:
        stmt = stmt.where(ProspectFollowUp.status == "open", ProspectFollowUp.due_at < now())
    rows = db.scalars(stmt.order_by(ProspectFollowUp.due_at, ProspectFollowUp.id).limit(200)).all()
    return {"items": [item(row) for row in rows], "truncated_at": 200,
            "automated_reminders_enabled": False}


@router.get("/prospects/{prospect_id}/follow-ups")
def list_prospect_followups(
    org_id: UUID, prospect_id: UUID, db: Session = Depends(get_db),
    access: OrgAccess = Depends(get_org_access)
):
    allow(access, READ_ROLES)
    _prospect(db, org_id, prospect_id)
    rows = db.scalars(select(ProspectFollowUp).where(
        ProspectFollowUp.org_id == org_id, ProspectFollowUp.prospect_id == prospect_id
    ).order_by(ProspectFollowUp.due_at, ProspectFollowUp.id).limit(100)).all()
    return [item(row) for row in rows]


@router.post("/prospects/{prospect_id}/follow-ups", status_code=201)
def create_followup(
    org_id: UUID, prospect_id: UUID, payload: CreateFollowUp,
    db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)
):
    allow(access, INTAKE)
    prospect = _prospect(db, org_id, prospect_id, lock=True)
    if prospect.stage in ("closed", "converted"):
        raise HTTPException(409, "Cannot add follow-ups to an inactive prospect")
    duplicate = db.scalar(select(ProspectFollowUp.id).where(
        ProspectFollowUp.org_id == org_id,
        ProspectFollowUp.prospect_id == prospect_id,
        func.lower(ProspectFollowUp.title) == payload.title.casefold(),
        ProspectFollowUp.status == "open").limit(1))
    if duplicate is not None:
        raise HTTPException(409, "An open follow-up with this title already exists")
    task = ProspectFollowUp(
        org_id=org_id, prospect_id=prospect_id, title=payload.title,
        due_at=payload.due_at, priority=payload.priority, status="open",
        assigned_to_sub=access.principal.sub, created_by_sub=access.principal.sub)
    db.add(task)
    db.flush()
    _event(db, access, "crm.followup_created", "crm_followup", task.id,
           {"priority": task.priority, "delivery": "none"})
    db.commit()
    return item(task)


def _existing(db, org_id, prospect_id, followup_id, lock=True):
    q = select(ProspectFollowUp).where(
        ProspectFollowUp.org_id == org_id,
        ProspectFollowUp.prospect_id == prospect_id,
        ProspectFollowUp.id == followup_id,
    )
    row = db.scalar(q.with_for_update() if lock else q)
    if row is None:
        raise HTTPException(404, "Follow-up not found")
    return row


@router.post("/prospects/{prospect_id}/follow-ups/{followup_id}/complete")
def complete_followup(
    org_id: UUID, prospect_id: UUID, followup_id: UUID,
    db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)
):
    allow(access, INTAKE)
    _prospect(db, org_id, prospect_id)
    row = _existing(db, org_id, prospect_id, followup_id)
    if row.status != "open":
        raise HTTPException(409, "Follow-up already completed or cancelled")
    row.status = "completed"
    row.completed_at = now()
    row.completed_by_sub = access.principal.sub
    _event(db, access, "crm.followup_completed", "crm_followup", row.id)
    db.commit()
    return item(row)


@router.post("/prospects/{prospect_id}/follow-ups/{followup_id}/cancel")
def cancel_followup(
    org_id: UUID, prospect_id: UUID, followup_id: UUID,
    db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)
):
    allow(access, INTAKE)
    _prospect(db, org_id, prospect_id)
    row = _existing(db, org_id, prospect_id, followup_id)
    if row.status != "open":
        raise HTTPException(409, "Follow-up already completed or cancelled")
    row.status = "cancelled"
    row.cancelled_at = now()
    row.cancelled_by_sub = access.principal.sub
    _event(db, access, "crm.followup_cancelled", "crm_followup", row.id)
    db.commit()
    return item(row)
