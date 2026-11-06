"""Reusable profiles and immutable *internal-only* IRCC answer draft snapshots.

No raw applicant profile answer is evidence-verified. No official IRCC PDF is
generated, validated, barcoded, signed or submitted by this module.
"""
from datetime import date
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.access import OrgAccess, WRITE_ROLES, allow, get_org_access
from app.applicant_models import ApplicantProfile, FamilyMember, CaseAnswerDraft
from app.db import get_db
from app.ircc_registry import REGISTRY
from app.main import record_event
from app.models import Case, Client
from app.package_models import CaseApplicationPackage
from app.schemas import Role

router = APIRouter(prefix="/api/v1/orgs/{org_id}", tags=["applicant-profiles"])
MANAGERS = {Role.owner, Role.admin, Role.consultant}


class Identity(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    given_name: str | None = Field(default=None, max_length=100)
    family_name: str | None = Field(default=None, max_length=100)
    date_of_birth: date | None = None
    citizenship: str | None = Field(default=None, max_length=100)
    passport_number: str | None = Field(default=None, max_length=60)
    passport_expiry: date | None = None
    country_of_birth: str | None = Field(default=None, max_length=100)


class ApplicantInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int | None = Field(default=None, ge=1)
    identity: Identity


class RelativeInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    relationship: str = Field(pattern=r"^(spouse|common_law_partner|child|parent|sibling|other)$")
    given_name: str = Field(min_length=1, max_length=100)
    family_name: str = Field(min_length=1, max_length=100)
    date_of_birth: date | None = None
    citizenship: str | None = Field(default=None, max_length=100)


class RelativeUpdate(RelativeInput):
    expected_version: int = Field(ge=1)


def _client(db: Session, org_id: UUID, client_id: UUID) -> Client:
    result = db.scalar(select(Client).where(Client.org_id == org_id, Client.id == client_id))
    if result is None:
        raise HTTPException(404, "Client not available")
    return result


def _family_json(member: FamilyMember) -> dict:
    return {
        "id": str(member.id), "relationship": member.relationship,
        "given_name": member.given_name, "family_name": member.family_name,
        "date_of_birth": member.date_of_birth, "citizenship": member.citizenship,
        "version": member.version,
    }


@router.get("/clients/{client_id}/applicant")
def get_applicant(org_id: UUID, client_id: UUID, db: Session = Depends(get_db),
                  access: OrgAccess = Depends(get_org_access)):
    _client(db, org_id, client_id)
    profile = db.scalar(select(ApplicantProfile).where(
        ApplicantProfile.org_id == org_id, ApplicantProfile.client_id == client_id))
    family = db.scalars(select(FamilyMember).where(
        FamilyMember.org_id == org_id, FamilyMember.client_id == client_id
    ).order_by(FamilyMember.updated_at, FamilyMember.id)).all()
    return {"client_id": str(client_id), "profile": None if profile is None else {
        "identity": profile.data.get("identity", {}), "version": profile.version,
        "updated_at": profile.updated_at.isoformat()},
        "family": [_family_json(row) for row in family],
        "verified_for_official_forms": False}


@router.put("/clients/{client_id}/applicant")
def save_applicant(org_id: UUID, client_id: UUID, payload: ApplicantInput,
                   db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    allow(access, WRITE_ROLES)
    _client(db, org_id, client_id)
    profile = db.scalar(select(ApplicantProfile).where(
        ApplicantProfile.org_id == org_id, ApplicantProfile.client_id == client_id).with_for_update())
    if profile is None:
        if payload.expected_version is not None:
            raise HTTPException(409, "Profile version changed; reload before saving")
        profile = ApplicantProfile(org_id=org_id, client_id=client_id,
                                   version=1, updated_by_sub=access.principal.sub)
        db.add(profile)
    else:
        if payload.expected_version != profile.version:
            raise HTTPException(409, "Profile version changed; reload before saving")
        profile.version += 1
        profile.updated_by_sub = access.principal.sub
    profile.data = {"identity": payload.identity.model_dump(mode="json", exclude_none=True)}
    db.flush()
    record_event(db, access, "applicant.profile_saved", "client", client_id,
                 {"version": profile.version})
    db.commit()
    return {"client_id": str(client_id), "version": profile.version,
            "identity": profile.data["identity"], "verified_for_official_forms": False}


@router.post("/clients/{client_id}/family", status_code=201)
def add_relative(org_id: UUID, client_id: UUID, payload: RelativeInput,
                 db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    allow(access, WRITE_ROLES)
    _client(db, org_id, client_id)
    item = FamilyMember(org_id=org_id, client_id=client_id, updated_by_sub=access.principal.sub,
                        **payload.model_dump(mode="json"))
    db.add(item)
    db.flush()
    record_event(db, access, "applicant.family_added", "family_member", item.id)
    db.commit()
    return _family_json(item)


@router.put("/clients/{client_id}/family/{relative_id}")
def update_relative(org_id: UUID, client_id: UUID, relative_id: UUID, payload: RelativeUpdate,
                    db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    allow(access, WRITE_ROLES)
    row = db.scalar(select(FamilyMember).where(
        FamilyMember.org_id == org_id, FamilyMember.client_id == client_id,
        FamilyMember.id == relative_id).with_for_update())
    if row is None:
        raise HTTPException(404, "Family member not available")
    if row.version != payload.expected_version:
        raise HTTPException(409, "Family member version changed")
    for key, value in payload.model_dump(mode="json", exclude={"expected_version"}).items():
        setattr(row, key, value)
    row.version += 1
    row.updated_by_sub = access.principal.sub
    record_event(db, access, "applicant.family_updated", "family_member", row.id,
                 {"version": row.version})
    db.commit()
    return _family_json(row)


@router.post("/cases/{case_id}/answer-drafts", status_code=201)
def build_answer_draft(org_id: UUID, case_id: UUID,
                       db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    allow(access, MANAGERS)
    case = db.scalar(select(Case).where(Case.org_id == org_id, Case.id == case_id))
    if case is None:
        raise HTTPException(404, "Case not available")
    pkg = db.scalar(select(CaseApplicationPackage).where(
        CaseApplicationPackage.org_id == org_id, CaseApplicationPackage.case_id == case_id))
    if pkg is None:
        raise HTTPException(409, "Initialize the study permit package first")
    form_code = "IMM5709" if pkg.filing_context == "inside_canada" else "IMM1294"
    source = REGISTRY[form_code]
    profile = db.scalar(select(ApplicantProfile).where(
        ApplicantProfile.org_id == org_id, ApplicantProfile.client_id == case.client_id))
    if profile is None:
        raise HTTPException(409, "Create the reusable applicant profile first")
    identity = profile.data.get("identity", {})
    # Canonical paths and observed worklist labels, NOT PDF field identifiers.
    mapping = {
        "identity.given_name": "given_name",
        "identity.family_name": "family_name",
        "identity.date_of_birth": "date_of_birth",
        "identity.citizenship": "citizenship",
        "identity.passport_number": "passport_number",
    }
    answers = {path: identity[key] for path, key in mapping.items()
               if isinstance(identity.get(key), str) and identity[key].strip()}
    unresolved = [path for path in mapping if path not in answers]
    draft = CaseAnswerDraft(
        org_id=org_id, case_id=case_id, client_id=case.client_id,
        form_code=form_code, source_revision=source.revision_label,
        profile_version=profile.version, answers=answers,
        unresolved_fields=unresolved, created_by_sub=access.principal.sub)
    db.add(draft)
    db.flush()
    record_event(db, access, "case.answer_draft_created", "case", case_id,
                 {"draft_id": str(draft.id), "form_code": form_code,
                  "profile_version": profile.version})
    db.commit()
    return _draft_json(draft)


def _draft_json(item: CaseAnswerDraft) -> dict:
    return {
        "id": str(item.id), "case_id": str(item.case_id),
        "form_code": item.form_code, "source_revision": item.source_revision,
        "profile_version": item.profile_version, "answers": item.answers,
        "unresolved_fields": item.unresolved_fields,
        "created_at": item.created_at.isoformat(),
        "status": "unverified_internal_draft",
        "official_pdf_autofill_supported": False,
        "official_validation_verified": False, "submission_supported": False,
    }


@router.get("/cases/{case_id}/answer-drafts")
def list_answer_drafts(org_id: UUID, case_id: UUID, db: Session = Depends(get_db),
                       access: OrgAccess = Depends(get_org_access)):
    records = db.scalars(select(CaseAnswerDraft).where(
        CaseAnswerDraft.org_id == org_id, CaseAnswerDraft.case_id == case_id
    ).order_by(CaseAnswerDraft.created_at.desc(), CaseAnswerDraft.id.desc()).limit(50)).all()
    return [_draft_json(row) for row in records]
