"""Client-submitted repeatable family/history entries; consultant-reviewed import.

Client claims are never independent evidence. Staff acceptance creates an
unverified master family/history record, never a verified CaseFact.
"""
from hashlib import sha256
from datetime import date
from typing import Literal
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.access import OrgAccess, allow, get_org_access
from app.applicant_history import ADAPTERS, _validated_details
from app.applicant_history_models import ApplicantHistory
from app.applicant_supplemental_history_models import ApplicantSupplementalHistory
from app.applicant_models import FamilyMember
from app.applicant_profiles import RelativeInput
from app.auth import Principal, get_principal
from app.db import get_db
from app.main import record_event
from app.portal import active_grant, db_verified_email
from app.repeatable_intake_models import ClientRepeatableProposal, ClientRepeatableDecision
from app.schemas import Role
from app.study_intake import NOTICE_VERSION, study_case

VERSION = "repeatable-preliminary-2026-11-08-v2"
KINDS = ("family", "address", "education", "employment", "travel",
         "previous_relationship", "foreign_residence")
client_router = APIRouter(prefix="/api/v1/client/cases/{case_id}/repeatables",
                          tags=["client-repeatable-intake"])
staff_router = APIRouter(prefix="/api/v1/orgs/{org_id}/cases/{case_id}/repeatables",
                         tags=["staff-repeatable-intake"])
READ = {Role.owner, Role.admin, Role.consultant, Role.assistant}
REVIEW = {Role.owner, Role.admin, Role.consultant}


class PreviousRelationship(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    relationship_type: Literal["married", "common_law"]
    family_name: str = Field(min_length=1, max_length=100)
    given_name: str = Field(min_length=1, max_length=100)
    date_of_birth: date | None = None
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def valid_period(self):
        if self.end_date < self.start_date:
            raise ValueError("Relationship end precedes start")
        return self


class ForeignResidence(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    country: str = Field(min_length=1, max_length=100)
    status: Literal["citizen", "permanent_resident", "visitor", "worker",
                    "student", "other", "protected_person", "refugee_claimant",
                    "foreign_national"]
    status_other: str | None = Field(default=None, min_length=1, max_length=160)
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def valid_residence(self):
        if self.end_date < self.start_date:
            raise ValueError("Residence end precedes start")
        if self.status == "other" and not self.status_other:
            raise ValueError("Other immigration status needs explanation")
        if self.status != "other" and self.status_other is not None:
            raise ValueError("Other-status explanation is not active")
        return self


SUPPLEMENTAL_ADAPTERS = {
    "previous_relationship": PreviousRelationship,
    "foreign_residence": ForeignResidence,
}


class ProposalInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    template_version: str = Field(min_length=5, max_length=80)
    acknowledged_notice: bool
    kind: str
    details: dict = Field(min_length=2, max_length=12)


class DecisionInput(BaseModel):
    decision: str = Field(pattern=r"^(accept|dismiss)$")


def normalized(kind: str, details: dict) -> dict:
    if kind == "family":
        try:
            return RelativeInput.model_validate(details).model_dump(
                mode="json", exclude_none=True)
        except ValidationError:
            raise HTTPException(422, "Invalid family member details") from None
    if kind in SUPPLEMENTAL_ADAPTERS:
        try:
            return SUPPLEMENTAL_ADAPTERS[kind].model_validate(details).model_dump(
                mode="json", exclude_none=True)
        except ValidationError:
            raise HTTPException(422, "Invalid supplemental history details or dates") from None
    if kind not in ADAPTERS:
        raise HTTPException(422, "Unsupported repeatable record category")
    return _validated_details(ADAPTERS[kind], details)


def _record_view(p: ClientRepeatableProposal, decision=None, *, show_details=True):
    return {
        "id": str(p.id), "kind": p.kind,
        "details": p.details if show_details else None,
        "created_at": p.created_at,
        "content_sha256": p.content_sha256,
        "review_status": decision.decision if decision else "pending",
        "created_record_id": str(decision.created_record_id)
        if decision and decision.created_record_id else None,
        "reviewed_by_sub": decision.reviewed_by_sub if decision else None,
        "verified_evidence": False, "official_form_complete": False,
    }


@client_router.get("")
def read_client_repeatables(case_id: UUID, response: Response,
                            db: Session = Depends(get_db),
                            principal: Principal = Depends(get_principal)):
    db_verified_email(db, principal)
    grant = active_grant(db, principal, case_id)
    study_case(db, grant.org_id, case_id)
    rows = db.scalars(select(ClientRepeatableProposal).where(
        ClientRepeatableProposal.org_id == grant.org_id,
        ClientRepeatableProposal.case_id == case_id,
        ClientRepeatableProposal.created_by_sub == principal.sub
    ).order_by(ClientRepeatableProposal.created_at.desc(),
               ClientRepeatableProposal.id.desc()).limit(100)).all()
    response.headers["Cache-Control"] = "no-store"
    return {"template_version": VERSION, "categories": list(KINDS),
            "proposals": [_record_view(row, show_details=False) for row in rows],
            "notice": "Development-only fictional data. Client records require staff review and supporting evidence.",
            "official_form_complete": False, "submission_supported": False}


@client_router.post("", status_code=201)
def submit_client_repeatable(case_id: UUID, payload: ProposalInput,
                             db: Session = Depends(get_db),
                             principal: Principal = Depends(get_principal)):
    db_verified_email(db, principal)
    grant = active_grant(db, principal, case_id)
    case = study_case(db, grant.org_id, case_id, lock=True)
    if case.status == "closed":
        raise HTTPException(409, "Closed matters cannot accept new entries")
    if payload.template_version != VERSION:
        raise HTTPException(409, "Repeatable questionnaire version changed")
    if payload.acknowledged_notice is not True:
        raise HTTPException(422, "Development data-use notice must be acknowledged")
    data = normalized(payload.kind, payload.details)
    digest = sha256(json.dumps({"kind": payload.kind, "details": data},
                               sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    # An identical re-submission is a separate immutable event, but exact
    # duplicates from one portal user should not flood the review queue.
    previous = db.scalar(select(ClientRepeatableProposal.id).where(
        ClientRepeatableProposal.org_id == grant.org_id,
        ClientRepeatableProposal.case_id == case_id,
        ClientRepeatableProposal.created_by_sub == principal.sub,
        ClientRepeatableProposal.content_sha256 == digest).limit(1))
    if previous is not None:
        raise HTTPException(409, "An identical entry has already been submitted")
    p = ClientRepeatableProposal(
        org_id=grant.org_id, case_id=case_id, kind=payload.kind,
        details=data, content_sha256=digest, template_version=VERSION,
        notice_version=NOTICE_VERSION, created_by_sub=principal.sub)
    db.add(p)
    db.flush()
    record_event(db, OrgAccess(grant.org_id, principal, Role.viewer),
                 "portal.repeatable_proposal_submitted", "client_repeatable_proposal",
                 p.id, {"kind": p.kind, "template_version": VERSION})
    db.commit()
    return {"id": str(p.id), "kind": p.kind, "review_status": "pending",
            "master_profile_updated": False, "verified_evidence": False}


@staff_router.get("")
def staff_repeatables(org_id: UUID, case_id: UUID, response: Response,
                      db: Session = Depends(get_db),
                      access: OrgAccess = Depends(get_org_access)):
    allow(access, READ)
    study_case(db, org_id, case_id)
    rows = db.scalars(select(ClientRepeatableProposal).where(
        ClientRepeatableProposal.org_id == org_id,
        ClientRepeatableProposal.case_id == case_id,
    ).order_by(ClientRepeatableProposal.created_at.desc(),
               ClientRepeatableProposal.id.desc()).limit(100)).all()
    ids = [p.id for p in rows]
    decisions = db.scalars(select(ClientRepeatableDecision).where(
        ClientRepeatableDecision.org_id == org_id,
        ClientRepeatableDecision.case_id == case_id,
        ClientRepeatableDecision.proposal_id.in_(ids))).all() if ids else []
    resolved = {d.proposal_id: d for d in decisions}
    response.headers["Cache-Control"] = "no-store"
    return {"template_version": VERSION,
            "proposals": [_record_view(p, resolved.get(p.id)) for p in rows],
            "pending_count": sum(p.id not in resolved for p in rows),
            "official_form_complete": False}


@staff_router.post("/{proposal_id}/decide", status_code=201)
def decide_repeatable(org_id: UUID, case_id: UUID, proposal_id: UUID,
                      payload: DecisionInput, db: Session = Depends(get_db),
                      access: OrgAccess = Depends(get_org_access)):
    allow(access, REVIEW)
    case = study_case(db, org_id, case_id, lock=True)
    if case.status == "closed":
        raise HTTPException(409, "Closed matters cannot accept records")
    p = db.scalar(select(ClientRepeatableProposal).where(
        ClientRepeatableProposal.org_id == org_id,
        ClientRepeatableProposal.case_id == case_id,
        ClientRepeatableProposal.id == proposal_id))
    if p is None:
        raise HTTPException(404, "Client entry not found in this case")
    prior = db.scalar(select(ClientRepeatableDecision.id).where(
        ClientRepeatableDecision.org_id == org_id,
        ClientRepeatableDecision.proposal_id == proposal_id))
    if prior is not None:
        raise HTTPException(409, "This client entry was already reviewed")
    new_id = None
    if payload.decision == "accept":
        if p.kind == "family":
            duplicates = db.scalars(select(FamilyMember).where(
                FamilyMember.org_id == org_id,
                FamilyMember.client_id == case.client_id)).all()
            if any(all(getattr(member, key) == value for key, value in p.details.items())
                   for member in duplicates):
                raise HTTPException(409, "Identical family record already exists")
            row = FamilyMember(org_id=org_id, client_id=case.client_id,
                               updated_by_sub=access.principal.sub, **p.details)
        else:
            duplicates = db.scalars(select(ApplicantHistory).where(
                ApplicantHistory.org_id == org_id,
                ApplicantHistory.client_id == case.client_id,
                ApplicantHistory.kind == p.kind)).all()
            if any(row.details == p.details for row in duplicates):
                raise HTTPException(409, "Identical history record already exists")
            row = ApplicantHistory(org_id=org_id, client_id=case.client_id,
                                   kind=p.kind, details=p.details,
                                   updated_by_sub=access.principal.sub)
        db.add(row)
        db.flush()
        new_id = row.id
    decision = ClientRepeatableDecision(
        org_id=org_id, case_id=case_id, proposal_id=proposal_id,
        decision=payload.decision, created_record_id=new_id,
        reviewed_by_sub=access.principal.sub)
    db.add(decision)
    db.flush()
    record_event(db, access, "client_repeatable.reviewed",
                 "client_repeatable_proposal", proposal_id,
                 {"kind": p.kind, "decision": payload.decision,
                  "created_record_id": str(new_id) if new_id else None})
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Concurrent review or duplicated record") from None
    return {"proposal_id": str(p.id), "decision": decision.decision,
            "created_record_id": str(new_id) if new_id else None,
            "master_claim_created": new_id is not None,
            "verified_evidence": False, "official_form_complete": False}
