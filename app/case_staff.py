"""Revocable assistant access to an engagement-linked, supervised case.

Only firm owners/admins or the designated primary consultant can invite an
existing ACTIVE assistant member to the specific case. No unverified people
are given access through arbitrary email addresses.
"""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.access import OrgAccess, allow, get_org_access
from app.case_scope import MANAGERS, active_staff_member, current_signed_engagement
from app.case_scope_models import CaseAccessGrant
from app.db import get_db
from app.engagement_models import MatterAssignment
from app.main import record_event
from app.models import Case, Membership
from app.schemas import Role

router = APIRouter(prefix="/api/v1/orgs/{org_id}/cases/{case_id}/staff", tags=["case-staff-scope"])


class GrantInput(BaseModel):
    subject: str = Field(min_length=3, max_length=255)
    scope: str = Field(pattern=r"^(read|intake)$")


def _manager(db, access, case_id):
    if access.role in MANAGERS:
        return
    if access.role != Role.consultant:
        raise HTTPException(403, "Only a manager or primary assigned consultant can manage case staff")
    primary = db.scalar(select(MatterAssignment.id).where(
        MatterAssignment.org_id == access.org_id,
        MatterAssignment.case_id == case_id,
        MatterAssignment.professional_sub == access.principal.sub,
    ))
    if primary is None:
        raise HTTPException(403, "Only the primary assigned consultant can manage case staff")


@router.get("/grants")
def list_grants(org_id: UUID, case_id: UUID,
                db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    _manager(db, access, case_id)
    rows = db.scalars(select(CaseAccessGrant).where(
        CaseAccessGrant.org_id == org_id, CaseAccessGrant.case_id == case_id
    ).order_by(CaseAccessGrant.created_at.desc()).limit(100)).all()
    return [{"id": str(x.id), "subject": x.subject, "scope": x.scope,
             "created_at": x.created_at, "revoked_at": x.revoked_at,
             "granted_by_sub": x.granted_by_sub, "revoked_by_sub": x.revoked_by_sub}
            for x in rows]


@router.post("/grants", status_code=201)
def grant_assistant(org_id: UUID, case_id: UUID, payload: GrantInput,
                    db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    _manager(db, access, case_id)
    case = db.scalar(select(Case).where(Case.org_id == org_id, Case.id == case_id).with_for_update())
    if case is None:
        raise HTTPException(404, "Case not found")
    if case.status == "closed":
        raise HTTPException(409, "Cannot grant access to closed cases")
    if not current_signed_engagement(db, case):
        raise HTTPException(409, "Case needs current reviewed service agreement before staff assignment")
    if not active_staff_member(db, org_id, payload.subject, ("assistant",)):
        raise HTTPException(422, "Assignee must be an active assistant in this firm")
    existing = db.scalar(select(CaseAccessGrant.id).where(
        CaseAccessGrant.org_id == org_id, CaseAccessGrant.case_id == case_id,
        CaseAccessGrant.subject == payload.subject,
        CaseAccessGrant.revoked_at.is_(None),
    ))
    if existing is not None:
        raise HTTPException(409, "Assistant already has active case access")
    grant = CaseAccessGrant(org_id=org_id, case_id=case_id, subject=payload.subject,
                            scope=payload.scope, granted_by_sub=access.principal.sub)
    try:
        db.add(grant)
        db.flush()
        record_event(db, access, "case.assistant_access_granted", "case_access_grant",
                     grant.id, {"case_id": str(case_id), "scope": grant.scope,
                                "assignee_subject": grant.subject})
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Another active grant already exists") from None
    return {"id": str(grant.id), "subject": grant.subject, "scope": grant.scope,
            "active": True, "permission_to_provide_legal_advice": False}


@router.post("/grants/{grant_id}/revoke")
def revoke_grant(org_id: UUID, case_id: UUID, grant_id: UUID,
                 db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    _manager(db, access, case_id)
    grant = db.scalar(select(CaseAccessGrant).where(
        CaseAccessGrant.org_id == org_id, CaseAccessGrant.case_id == case_id,
        CaseAccessGrant.id == grant_id).with_for_update())
    if grant is None:
        raise HTTPException(404, "Grant not found")
    if grant.revoked_at is not None:
        raise HTTPException(409, "Already revoked")
    grant.revoked_at = datetime.now(timezone.utc)
    grant.revoked_by_sub = access.principal.sub
    record_event(db, access, "case.assistant_access_revoked", "case_access_grant",
                 grant.id, {"case_id": str(case_id), "assignee_subject": grant.subject})
    db.commit()
    return {"id": str(grant.id), "revoked": True}
