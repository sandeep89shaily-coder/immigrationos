"""Strict applicant history CRUD and case-scoped evidence comparison.

History values are client/staff-entered claims, not verified evidence. Comparison
is read-only and never promotes claims into verified CaseFact records.
"""
from datetime import date
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.access import OrgAccess, WRITE_ROLES, allow, get_org_access
from app.applicant_history_models import ApplicantHistory
from app.db import get_db
from app.main import record_event
from app.models import Case, Client, CaseFact, CaseDocument
from app.workspace import insert_fact_with_conflicts, ensure_case_open
from app.workspace_schemas import FactCreate
from app.schemas import Role

router = APIRouter(prefix="/api/v1/orgs/{org_id}", tags=["applicant-history"])
KINDS = ("address", "education", "employment", "travel")


class Period(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    start_date: date
    end_date: date | None = None

    @model_validator(mode="after")
    def validate_period(self):
        if self.end_date is not None and self.end_date < self.start_date:
            raise ValueError("End date precedes start date")
        return self


class Address(Period):
    line1: str = Field(min_length=1, max_length=160)
    line2: str | None = Field(default=None, max_length=160)
    city: str = Field(min_length=1, max_length=100)
    region: str | None = Field(default=None, max_length=100)
    country: str = Field(min_length=1, max_length=100)
    postal_code: str | None = Field(default=None, max_length=24)


class Education(Period):
    institution: str = Field(min_length=1, max_length=160)
    country: str = Field(min_length=1, max_length=100)
    program: str = Field(min_length=1, max_length=160)
    credential: str | None = Field(default=None, max_length=120)


class Employment(Period):
    employer: str = Field(min_length=1, max_length=160)
    position: str = Field(min_length=1, max_length=160)
    country: str = Field(min_length=1, max_length=100)
    city: str | None = Field(default=None, max_length=100)
    employment_status: Literal["employed", "self_employed", "unemployed", "student", "other"]


class Travel(Period):
    destination_country: str = Field(min_length=1, max_length=100)
    purpose: str = Field(min_length=1, max_length=160)
    origin_country: str | None = Field(default=None, max_length=100)


ADAPTERS = {
    "address": TypeAdapter(Address), "education": TypeAdapter(Education),
    "employment": TypeAdapter(Employment), "travel": TypeAdapter(Travel),
}


class HistoryPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    details: dict = Field(min_length=2, max_length=12)
    expected_version: int | None = Field(default=None, ge=1)


def _kind(kind: str):
    if kind not in ADAPTERS:
        raise HTTPException(404, "History category not supported")
    return ADAPTERS[kind]


def _validated_details(validator, details):
    try:
        return validator.validate_python(details).model_dump(mode="json", exclude_none=True)
    except ValidationError as exc:
        raise HTTPException(422, "Invalid history fields, dates or values") from exc


def _client(db, org_id, client_id):
    if db.scalar(select(Client.id).where(Client.org_id == org_id, Client.id == client_id)) is None:
        raise HTTPException(404, "Client not available")


def canonical_history_path(item, key: str) -> str:
    return f"history.{item.kind}.r_{item.id.hex}.{key}"


def _view(item):
    return {"id": str(item.id), "kind": item.kind, "version": item.version,
            "details": item.details, "updated_at": item.updated_at.isoformat(),
            "verified_evidence": False}


@router.get("/clients/{client_id}/histories")
def list_histories(org_id: UUID, client_id: UUID, db: Session = Depends(get_db),
                   access: OrgAccess = Depends(get_org_access)):
    _client(db, org_id, client_id)
    records = db.scalars(select(ApplicantHistory).where(
        ApplicantHistory.org_id == org_id, ApplicantHistory.client_id == client_id
    ).order_by(ApplicantHistory.kind, ApplicantHistory.id)).all()
    return {"client_id": str(client_id),
            "records": [_view(item) for item in records],
            "official_form_verified": False}


@router.post("/clients/{client_id}/histories/{kind}", status_code=201)
def add_history(org_id: UUID, client_id: UUID, kind: str, payload: HistoryPayload,
                db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    allow(access, WRITE_ROLES)
    validator = _kind(kind)
    if payload.expected_version is not None:
        raise HTTPException(409, "New history items cannot have an existing version")
    _client(db, org_id, client_id)
    normalized = _validated_details(validator, payload.details)
    item = ApplicantHistory(org_id=org_id, client_id=client_id, kind=kind, details=normalized,
                            updated_by_sub=access.principal.sub)
    db.add(item)
    db.flush()
    record_event(db, access, "applicant.history_added", "client", client_id,
                 {"record_id": str(item.id), "kind": kind, "version": 1})
    db.commit()
    return _view(item)


@router.put("/clients/{client_id}/histories/{kind}/{record_id}")
def update_history(org_id: UUID, client_id: UUID, kind: str, record_id: UUID,
                   payload: HistoryPayload, db: Session = Depends(get_db),
                   access: OrgAccess = Depends(get_org_access)):
    allow(access, WRITE_ROLES)
    validator = _kind(kind)
    item = db.scalar(select(ApplicantHistory).where(
        ApplicantHistory.org_id == org_id, ApplicantHistory.client_id == client_id,
        ApplicantHistory.id == record_id, ApplicantHistory.kind == kind).with_for_update())
    if item is None:
        raise HTTPException(404, "History item not available")
    if payload.expected_version != item.version:
        raise HTTPException(409, "History item changed; reload before saving")
    item.details = _validated_details(validator, payload.details)
    item.version += 1
    item.updated_by_sub = access.principal.sub
    record_event(db, access, "applicant.history_updated", "client", client_id,
                 {"record_id": str(item.id), "kind": kind, "version": item.version})
    db.commit()
    return _view(item)


@router.get("/cases/{case_id}/history-evidence-review")
def history_evidence_review(org_id: UUID, case_id: UUID,
                            db: Session = Depends(get_db),
                            access: OrgAccess = Depends(get_org_access)):
    """Compare self-reported histories with reviewed case facts, without making them authoritative."""
    case = db.scalar(select(Case).where(Case.org_id == org_id, Case.id == case_id))
    if case is None:
        raise HTTPException(404, "Case not available")
    records = db.scalars(select(ApplicantHistory).where(
        ApplicantHistory.org_id == org_id, ApplicantHistory.client_id == case.client_id
    ).order_by(ApplicantHistory.kind, ApplicantHistory.id)).all()
    facts = db.scalars(select(CaseFact).where(
        CaseFact.org_id == org_id, CaseFact.case_id == case_id,
        CaseFact.review_status == "verified")).all()
    # Only fields with explicitly matching internal canonical paths are compared.
    # No matching CaseFact is *not* proof that a history value is false.
    evidence = {}
    for fact in facts:
        evidence.setdefault(fact.field_path, []).append(fact)
    results = []
    for item in records:
        fields = []
        for key, value in item.details.items():
            if value is None:
                continue
            path = canonical_history_path(item, key)
            matches = evidence.get(path, [])
            values = {fact.value.strip() for fact in matches}
            status = ("not_evidence_reviewed" if not matches else
                      "conflict_requires_review" if values != {str(value)} else
                      "matches_verified_fact")
            fields.append({"canonical_path": path, "status": status,
                           "fact_ids": sorted(str(fact.id) for fact in matches)})
        results.append({"record_id": str(item.id), "kind": item.kind,
                        "version": item.version, "fields": fields})
    return {"case_id": str(case_id), "records": results,
            "all_histories_verified": False, "official_form_generation_allowed": False,
            "warning": "Comparisons are informational. Supporting documents, gaps, chronology and professional applicability must be checked independently."}


class HistoryEvidenceLink(BaseModel):
    model_config = ConfigDict(extra="forbid")
    document_id: UUID
    source_page: int | None = Field(default=None, ge=1, le=10000)
    source_excerpt: str | None = Field(default=None, min_length=10, max_length=500)


@router.post("/cases/{case_id}/histories/{record_id}/fields/{field_key}/evidence", status_code=201)
def link_history_evidence(org_id: UUID, case_id: UUID, record_id: UUID, field_key: str,
                          payload: HistoryEvidenceLink, db: Session = Depends(get_db),
                          access: OrgAccess = Depends(get_org_access)):
    """Document-bound candidate fact, always pending until a separate professional review."""
    allow(access, {Role.owner, Role.admin, Role.consultant})
    case = ensure_case_open(db, org_id, case_id)
    item = db.scalar(select(ApplicantHistory).where(
        ApplicantHistory.org_id == org_id, ApplicantHistory.client_id == case.client_id,
        ApplicantHistory.id == record_id))
    if item is None:
        raise HTTPException(404, "History item not available in this case")
    value = item.details.get(field_key)
    if not isinstance(value, str) or not value:
        raise HTTPException(404, "History field not available")
    source = db.scalar(select(CaseDocument).where(
        CaseDocument.org_id == org_id, CaseDocument.case_id == case_id,
        CaseDocument.id == payload.document_id))
    if source is None:
        raise HTTPException(404, "Supporting document not available in this case")
    path = canonical_history_path(item, field_key)
    # Deliberately no human-verification promotion. History edits leave prior
    # facts intact; subsequent versions create conflicts for review.
    fact = insert_fact_with_conflicts(db, access, case_id, FactCreate(
        field_path=path, value=value, document_id=source.id,
        source_page=payload.source_page, source_excerpt=payload.source_excerpt))
    record_event(db, access, "applicant.history_evidence_linked", "case", case_id,
                 {"record_id": str(record_id), "field_key": field_key,
                  "fact_id": str(fact.id)})
    db.commit()
    return {"fact_id": str(fact.id), "field_path": path,
            "review_status": "pending", "document_id": str(source.id),
            "automatic_verification": False}
