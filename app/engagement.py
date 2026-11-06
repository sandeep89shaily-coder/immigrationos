"""RCIC service engagement gates for fictional development cases only.

No RCIC licensing, external signature, actual client delivery, legal adequacy,
trust handling or IRCC submission is independently verified here.
"""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import html
import json
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.access import OrgAccess, READ_ROLES, allow, get_org_access
from app.case_scope import MANAGERS, active_staff_member, visible_case_ids
from app.db import get_db
from app.engagement_models import (EngagementScreen, MatterAssignment,
                                   ServiceAgreementDraft, ServiceSignedCopy)
from app.main import record_event
from app.malware_scan import scan_bytes, ScannerUnavailable
from app.models import Case, Client, Membership
from app.schemas import Role
from app.storage import MAX_BYTES, save_blob, load_blob, delete_failed_blob

router = APIRouter(prefix="/api/v1/orgs/{org_id}/engagements", tags=["rcic-service-engagement"])
REVIEW = {Role.owner, Role.admin, Role.consultant}
INTAKE = REVIEW | {Role.assistant}

CODE_24 = "https://laws-lois.justice.gc.ca/eng/regulations/SOR-2022-128/section-24.html"
CODE_15 = "https://laws-lois.justice.gc.ca/eng/regulations/SOR-2022-128/section-15.html"

# All headings mandated by the Code s.24(3). These are checkboxes/fields for
# professional completion, NOT government-validated clauses.
CLAUSES = {
    "a_licensee": "Licensee identity, registration and contact",
    "b_client": "Client identity and personal/business contacts",
    "c_preliminary_advice": "Summary of preliminary advice (state none if applicable)",
    "d_supervision": "Quality services and supervision undertaking",
    "e_assistants": "Likely assisting professionals/staff (or none)",
    "f_client_instructions": "Client instructions",
    "g_services": "Client-specific itemized scope and services",
    "h_timeframes": "Estimated service timeframes",
    "i_fees": "Fixed/hourly fee estimate or pro bono statement",
    "j_disbursements": "Expected disbursements (or none)",
    "k_taxes": "Applicable taxes/levies (or none with reason)",
    "l_payment_terms": "Payment and interest terms",
    "m_advance_refunds": "Advances and refund policy",
    "n_extra_costs": "Other possible costs",
    "o_conflict": "Conflict disclosures (or none identified)",
    "p_originals_return": "Return of client's original documents",
    "q_confidentiality": "Confidentiality and practical safeguards",
    "r_firm_complaints": "Licensee complaint-handling procedure",
    "s_official_language": "Official language used for services",
    "t_status_updates": "Timely case status information commitment",
    "u_interpreters": "Assistance, translators and interpreters",
    "v_college_role": "College regulation and complaints process",
    "w_college_records": "College authority to require documents",
    "x_code_copy": "Written statement that Code copy provided",
    "y_incapacity": "Incapacity/continuity and client-file handling",
    "z_other_terms": "Other agreed terms (or expressly none)",
}


def utcnow():
    return datetime.now(timezone.utc)


def normalized(ts):
    if ts is None:
        return None
    return ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts.astimezone(timezone.utc)


class ScreenInput(BaseModel):
    client_identity_verified: bool
    previous_rep_checked: bool
    prior_rep: str = Field(pattern=r"^(none|ended_in_writing|concurrent|unknown)$")
    conflict_status: str = Field(pattern=r"^(none_identified|potential|prohibited|unresolved)$")
    details: str = Field(min_length=25, max_length=1200)
    independently_reviewed_conflicts: bool

    @model_validator(mode="after")
    def details_required(self):
        self.details = self.details.strip()
        if len(self.details) < 25 or not self.independently_reviewed_conflicts:
            raise ValueError("A documented, independent professional conflict review is required")
        return self


class AgreementInput(BaseModel):
    clauses: dict[str, str]
    professional_checked_current_code: bool

    @model_validator(mode="after")
    def require_all_clauses(self):
        if not self.professional_checked_current_code:
            raise ValueError("Reviewer must check current Code s.24")
        if set(self.clauses) != set(CLAUSES):
            raise ValueError("All Code section 24(3) clauses a-z require review")
        for key, raw in self.clauses.items():
            if not isinstance(raw, str) or len(raw.strip()) < 3 or len(raw.strip()) > 1500:
                raise ValueError("Incomplete or oversized agreement clause: " + key)
        self.clauses = {k: v.strip() for k, v in self.clauses.items()}
        return self


class SignedReviewInput(BaseModel):
    decision: str = Field(pattern=r"^(accept|reject)$")
    reviewer_confirmed_signed_terms_and_delivery: bool
    note: str = Field(min_length=25, max_length=1000)

    @model_validator(mode="after")
    def check(self):
        if not self.reviewer_confirmed_signed_terms_and_delivery:
            raise ValueError("Human reviewer must confirm signed terms and client-copy delivery")
        if len(self.note.strip()) < 25:
            raise ValueError("Review note must be substantive")
        return self


class OpenMatterInput(BaseModel):
    application_type: str = Field(min_length=3, max_length=80, pattern=r"^[a-z][a-z0-9_]*$")
    title: str = Field(min_length=4, max_length=160)
    professional_sub: str = Field(min_length=3, max_length=255)
    confirm_engagement_and_professional_assignment: bool

    @model_validator(mode="after")
    def ready(self):
        if not self.confirm_engagement_and_professional_assignment:
            raise ValueError("Explicit engagement and professional assignment confirmation is required")
        return self


def client_for(db, org_id, client_id, lock=False):
    q = select(Client).where(Client.org_id == org_id, Client.id == client_id)
    c = db.scalar(q.with_for_update() if lock else q)
    if c is None:
        raise HTTPException(404, "Client not found")
    return c


def latest_screen(db, org_id, client_id):
    return db.scalar(select(EngagementScreen).where(
        EngagementScreen.org_id == org_id, EngagementScreen.client_id == client_id
    ).order_by(EngagementScreen.created_at.desc(), EngagementScreen.id.desc()).limit(1))


def latest_draft(db, org_id, client_id):
    return db.scalar(select(ServiceAgreementDraft).where(
        ServiceAgreementDraft.org_id == org_id, ServiceAgreementDraft.client_id == client_id
    ).order_by(ServiceAgreementDraft.version.desc()).limit(1))


def get_draft(db, org_id, client_id, draft_id):
    draft = db.scalar(select(ServiceAgreementDraft).where(
        ServiceAgreementDraft.org_id == org_id,
        ServiceAgreementDraft.client_id == client_id,
        ServiceAgreementDraft.id == draft_id))
    if draft is None:
        raise HTTPException(404, "Service agreement draft not found")
    return draft


def get_signed(db, org_id, client_id, draft_id):
    return db.scalar(select(ServiceSignedCopy).where(
        ServiceSignedCopy.org_id == org_id,
        ServiceSignedCopy.client_id == client_id,
        ServiceSignedCopy.draft_id == draft_id))


def screen_ready(s):
    return bool(s and s.client_identity_verified and s.previous_rep_checked and
                s.prior_rep in ("none", "ended_in_writing") and
                s.conflict_status == "none_identified")


def proof_ready(p):
    return bool(p and p.scan_status == "cleared" and p.review_status == "accepted")


def snapshot(db, org_id, client_id):
    s = latest_screen(db, org_id, client_id)
    d = latest_draft(db, org_id, client_id)
    p = get_signed(db, org_id, client_id, d.id) if d else None
    return {
        "client_id": str(client_id),
        "screen": None if s is None else {
            "id": str(s.id), "prior_rep": s.prior_rep, "conflict_status": s.conflict_status,
            "client_identity_verified": s.client_identity_verified,
            "previous_rep_checked": s.previous_rep_checked,
            "details": s.details, "reviewer_sub": s.reviewer_sub,
            "created_at": s.created_at, "clear_for_drafting": screen_ready(s),
        },
        "draft": None if d is None else {
            "id": str(d.id), "version": d.version, "sha256": d.sha256,
            "clauses": d.clauses, "created_at": d.created_at,
            "uses_current_screen": bool(s and s.id == d.screen_id),
        },
        "signed_copy": None if p is None else {
            "id": str(p.id), "sha256": p.sha256, "scan_status": p.scan_status,
            "review_status": p.review_status, "draft_provided_at": p.draft_provided_at,
            "signed_at": p.signed_at, "client_copy_provided_at": p.client_copy_provided_at,
            "reviewed_by_sub": p.reviewed_by_sub, "reviewed_at": p.reviewed_at,
        },
        "eligible_for_engagement_gated_case_creation": bool(
            screen_ready(s) and d and s.id == d.screen_id and proof_ready(p)),
        "legal_service_authority_independently_verified": False,
        "official_ircc_submission_enabled": False,
        "warnings": [
            "This records staff attestation, not independently verified RCIC licence or legal compliance.",
            "A new conflict screen or unsigned agreement version invalidates this gate.",
            "Legacy draft-case routes remain separate and are not a regulated engagement gate.",
        ],
    }


@router.get("/s24/clauses")
def get_clause_headings(org_id: UUID, access: OrgAccess = Depends(get_org_access)):
    allow(access, READ_ROLES)
    return {"source": CODE_24, "heading_schema": "s24-2026-research-v1",
            "items": [{"key": k, "label": v} for k, v in CLAUSES.items()],
            "not_a_legal_template": True}


@router.get("/clients/{client_id}")
def engagement_status(org_id: UUID, client_id: UUID,
                      db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    allow(access, READ_ROLES)
    client_for(db, org_id, client_id)
    return snapshot(db, org_id, client_id)


@router.post("/clients/{client_id}/screens", status_code=201)
def record_screen(org_id: UUID, client_id: UUID, payload: ScreenInput,
                  db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    allow(access, REVIEW)
    client_for(db, org_id, client_id, lock=True)
    s = EngagementScreen(org_id=org_id, client_id=client_id,
                         reviewer_sub=access.principal.sub, **payload.model_dump(
                             exclude={"independently_reviewed_conflicts"}))
    db.add(s)
    db.flush()
    record_event(db, access, "engagement.screen_recorded", "engagement_screen", s.id,
                 {"status": "clear" if screen_ready(s) else "hold"})
    db.commit()
    return {"id": str(s.id), "ready_for_draft": screen_ready(s),
            "professional_review_only": True}


@router.post("/clients/{client_id}/drafts", status_code=201)
def create_service_draft(org_id: UUID, client_id: UUID, payload: AgreementInput,
                         db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    allow(access, REVIEW)
    client_for(db, org_id, client_id, lock=True)
    screen = latest_screen(db, org_id, client_id)
    if not screen_ready(screen):
        raise HTTPException(409, "Identity/prior representation/conflict review must be cleared")
    old = latest_draft(db, org_id, client_id)
    clauses = payload.clauses
    canonical = json.dumps(clauses, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    d = ServiceAgreementDraft(
        org_id=org_id, client_id=client_id, screen_id=screen.id,
        version=old.version + 1 if old else 1,
        clauses=clauses, sha256=sha256(canonical.encode("utf-8")).hexdigest(),
        created_by_sub=access.principal.sub,
    )
    db.add(d)
    db.flush()
    record_event(db, access, "engagement.service_draft_created", "service_draft", d.id,
                 {"version": d.version, "clauses": len(CLAUSES)})
    db.commit()
    return {"id": str(d.id), "version": d.version, "sha256": d.sha256,
            "status": "unsigned_draft", "clauses_covered": len(CLAUSES),
            "code_source": CODE_24, "independently_legally_reviewed": False}


@router.get("/clients/{client_id}/drafts/{draft_id}/print")
def print_draft(org_id: UUID, client_id: UUID, draft_id: UUID,
                db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    allow(access, READ_ROLES)
    d = get_draft(db, org_id, client_id, draft_id)
    rows = "".join("<tr><th>" + html.escape(CLAUSES[k]) + "</th><td>" +
                   html.escape(d.clauses[k]) + "</td></tr>" for k in CLAUSES)
    page = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<title>UNSIGNED RCIC service agreement draft</title><style>"
        "body{font:15px/1.5 Arial,sans-serif;max-width:900px;margin:28px auto;padding:20px}"
        "th,td{border:1px solid #aaa;padding:9px;text-align:left;vertical-align:top}"
        "th{width:35%;background:#eee}table{width:100%;border-collapse:collapse}"
        ".warning{font-weight:bold;color:#800;border:2px solid #a00;padding:12px}"
        "</style></head><body><h1>Service agreement — unapproved draft</h1>"
        "<p class='warning'>NOT SIGNED · NOT REVIEWED FOR LEGAL SUFFICIENCY · FICTIONAL DATA ONLY</p>"
        "<p>Version: " + str(d.version) + " · SHA-256: " +
        html.escape(d.sha256) + "</p><table>" + rows + "</table>"
        "<p>Licensee signature: ___________________ Date: __________</p>"
        "<p>Client signature: _____________________ Date: __________</p>"
        "<p>Source: CICC Code s.24. This form is a development checklist, "
        "not regulator-approved language; the signed copy, professional review, "
        "and client's receipt must be documented separately.</p></body></html>"
    )
    return HTMLResponse(page, headers={
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'",
    })


@router.post("/clients/{client_id}/drafts/{draft_id}/signed-copy", status_code=201)
async def upload_signed(org_id: UUID, client_id: UUID, draft_id: UUID,
                        draft_provided_at: datetime = Form(...),
                        signed_at: datetime = Form(...),
                        client_copy_provided_at: datetime = Form(...),
                        file: UploadFile = File(...),
                        db: Session = Depends(get_db),
                        access: OrgAccess = Depends(get_org_access)):
    allow(access, INTAKE)
    client_for(db, org_id, client_id)
    d = get_draft(db, org_id, client_id, draft_id)
    if latest_draft(db, org_id, client_id).id != d.id:
        raise HTTPException(409, "Only the current agreement version can receive a signed copy")
    if get_signed(db, org_id, client_id, draft_id):
        raise HTTPException(409, "Signed copy already recorded for this revision")
    stamps = [draft_provided_at, signed_at, client_copy_provided_at]
    if any(x.tzinfo is None for x in stamps):
        raise HTTPException(422, "All timestamps must include timezone offsets")
    shown, signed, copied = map(normalized, stamps)
    if not (normalized(d.created_at) <= shown <= signed <= copied <= utcnow() + timedelta(minutes=5)):
        raise HTTPException(422, "Draft delivery, signing and client-copy dates are inconsistent")
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(415, "A signed PDF is required")
    raw = await file.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise HTTPException(413, "PDF exceeds size limit")
    key, digest = save_blob(raw, "application/pdf")
    try:
        try:
            scan_status = scan_bytes(raw).status
        except ScannerUnavailable:
            scan_status = "quarantined"
        proof = ServiceSignedCopy(
            org_id=org_id, client_id=client_id, draft_id=draft_id,
            storage_key=key, sha256=digest, size_bytes=len(raw),
            draft_provided_at=shown, signed_at=signed,
            client_copy_provided_at=copied,
            scan_status=scan_status, review_status="pending",
            created_by_sub=access.principal.sub,
        )
        db.add(proof)
        db.flush()
        record_event(db, access, "engagement.signed_copy_received", "service_signed_copy", proof.id,
                     {"scan_status": scan_status, "draft_version": d.version})
        db.commit()
        return {"signed_copy_id": str(proof.id), "sha256": proof.sha256,
                "scan_status": proof.scan_status,
                "review_status": proof.review_status,
                "signature_authenticity_confirmed_by_system": False}
    except Exception:
        db.rollback()
        delete_failed_blob(key)
        raise


@router.post("/clients/{client_id}/drafts/{draft_id}/scan")
def rescan_proof(org_id: UUID, client_id: UUID, draft_id: UUID,
                 db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    allow(access, REVIEW)
    get_draft(db, org_id, client_id, draft_id)
    proof = get_signed(db, org_id, client_id, draft_id)
    if not proof or proof.scan_status != "quarantined" or proof.review_status != "pending":
        raise HTTPException(409, "Only pending quarantined signed copies may be rescanned")
    raw = load_blob(proof.storage_key)
    if sha256(raw).hexdigest() != proof.sha256:
        raise HTTPException(409, "Signed-copy SHA-256 mismatch")
    try:
        proof.scan_status = scan_bytes(raw).status
    except ScannerUnavailable:
        raise HTTPException(503, "Scanner unavailable; document remains quarantined") from None
    record_event(db, access, "engagement.signed_copy_scanned", "service_signed_copy", proof.id,
                 {"scan_status": proof.scan_status})
    db.commit()
    return {"scan_status": proof.scan_status}


@router.get("/clients/{client_id}/drafts/{draft_id}/signed-copy")
def download_signed(org_id: UUID, client_id: UUID, draft_id: UUID,
                    db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    allow(access, REVIEW)
    get_draft(db, org_id, client_id, draft_id)
    proof = get_signed(db, org_id, client_id, draft_id)
    if not proof:
        raise HTTPException(404, "Signed copy not found")
    if proof.scan_status != "cleared":
        raise HTTPException(423, "Signed copy remains quarantined/rejected")
    raw = load_blob(proof.storage_key)
    if sha256(raw).hexdigest() != proof.sha256:
        raise HTTPException(409, "Signed-copy checksum mismatch")
    record_event(db, access, "engagement.signed_copy_downloaded", "service_signed_copy", proof.id)
    db.commit()
    return Response(raw, media_type="application/pdf", headers={
        "Content-Disposition": 'attachment; filename="signed-service-agreement.pdf"',
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
    })


@router.post("/clients/{client_id}/drafts/{draft_id}/review")
def review_signed(org_id: UUID, client_id: UUID, draft_id: UUID,
                  payload: SignedReviewInput, db: Session = Depends(get_db),
                  access: OrgAccess = Depends(get_org_access)):
    allow(access, REVIEW)
    client_for(db, org_id, client_id, lock=True)
    d = get_draft(db, org_id, client_id, draft_id)
    p = get_signed(db, org_id, client_id, draft_id)
    current_screen = latest_screen(db, org_id, client_id)
    if not p or p.review_status != "pending" or latest_draft(db, org_id, client_id).id != d.id:
        raise HTTPException(409, "No pending signed copy for current agreement version")
    if not screen_ready(current_screen) or current_screen.id != d.screen_id:
        raise HTTPException(409, "Conflict check is stale or unresolved")
    if p.scan_status != "cleared":
        raise HTTPException(423, "Signed copy must first pass malware scanning")
    p.review_status = "accepted" if payload.decision == "accept" else "rejected"
    p.review_note = payload.note.strip()
    p.reviewed_by_sub = access.principal.sub
    p.reviewed_at = utcnow()
    record_event(db, access, "engagement.signed_copy_reviewed", "service_signed_copy", p.id,
                 {"decision": p.review_status, "draft_version": d.version})
    db.commit()
    return {"review_status": p.review_status,
            "signature_verified_cryptographically": False,
            "rcic_registration_verified": False}


@router.post("/clients/{client_id}/open-matter", status_code=201)
def open_engaged_matter(org_id: UUID, client_id: UUID, payload: OpenMatterInput,
                        db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    allow(access, REVIEW)
    client_for(db, org_id, client_id, lock=True)
    s = latest_screen(db, org_id, client_id)
    d = latest_draft(db, org_id, client_id)
    p = get_signed(db, org_id, client_id, d.id) if d else None
    if not (screen_ready(s) and d and d.screen_id == s.id and proof_ready(p)):
        raise HTTPException(409, "A current, cleared, reviewed signed service agreement is required")
    # Select only authenticated active staff with a professional role; the
    # CICC licence itself is NOT checked by this prototype.
    if not active_staff_member(db, org_id, payload.professional_sub,
                               ("owner", "admin", "consultant")):
        raise HTTPException(422, "Assigned professional must be an active firm owner/admin/consultant")
    case = Case(org_id=org_id, client_id=client_id, application_type=payload.application_type,
                title=payload.title.strip(), status="draft")
    db.add(case)
    db.flush()
    assignment = MatterAssignment(
        org_id=org_id, client_id=client_id, case_id=case.id, draft_id=d.id,
        professional_sub=payload.professional_sub, assigned_by_sub=access.principal.sub)
    db.add(assignment)
    db.flush()
    record_event(db, access, "engagement.matter_opened", "case", case.id,
                 {"draft_id": str(d.id), "assigned_professional_sub": payload.professional_sub,
                  "staff_attestation_only": True})
    db.commit()
    return {"case_id": str(case.id), "client_id": str(client_id),
            "assignment_id": str(assignment.id),
            "professional_sub": payload.professional_sub, "agreement_version": d.version,
            "case_status": "draft",
            "regulated_authority_independently_verified": False,
            "legacy_draft_case_routes_remain_outside_this_gate": True}


@router.get("/clients/{client_id}/matters")
def engaged_matters(org_id: UUID, client_id: UUID,
                    db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    allow(access, READ_ROLES)
    client_for(db, org_id, client_id)
    q = select(MatterAssignment).where(
        MatterAssignment.org_id == org_id, MatterAssignment.client_id == client_id)
    if access.role not in MANAGERS:
        q = q.where(MatterAssignment.case_id.in_(
            visible_case_ids(org_id, access.principal.sub, access.role)))
    rows = db.scalars(q.order_by(MatterAssignment.created_at.desc()).limit(50)).all()
    return [{"id": str(x.id), "case_id": str(x.case_id), "draft_id": str(x.draft_id),
             "professional_sub": x.professional_sub, "created_at": x.created_at,
             "staff_assignment_only": True} for x in rows]


@router.get("/clients/{client_id}/history")
def engagement_revision_history(
    org_id: UUID, client_id: UUID,
    db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access),
):
    """Show version changes without rewriting prior professional decisions."""
    allow(access, REVIEW)
    client_for(db, org_id, client_id)
    current_screen = latest_screen(db, org_id, client_id)
    current_draft = latest_draft(db, org_id, client_id)
    screens = db.scalars(select(EngagementScreen).where(
        EngagementScreen.org_id == org_id, EngagementScreen.client_id == client_id
    ).order_by(EngagementScreen.created_at.desc(), EngagementScreen.id.desc()).limit(50)).all()
    drafts = db.scalars(select(ServiceAgreementDraft).where(
        ServiceAgreementDraft.org_id == org_id, ServiceAgreementDraft.client_id == client_id
    ).order_by(ServiceAgreementDraft.version.desc()).limit(50)).all()
    return {
        "client_id": str(client_id),
        "screens": [{
            "id": str(e.id), "created_at": e.created_at,
            "reviewer_sub": e.reviewer_sub, "prior_rep": e.prior_rep,
            "conflict_status": e.conflict_status,
            "currently_latest": bool(current_screen and e.id == current_screen.id),
            "professional_attestation_only": True,
        } for e in screens],
        "drafts": [{
            "id": str(d.id), "version": d.version, "sha256": d.sha256,
            "created_at": d.created_at, "created_by_sub": d.created_by_sub,
            "screen_id": str(d.screen_id),
            "currently_latest": bool(current_draft and d.id == current_draft.id),
            "screen_still_latest": bool(current_screen and d.screen_id == current_screen.id),
            "signed_copy": {
                "exists": bool(p := get_signed(db, org_id, client_id, d.id)),
                "scan_status": p.scan_status if p else None,
                "review_status": p.review_status if p else None,
                "accepted_by_staff": proof_ready(p),
            },
        } for d in drafts],
        "history_limit": 50,
        "not_independent_regulatory_validation": True,
    }


@router.get("/cases/{case_id}")
def case_engagement_status(
    org_id: UUID, case_id: UUID,
    db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access),
):
    """Reconcile actual case assignment with newest signed terms and conflict review.

    Does not itself grant or revoke case access. A legacy case is reported as
    unengaged; it is not implicitly authorized by another client's agreement.
    """
    allow(access, READ_ROLES)
    case = db.scalar(select(Case).where(Case.org_id == org_id, Case.id == case_id))
    if case is None:
        raise HTTPException(404, "Case not found")
    assignment = db.scalar(select(MatterAssignment).where(
        MatterAssignment.org_id == org_id, MatterAssignment.case_id == case_id,
        MatterAssignment.client_id == case.client_id))
    if assignment is None:
        return {
            "case_id": str(case.id), "engagement_link_missing": True,
            "assigned_professional_sub": None,
            "has_current_reviewed_signed_agreement": False,
            "requires_professional_reconciliation": True,
            "warning": "Legacy/unlinked draft case. No signed service agreement is evidenced by the engagement module.",
        }
    bound = get_draft(db, org_id, case.client_id, assignment.draft_id)
    evidence = get_signed(db, org_id, case.client_id, bound.id)
    screen = latest_screen(db, org_id, case.client_id)
    newest = latest_draft(db, org_id, case.client_id)
    still_latest = bool(newest and newest.id == bound.id)
    screen_matches = bool(screen and screen.id == bound.screen_id and screen_ready(screen))
    signed_validated_by_staff = proof_ready(evidence)
    current = still_latest and screen_matches and signed_validated_by_staff
    return {
        "case_id": str(case.id), "client_id": str(case.client_id),
        "engagement_link_missing": False,
        "assigned_professional_sub": assignment.professional_sub,
        "agreement_version": bound.version, "agreement_sha256": bound.sha256,
        "latest_agreement_version": newest.version if newest else None,
        "assigned_agreement_is_latest": still_latest,
        "assigned_screen_still_current_and_clear": screen_matches,
        "linked_signed_copy_accepted_by_staff": signed_validated_by_staff,
        "has_current_reviewed_signed_agreement": current,
        "requires_professional_reconciliation": not current,
        "warning": (
            "Current staff-reviewed revision matches the case link. This does NOT prove regulatory authority."
            if current else
            "Newer agreement or conflict review requires professional reconciliation. "
            "This status does not itself invalidate or amend a legal agreement."
        ),
    }
