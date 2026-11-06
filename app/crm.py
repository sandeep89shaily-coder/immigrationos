"""Firm-scoped prospect CRM and audited consultation-agreement workflow.

Designed for fictional data. External e-signatures, email delivery, CICC licence
verification, conflict checks and service retainers are NOT implemented.
A review is a recorded human attestation, not signature authentication.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import json
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.access import OrgAccess, READ_ROLES, allow, get_org_access
from app.crm_models import (Prospect, ProspectActivity, Consultation,
                            ConsultationAgreement, ConsultationSignedCopy)
from app.db import get_db, set_db_context
from app.main import record_event
from app.malware_scan import ScannerUnavailable, scan_bytes
from app.models import Client
from app.schemas import Role
from app.storage import MAX_BYTES, delete_failed_blob, load_blob, save_blob

router = APIRouter(prefix="/api/v1/orgs/{org_id}/crm", tags=["rcic-prospect-crm"])
INTAKE = {Role.owner, Role.admin, Role.consultant, Role.assistant}
REVIEW = {Role.owner, Role.admin, Role.consultant}
CODE_REFERENCE = "https://laws-lois.justice.gc.ca/eng/regulations/SOR-2022-128/section-23.html"


class ProspectCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: str | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=40)
    source: str = Field(min_length=2, max_length=50, pattern=r"^[a-z][a-z0-9_-]*$")
    outreach_consent: bool = False
    consent_source: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def check_contact(self):
        if not (self.email or self.phone):
            raise ValueError("Provide a prospect email or phone")
        if self.outreach_consent and not self.consent_source:
            raise ValueError("Record how outreach consent was obtained")
        return self


class ProspectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    org_id: UUID
    first_name: str
    last_name: str
    email: str | None
    phone: str | None
    source: str
    stage: str
    outreach_consent: bool
    consent_source: str | None
    assigned_to_sub: str | None
    converted_client_id: UUID | None
    created_at: datetime


class ActivityInput(BaseModel):
    kind: str = Field(pattern=r"^(call|email|meeting|note)$")
    content: str = Field(min_length=5, max_length=1200)


class ConsultationInput(BaseModel):
    starts_at: datetime
    ends_at: datetime

    @model_validator(mode="after")
    def interval(self):
        if (self.starts_at.tzinfo is None or self.ends_at.tzinfo is None or
            self.ends_at <= self.starts_at or
            self.ends_at - self.starts_at > timedelta(hours=8)):
            raise ValueError("Consultation must have offset-aware, ascending dates <= 8 hours")
        return self


class ConsultationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    prospect_id: UUID
    professional_sub: str
    starts_at: datetime
    ends_at: datetime
    status: str
    created_at: datetime


class AgreementInput(BaseModel):
    licensee_name: str = Field(min_length=3, max_length=180)
    licensee_registration_number: str = Field(min_length=3, max_length=50)
    licensee_address: str = Field(min_length=10, max_length=400)
    licensee_phone: str = Field(min_length=7, max_length=40)
    licensee_email: str = Field(min_length=5, max_length=254)
    client_address: str = Field(min_length=10, max_length=400)
    purpose_scope: str = Field(min_length=20, max_length=900)
    regulator_description: str = Field(min_length=25, max_length=500)
    fee_cents_cad: int = Field(ge=0, le=100_000_000)
    pro_bono: bool = False

    @model_validator(mode="after")
    def valid_fee(self):
        if self.pro_bono != (self.fee_cents_cad == 0):
            raise ValueError("A pro bono consultation must have a zero fee, and vice versa")
        return self


class SignedCopyReview(BaseModel):
    decision: str = Field(pattern=r"^(accept|reject)$")
    reviewer_attests_signed_agreement_and_client_copy: bool
    review_note: str = Field(min_length=20, max_length=800)


def utcnow():
    return datetime.now(timezone.utc)


def _prospect(db: Session, org_id: UUID, prospect_id: UUID, lock=False) -> Prospect:
    stmt = select(Prospect).where(Prospect.org_id == org_id, Prospect.id == prospect_id)
    item = db.scalar(stmt.with_for_update() if lock else stmt)
    if item is None:
        raise HTTPException(404, "Prospect not found")
    return item


def _consultation(db, org_id, prospect_id, consultation_id, lock=False) -> Consultation:
    stmt = select(Consultation).where(
        Consultation.org_id == org_id, Consultation.prospect_id == prospect_id,
        Consultation.id == consultation_id)
    item = db.scalar(stmt.with_for_update() if lock else stmt)
    if item is None:
        raise HTTPException(404, "Consultation not found")
    return item


def _agreement(db, org_id, prospect_id, consultation_id, agreement_id) -> ConsultationAgreement:
    item = db.scalar(select(ConsultationAgreement).where(
        ConsultationAgreement.org_id == org_id,
        ConsultationAgreement.prospect_id == prospect_id,
        ConsultationAgreement.consultation_id == consultation_id,
        ConsultationAgreement.id == agreement_id))
    if item is None:
        raise HTTPException(404, "Agreement not found for this consultation")
    return item


def _latest(db, org_id, consultation_id):
    return db.scalar(select(ConsultationAgreement).where(
        ConsultationAgreement.org_id == org_id,
        ConsultationAgreement.consultation_id == consultation_id
    ).order_by(ConsultationAgreement.version.desc()).limit(1))


def _proof(db, org_id, prospect_id, agreement_id):
    return db.scalar(select(ConsultationSignedCopy).where(
        ConsultationSignedCopy.org_id == org_id,
        ConsultationSignedCopy.prospect_id == prospect_id,
        ConsultationSignedCopy.agreement_id == agreement_id))


def _event(db, access, action, resource_type, resource_id, details=None):
    # Never log names, contact details, agreement text or signed documents.
    record_event(db, access, action, resource_type, resource_id, details or {})


@router.get("/prospects", response_model=list[ProspectRead])
def list_prospects(org_id: UUID, stage: str = Query("all", pattern=r"^(all|new|contacted|consultation_scheduled|consulted|converted|closed)$"),
                   db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    allow(access, READ_ROLES)
    stmt = select(Prospect).where(Prospect.org_id == org_id)
    if stage != "all":
        stmt = stmt.where(Prospect.stage == stage)
    return db.scalars(stmt.order_by(Prospect.created_at.desc()).limit(100)).all()


@router.post("/prospects", response_model=ProspectRead, status_code=201)
def create_prospect(org_id: UUID, payload: ProspectCreate,
                    db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    allow(access, INTAKE)
    data = payload.model_dump()
    data["email"] = (data["email"] or "").strip().lower() or None
    data["phone"] = (data["phone"] or "").strip() or None
    data["consent_source"] = data["consent_source"] if data["outreach_consent"] else None
    # Surface exact-email duplicates; never automatically merge distinct people.
    if data["email"]:
        existing = db.scalar(select(Prospect.id).where(
            Prospect.org_id == org_id, func.lower(Prospect.email) == data["email"],
            Prospect.stage != "closed").limit(1))
        if existing is not None:
            raise HTTPException(409, "Possible duplicate prospect: review the existing record")
    entry = Prospect(org_id=org_id, created_by_sub=access.principal.sub,
                     assigned_to_sub=access.principal.sub, **data)
    db.add(entry)
    db.flush()
    _event(db, access, "crm.prospect_created", "prospect", entry.id)
    db.commit()
    return entry


@router.get("/prospects/{prospect_id}", response_model=ProspectRead)
def get_prospect(org_id: UUID, prospect_id: UUID,
                 db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    allow(access, READ_ROLES)
    return _prospect(db, org_id, prospect_id)


@router.get("/prospects/{prospect_id}/activities")
def list_activities(org_id: UUID, prospect_id: UUID, db: Session = Depends(get_db),
                    access: OrgAccess = Depends(get_org_access)):
    allow(access, READ_ROLES)
    _prospect(db, org_id, prospect_id)
    items = db.scalars(select(ProspectActivity).where(
        ProspectActivity.org_id == org_id, ProspectActivity.prospect_id == prospect_id
    ).order_by(ProspectActivity.created_at.desc()).limit(100)).all()
    return [{"id": str(e.id), "kind": e.kind, "content": e.content,
             "created_by_sub": e.created_by_sub, "created_at": e.created_at} for e in items]


@router.post("/prospects/{prospect_id}/activities", status_code=201)
def create_activity(org_id: UUID, prospect_id: UUID, payload: ActivityInput,
                    db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    allow(access, INTAKE)
    entry = _prospect(db, org_id, prospect_id, lock=True)
    if entry.stage in ("converted", "closed"):
        raise HTTPException(409, "This prospect is no longer active")
    event = ProspectActivity(org_id=org_id, prospect_id=prospect_id,
                             kind=payload.kind, content=payload.content,
                             created_by_sub=access.principal.sub)
    db.add(event)
    if entry.stage == "new" and payload.kind in ("call", "email", "meeting"):
        entry.stage = "contacted"
    db.flush()
    _event(db, access, "crm.activity_recorded", "prospect_activity", event.id,
           {"kind": payload.kind, "message_sent_automatically": False})
    db.commit()
    return {"id": str(event.id), "recorded_only": True, "message_sent": False}


@router.get("/prospects/{prospect_id}/consultations", response_model=list[ConsultationRead])
def list_consultations(org_id: UUID, prospect_id: UUID, db: Session = Depends(get_db),
                       access: OrgAccess = Depends(get_org_access)):
    allow(access, READ_ROLES)
    _prospect(db, org_id, prospect_id)
    return db.scalars(select(Consultation).where(
        Consultation.org_id == org_id, Consultation.prospect_id == prospect_id
    ).order_by(Consultation.created_at.desc()).limit(25)).all()


@router.post("/prospects/{prospect_id}/consultations", response_model=ConsultationRead, status_code=201)
def schedule_consultation(org_id: UUID, prospect_id: UUID, payload: ConsultationInput,
                          db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    allow(access, REVIEW)
    entry = _prospect(db, org_id, prospect_id, lock=True)
    if entry.stage in ("converted", "closed"):
        raise HTTPException(409, "This prospect cannot be scheduled")
    already = db.scalar(select(Consultation.id).where(
        Consultation.org_id == org_id, Consultation.prospect_id == prospect_id,
        Consultation.status == "scheduled"))
    if already is not None:
        raise HTTPException(409, "A consultation is already scheduled")
    if payload.starts_at.astimezone(timezone.utc) <= utcnow():
        raise HTTPException(422, "Choose a future consultation time")
    booking = Consultation(org_id=org_id, prospect_id=prospect_id,
                           professional_sub=access.principal.sub,
                           created_by_sub=access.principal.sub,
                           starts_at=payload.starts_at, ends_at=payload.ends_at)
    db.add(booking)
    entry.stage = "consultation_scheduled"
    db.flush()
    _event(db, access, "crm.consultation_scheduled", "consultation", booking.id)
    db.commit()
    return booking


@router.post("/prospects/{prospect_id}/consultations/{consultation_id}/cancel")
def cancel_consultation(org_id: UUID, prospect_id: UUID, consultation_id: UUID,
                        db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    allow(access, REVIEW)
    entry = _prospect(db, org_id, prospect_id, lock=True)
    booking = _consultation(db, org_id, prospect_id, consultation_id, lock=True)
    if booking.status != "scheduled":
        raise HTTPException(409, "Only scheduled consultations can be cancelled")
    booking.status = "cancelled"
    booking.cancelled_at = utcnow()
    if entry.stage == "consultation_scheduled":
        entry.stage = "contacted"
    _event(db, access, "crm.consultation_cancelled", "consultation", booking.id)
    db.commit()
    return {"status": "cancelled", "consultation_id": str(booking.id)}


@router.get("/prospects/{prospect_id}/consultations/{consultation_id}/agreements")
def list_agreements(org_id: UUID, prospect_id: UUID, consultation_id: UUID,
                    db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    allow(access, READ_ROLES)
    _consultation(db, org_id, prospect_id, consultation_id)
    items = db.scalars(select(ConsultationAgreement).where(
        ConsultationAgreement.org_id == org_id,
        ConsultationAgreement.consultation_id == consultation_id
    ).order_by(ConsultationAgreement.version.desc())).all()
    return [{
        "id": str(item.id), "version": item.version, "terms_sha256": item.terms_sha256,
        "terms": item.terms, "created_at": item.created_at,
        "signed_copy": _proof_summary(_proof(db, org_id, prospect_id, item.id))
    } for item in items]


def _proof_summary(proof):
    if proof is None:
        return None
    return {"id": str(proof.id), "sha256": proof.sha256,
            "scan_status": proof.scan_status, "review_status": proof.review_status,
            "reviewed_by_sub": proof.reviewed_by_sub,
            "signed_at": proof.signed_at, "client_copy_provided_at": proof.client_copy_provided_at}


@router.post("/prospects/{prospect_id}/consultations/{consultation_id}/agreements", status_code=201)
def prepare_agreement(org_id: UUID, prospect_id: UUID, consultation_id: UUID, payload: AgreementInput,
                      db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    allow(access, REVIEW)
    entry = _prospect(db, org_id, prospect_id, lock=True)
    booking = _consultation(db, org_id, prospect_id, consultation_id, lock=True)
    if booking.status != "scheduled" or entry.stage != "consultation_scheduled":
        raise HTTPException(409, "Only a scheduled consultation can receive new agreement terms")
    previous = _latest(db, org_id, consultation_id)
    if previous and _proof(db, org_id, prospect_id, previous.id):
        raise HTTPException(409, "An uploaded signed copy locks this agreement; start a new consultation")
    snapshot = {
        "schema_version": "consultation-s23-preliminary-v1",
        "licensee_name": payload.licensee_name.strip(),
        "licensee_registration_number": payload.licensee_registration_number.strip(),
        "licensee_address": payload.licensee_address.strip(),
        "licensee_phone": payload.licensee_phone.strip(),
        "licensee_email": payload.licensee_email.strip(),
        "client_name": f"{entry.first_name} {entry.last_name}",
        "client_address": payload.client_address.strip(),
        "client_phone": entry.phone,
        "client_email": entry.email,
        "fee_cents_cad": payload.fee_cents_cad,
        "pro_bono": payload.pro_bono,
        "regulator_description": payload.regulator_description.strip(),
        "purpose_scope": payload.purpose_scope.strip(),
        "source_url": CODE_REFERENCE,
        "not_approved_legal_template": True,
    }
    encoded = json.dumps(snapshot, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    agreement = ConsultationAgreement(
        org_id=org_id, prospect_id=prospect_id, consultation_id=consultation_id,
        version=(previous.version + 1 if previous else 1),
        terms=snapshot, terms_sha256=hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
        created_by_sub=access.principal.sub,
    )
    db.add(agreement)
    db.flush()
    _event(db, access, "crm.agreement_terms_prepared", "consultation_agreement", agreement.id,
           {"consultation_id": str(consultation_id), "version": agreement.version})
    db.commit()
    return {"id": str(agreement.id), "version": agreement.version,
            "terms_sha256": agreement.terms_sha256, "terms": snapshot,
            "status": "draft_not_signed", "s23_check_required": True,
            "delivery_and_e_signature_not_implemented": True}


@router.post("/prospects/{prospect_id}/consultations/{consultation_id}/agreements/{agreement_id}/signed-copy",
             status_code=201)
async def upload_signed_copy(org_id: UUID, prospect_id: UUID, consultation_id: UUID, agreement_id: UUID,
                             signed_at: datetime = Form(...), client_copy_provided_at: datetime = Form(...),
                             file: UploadFile = File(...),
                             db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    allow(access, INTAKE)
    booking = _consultation(db, org_id, prospect_id, consultation_id)
    _agreement(db, org_id, prospect_id, consultation_id, agreement_id)
    if booking.status != "scheduled":
        raise HTTPException(409, "Consultation must be scheduled")
    current = _latest(db, org_id, consultation_id)
    if current is None or current.id != agreement_id:
        raise HTTPException(409, "Only latest agreement version can receive signed proof")
    if _proof(db, org_id, prospect_id, agreement_id) is not None:
        raise HTTPException(409, "Signed copy already recorded for this agreement")
    if signed_at.tzinfo is None or client_copy_provided_at.tzinfo is None:
        raise HTTPException(422, "Signed and delivered timestamps must include an offset")
    if (client_copy_provided_at < signed_at or signed_at > utcnow() + timedelta(minutes=5)
            or client_copy_provided_at > utcnow() + timedelta(minutes=5)):
        raise HTTPException(422, "Invalid signing/client-delivery timestamps")
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(415, "Signed consultation copy must be a PDF")
    raw = await file.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise HTTPException(413, "Signed PDF exceeds 8 MB")
    key, digest = save_blob(raw, "application/pdf")
    try:
        try:
            verdict = scan_bytes(raw)
            scan_status = verdict.status
        except ScannerUnavailable:
            scan_status = "quarantined"
        proof = ConsultationSignedCopy(
            org_id=org_id, prospect_id=prospect_id, agreement_id=agreement_id,
            storage_key=key, sha256=digest, size_bytes=len(raw), signed_at=signed_at,
            client_copy_provided_at=client_copy_provided_at,
            scan_status=scan_status, review_status="pending",
            created_by_sub=access.principal.sub,
        )
        db.add(proof)
        db.flush()
        _event(db, access, "crm.signed_copy_uploaded", "consultation_signed_copy", proof.id,
               {"agreement_id": str(agreement_id), "scan_status": scan_status})
        db.commit()
        return {"id": str(proof.id), "sha256": digest, "scan_status": scan_status,
                "review_status": "pending", "electronic_signature_verified": False,
                "human_review_required": True}
    except Exception:
        db.rollback()
        delete_failed_blob(key)
        raise


@router.post("/prospects/{prospect_id}/consultations/{consultation_id}/agreements/{agreement_id}/scan")
def rescan_signed_copy(org_id: UUID, prospect_id: UUID, consultation_id: UUID, agreement_id: UUID,
                       db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    allow(access, REVIEW)
    _agreement(db, org_id, prospect_id, consultation_id, agreement_id)
    proof = _proof(db, org_id, prospect_id, agreement_id)
    if proof is None:
        raise HTTPException(404, "Signed copy not recorded")
    if proof.review_status != "pending" or proof.scan_status != "quarantined":
        raise HTTPException(409, "Only pending quarantined copies may be rescanned")
    raw = load_blob(proof.storage_key)
    if hashlib.sha256(raw).hexdigest() != proof.sha256:
        raise HTTPException(409, "Stored signed-copy checksum mismatch")
    try:
        verdict = scan_bytes(raw)
    except ScannerUnavailable:
        raise HTTPException(503, "Scanner unavailable; signed copy remains quarantined") from None
    proof.scan_status = verdict.status
    _event(db, access, "crm.signed_copy_scanned", "consultation_signed_copy", proof.id,
           {"scan_status": proof.scan_status})
    db.commit()
    return {"scan_status": proof.scan_status, "human_review_required": True}


@router.post("/prospects/{prospect_id}/consultations/{consultation_id}/agreements/{agreement_id}/review")
def review_signed_copy(org_id: UUID, prospect_id: UUID, consultation_id: UUID, agreement_id: UUID,
                       payload: SignedCopyReview, db: Session = Depends(get_db),
                       access: OrgAccess = Depends(get_org_access)):
    allow(access, REVIEW)
    booking = _consultation(db, org_id, prospect_id, consultation_id, lock=True)
    _agreement(db, org_id, prospect_id, consultation_id, agreement_id)
    proof = _proof(db, org_id, prospect_id, agreement_id)
    if booking.status != "scheduled" or proof is None or proof.review_status != "pending":
        raise HTTPException(409, "Signed-copy review is unavailable")
    if proof.scan_status != "cleared":
        raise HTTPException(423, "Signed copy has not passed malware scanning")
    if not payload.reviewer_attests_signed_agreement_and_client_copy:
        raise HTTPException(422, "Human reviewer must attest the signed content and client-copy delivery")
    # Reviewer has seen and confirmed the actual signed PDF; no app-level claim
    # that the signature service, identity or current RCIC status was verified.
    proof.review_status = "accepted" if payload.decision == "accept" else "rejected"
    proof.review_note = payload.review_note
    proof.reviewed_by_sub = access.principal.sub
    proof.reviewed_at = utcnow()
    _event(db, access, "crm.signed_copy_reviewed", "consultation_signed_copy", proof.id,
           {"decision": proof.review_status, "signed_copy_sha256": proof.sha256})
    db.commit()
    return {"review_status": proof.review_status, "professional_role_verified": False,
            "external_signature_cryptography_verified": False, "review_note_stored_with_restricted_proof": True}


@router.post("/prospects/{prospect_id}/consultations/{consultation_id}/complete")
def complete_consultation(org_id: UUID, prospect_id: UUID, consultation_id: UUID,
                          db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    allow(access, REVIEW)
    entry = _prospect(db, org_id, prospect_id, lock=True)
    booking = _consultation(db, org_id, prospect_id, consultation_id, lock=True)
    if booking.status != "scheduled":
        raise HTTPException(409, "Consultation is not currently scheduled")
    current = _latest(db, org_id, consultation_id)
    proof = _proof(db, org_id, prospect_id, current.id) if current else None
    if proof is None or proof.review_status != "accepted" or proof.scan_status != "cleared":
        raise HTTPException(409, "A cleared, reviewed signed consultation agreement is required")
    booking.status = "completed"
    booking.completed_at = utcnow()
    entry.stage = "consulted"
    _event(db, access, "crm.consultation_completed", "consultation", booking.id,
           {"agreement_id": str(current.id), "signed_copy_sha256": proof.sha256})
    db.commit()
    return {"status": "completed", "prospect_stage": entry.stage,
            "further_services_require_separate_service_agreement": True}


@router.post("/prospects/{prospect_id}/convert", status_code=201)
def convert_prospect(org_id: UUID, prospect_id: UUID,
                     db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    allow(access, REVIEW)
    entry = _prospect(db, org_id, prospect_id, lock=True)
    if entry.stage == "converted" and entry.converted_client_id is not None:
        return {"client_id": str(entry.converted_client_id), "created": False,
                "service_agreement_required_before_further_consulting": True}
    if entry.stage != "consulted":
        raise HTTPException(409, "Consultation completion with reviewed signed terms required")
    if entry.email:
        duplicate = db.scalar(select(Client).where(
            Client.org_id == org_id, func.lower(Client.email) == entry.email.lower()).limit(1))
        if duplicate is not None:
            raise HTTPException(409, "Existing client with matching email needs explicit reconciliation")
    existing = db.scalar(select(Client).where(
        Client.org_id == org_id, Client.first_name == entry.first_name,
        Client.last_name == entry.last_name, Client.phone == entry.phone).limit(1))
    if existing is not None:
        raise HTTPException(409, "Possible duplicate client: manual reconciliation required")
    client = Client(org_id=org_id, first_name=entry.first_name,
                    last_name=entry.last_name, email=entry.email, phone=entry.phone)
    db.add(client)
    db.flush()
    entry.stage = "converted"
    entry.converted_client_id = client.id
    _event(db, access, "crm.prospect_converted", "prospect", entry.id,
           {"client_id": str(client.id), "service_agreement_not_automatically_satisfied": True})
    db.commit()
    return {"client_id": str(client.id), "created": True,
            "service_agreement_required_before_further_consulting": True}
