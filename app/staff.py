"""Verified-email RCIC staff onboarding with one-time tokens and safe role controls.

Manual delivery only; no email/SMS service, licence verification or user
creation in Keycloak is implemented. All data in this release is synthetic.
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.access import OrgAccess, allow, get_org_access
from app.auth import Principal, get_principal
from app.db import get_db, set_db_context
from app.main import record_event
from app.models import Membership
from app.portal import authenticated_email, db_verified_email
from app.schemas import Role
from app.staff_models import StaffInvitation

router = APIRouter(prefix="/api/v1/orgs/{org_id}/staff", tags=["staff-onboarding"])
claim_router = APIRouter(prefix="/api/v1/staff", tags=["staff-invite-accept"])
MANAGERS = {Role.owner, Role.admin}
INVITABLE = {"admin", "consultant", "assistant", "viewer"}


def now():
    return datetime.now(timezone.utc)


class InviteInput(BaseModel):
    email: str = Field(min_length=6, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    role: str = Field(pattern=r"^(admin|consultant|assistant|viewer)$")

    @field_validator("email")
    @classmethod
    def normalize(cls, value):
        return value.strip().casefold()


class InviteClaim(BaseModel):
    token: str = Field(min_length=48, max_length=256)


class StaffRoleChange(BaseModel):
    role: str = Field(pattern=r"^(admin|consultant|assistant|viewer)$")


def _invite_data(entry: StaffInvitation):
    ts = now()
    state = ("accepted" if entry.accepted_at else
             "revoked" if entry.revoked_at else
             "expired" if _utc(entry.expires_at) <= ts else "pending")
    return {
        "id": str(entry.id), "email": entry.invited_email, "role": entry.role,
        "status": state, "created_at": entry.created_at, "expires_at": entry.expires_at,
        "accepted_at": entry.accepted_at, "revoked_at": entry.revoked_at,
        "delivery": "manual_only", "email_sent": False,
    }


@router.get("/members")
def list_members(org_id: UUID, db: Session = Depends(get_db),
                 access: OrgAccess = Depends(get_org_access)):
    allow(access, MANAGERS)
    members = db.scalars(select(Membership).where(
        Membership.org_id == org_id).order_by(Membership.created_at, Membership.id)).all()
    return [{"subject": m.subject, "role": m.role, "active": m.is_active,
             "verified_email": m.verified_email,
             "created_at": m.created_at} for m in members]


@router.get("/invitations")
def list_invitations(org_id: UUID, db: Session = Depends(get_db),
                     access: OrgAccess = Depends(get_org_access)):
    allow(access, MANAGERS)
    invites = db.scalars(select(StaffInvitation).where(
        StaffInvitation.org_id == org_id).order_by(
            StaffInvitation.created_at.desc()).limit(100)).all()
    return {"items": [_invite_data(i) for i in invites],
            "manual_secure_delivery_required": True,
            "outbound_email_enabled": False}


@router.post("/invitations", status_code=201)
def issue_invitation(org_id: UUID, payload: InviteInput,
                     db: Session = Depends(get_db),
                     access: OrgAccess = Depends(get_org_access)):
    allow(access, MANAGERS)
    if payload.role == "admin" and access.role != Role.owner:
        raise HTTPException(403, "Only a firm owner may invite an administrator")
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        # Serialize competing issuers for the same organization/email. Without
        # this, concurrent managers can create multiple live tokens.
        db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                   {"key": f"staff-invite:{org_id}:{payload.email}"})
    known = db.scalar(select(Membership.id).where(
        Membership.org_id == org_id,
        func.lower(Membership.verified_email) == payload.email))
    if known is not None:
        raise HTTPException(409, "Email already associated with a firm member")
    pending = db.scalar(select(StaffInvitation.id).where(
        StaffInvitation.org_id == org_id,
        StaffInvitation.invited_email == payload.email,
        StaffInvitation.accepted_at.is_(None),
        StaffInvitation.revoked_at.is_(None),
        StaffInvitation.expires_at > now(),
    ).limit(1))
    if pending is not None:
        raise HTTPException(409, "A live invitation already exists for that email")
    # No purpose, tenant or role is encoded in the token. Only its digest is saved.
    token = secrets.token_urlsafe(48)
    expiry = now() + timedelta(hours=72)
    entry = StaffInvitation(org_id=org_id, invited_email=payload.email,
                            role=payload.role,
                            token_hash=hashlib.sha256(token.encode()).hexdigest(),
                            created_by_sub=access.principal.sub, expires_at=expiry)
    db.add(entry)
    db.flush()
    record_event(db, access, "staff.invitation_created", "staff_invitation", entry.id,
                 {"role": payload.role, "delivery": "manual"})
    db.commit()
    return {"id": str(entry.id), "token": token, "expires_at": expiry,
            "role": entry.role, "email": entry.invited_email,
            "warning": "Shown once. Deliver via an approved private channel; no email was sent.",
            "email_sent": False}


@router.post("/invitations/{invitation_id}/revoke")
def revoke_invitation(org_id: UUID, invitation_id: UUID,
                      db: Session = Depends(get_db),
                      access: OrgAccess = Depends(get_org_access)):
    allow(access, MANAGERS)
    invitation = db.scalar(select(StaffInvitation).where(
        StaffInvitation.org_id == org_id,
        StaffInvitation.id == invitation_id).with_for_update())
    if invitation is None:
        raise HTTPException(404, "Invitation not found")
    if invitation.role == "admin" and access.role != Role.owner:
        raise HTTPException(403, "Only a firm owner may revoke an admin invitation")
    if invitation.revoked_at or invitation.accepted_at:
        raise HTTPException(409, "Invitation is already finalized")
    invitation.revoked_by_sub = access.principal.sub
    invitation.revoked_at = now()
    record_event(db, access, "staff.invitation_revoked", "staff_invitation", invitation.id)
    db.commit()
    return {"status": "revoked", "id": str(invitation.id)}


@claim_router.post("/invitations/accept")
def accept_invitation(payload: InviteClaim, db: Session = Depends(get_db),
                      principal: Principal = Depends(get_principal)):
    verified_email = db_verified_email(db, principal)
    digest = hashlib.sha256(payload.token.encode()).hexdigest()
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        # Function holds invitation row lock; bypasses member INSERT RLS
        # but makes no grant if email, expiry, replay or identity are invalid.
        try:
            found = db.execute(text(
                "SELECT org_id, invitation_id, assigned_role "
                "FROM ios_accept_staff_invitation(:digest)"
            ), {"digest": digest}).one_or_none()
            if found is None:
                raise HTTPException(404, "Invitation invalid, expired, or already used")
            org_id, invite_id, role = found
            set_db_context(db, principal.sub, org_id)
            record_event(db, OrgAccess(org_id, principal, Role(role)),
                         "staff.invitation_accepted", "staff_invitation", invite_id,
                         {"role": role, "identity_verified": True})
            db.commit()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "Firm member identity is already enrolled") from None
    else:
        entry = db.scalar(select(StaffInvitation).where(
            StaffInvitation.token_hash == digest,
            StaffInvitation.invited_email == verified_email).with_for_update())
        if (entry is None or entry.revoked_at or entry.accepted_at
                or _utc(entry.expires_at) <= now()):
            raise HTTPException(404, "Invitation invalid, expired, or already used")
        already = db.scalar(select(Membership.id).where(
            Membership.org_id == entry.org_id,
            (Membership.subject == principal.sub) |
            (func.lower(Membership.verified_email) == verified_email)))
        if already:
            raise HTTPException(409, "Firm member identity is already enrolled")
        try:
            membership = Membership(org_id=entry.org_id, subject=principal.sub,
                                    role=entry.role, verified_email=verified_email,
                                    is_active=True)
            db.add(membership)
            db.flush()
            entry.accepted_by_sub = principal.sub
            entry.accepted_at = now()
            record_event(db, OrgAccess(entry.org_id, principal, Role(entry.role)),
                         "staff.invitation_accepted", "staff_invitation", entry.id,
                         {"role": entry.role, "identity_verified": True})
            db.commit()
            org_id, invite_id, role = entry.org_id, entry.id, entry.role
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "Firm member identity is already enrolled") from None
    return {"org_id": str(org_id), "role": role,
            "status": "joined", "invitation_id": str(invite_id),
            "email_sent": False, "current_rcic_licence_verified": False}


def _utc(value: datetime):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _target(db, org_id, sub):
    return db.scalar(select(Membership).where(
        Membership.org_id == org_id, Membership.subject == sub).with_for_update())


@router.post("/members/{subject}/role")
def change_role(org_id: UUID, subject: str, payload: StaffRoleChange,
                db: Session = Depends(get_db),
                access: OrgAccess = Depends(get_org_access)):
    allow(access, MANAGERS)
    if subject == access.principal.sub:
        raise HTTPException(403, "Cannot change your own access role")
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        permitted = bool(db.scalar(text(
            "SELECT ios_change_staff_role(:org, :subject, :role)"
        ), {"org": org_id, "subject": subject, "role": payload.role}))
    else:
        target = _target(db, org_id, subject)
        permitted = bool(
            target and target.is_active and target.role != "owner" and
            (target.role != "admin" and payload.role != "admin" or
             access.role == Role.owner))
        if permitted:
            target.role = payload.role
    if not permitted:
        raise HTTPException(403, "Role change not permitted for that member")
    record_event(db, access, "staff.role_changed", "organization", org_id,
                 {"subject": subject, "new_role": payload.role})
    db.commit()
    return {"subject": subject, "role": payload.role, "status": "changed"}


@router.post("/members/{subject}/revoke")
def revoke_member(org_id: UUID, subject: str,
                  db: Session = Depends(get_db),
                  access: OrgAccess = Depends(get_org_access)):
    allow(access, MANAGERS)
    if subject == access.principal.sub:
        raise HTTPException(403, "Cannot deactivate your own membership")
    if db.bind is not None and db.bind.dialect.name == "postgresql":
        permitted = bool(db.scalar(text(
            "SELECT ios_revoke_staff(:org, :subject)"
        ), {"org": org_id, "subject": subject}))
    else:
        target = _target(db, org_id, subject)
        permitted = bool(
            target and target.is_active and target.role != "owner" and
            (target.role != "admin" or access.role == Role.owner))
        if permitted:
            target.is_active = False
    if not permitted:
        raise HTTPException(403, "Member deactivation not permitted")
    record_event(db, access, "staff.member_deactivated", "organization", org_id,
                 {"subject": subject})
    db.commit()
    return {"subject": subject, "active": False, "access_revoked": True}
