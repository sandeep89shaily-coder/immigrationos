"""Case-scoped OIDC client portal and consultant-managed document requests.

No public links to confidential content; invitations are one-use, short-lived,
email-bound and require a verified OIDC identity. Development/synthetic data only.
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.access import OrgAccess, allow, get_org_access
from app.auth import Principal, get_principal
from app.db import get_db, set_db_context
from app.main import record_event
from app.models import Case, CaseDocument, Client
from app.portal_models import DocumentRequest, PortalGrant, PortalInvitation, PortalSubmission
from app.schemas import Role
from app.storage import MAX_BYTES, delete_failed_blob, load_blob, save_blob
from app.malware_scan import scan_bytes, ScannerUnavailable

staff_router = APIRouter(prefix='/api/v1/orgs/{org_id}/cases/{case_id}/portal', tags=['client-portal-staff'])
router = APIRouter(prefix='/api/v1/client', tags=['client-portal'])
STAFF = {Role.owner, Role.admin, Role.consultant}
INTAKE = STAFF | {Role.assistant}


def now():
    return datetime.now(timezone.utc)


def clean_email(email: str | None) -> str:
    return (email or '').strip().casefold()


def authenticated_email(principal: Principal) -> str:
    email = clean_email(principal.email)
    if not principal.email_verified or not email or '@' not in email:
        raise HTTPException(status_code=403, detail='A verified identity-provider email is required')
    return email


def db_verified_email(db: Session, principal: Principal):
    """Only set from cryptographically verified OIDC claims, not request parameters."""
    email = authenticated_email(principal)
    set_db_context(db, principal.sub)
    if db.bind and db.bind.dialect.name == 'postgresql':
        db.execute(text("SELECT set_config('app.verified_email', :email, true)"), {'email': email})
    return email


def ensure_staff_case(db: Session, org_id: UUID, case_id: UUID) -> Case:
    case = db.scalar(select(Case).where(Case.org_id == org_id, Case.id == case_id))
    if case is None:
        raise HTTPException(404, 'Case not found')
    return case


def active_grant(db: Session, principal: Principal, case_id: UUID) -> PortalGrant:
    set_db_context(db, principal.sub)
    grant = db.scalar(select(PortalGrant).where(
        PortalGrant.case_id == case_id, PortalGrant.principal_sub == principal.sub,
        PortalGrant.revoked_at.is_(None)))
    if grant is None:
        raise HTTPException(404, 'Case not available')
    set_db_context(db, principal.sub, grant.org_id)
    return grant


class InviteCreated(BaseModel):
    invitation_id: UUID
    invite_token: str
    expires_at: datetime
    warning: str = 'Shown once. Deliver through an approved secure channel; do not log or email casually.'


class InviteAccepted(BaseModel):
    case_id: UUID
    message: str = 'Access granted to the authenticated identity'


class InviteClaim(BaseModel):
    token: str = Field(min_length=36, max_length=256)


class DocumentRequestCreate(BaseModel):
    title: str = Field(min_length=3, max_length=180)
    instructions: str = Field(default='', max_length=1200)
    document_type: str = Field(min_length=2, max_length=80, pattern=r'^[a-z][a-z0-9_]{1,79}$')
    due_at: datetime | None = None


class RequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    case_id: UUID
    title: str
    instructions: str
    document_type: str
    status: str
    due_at: datetime | None
    created_at: datetime


class PortalCaseRead(BaseModel):
    id: UUID
    title: str
    application_type: str
    status: str


class SubmissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    case_id: UUID
    request_id: UUID
    document_id: UUID
    scan_status: str
    scan_engine: str | None = None
    scanned_at: datetime | None = None
    created_at: datetime


@staff_router.post('/invitations', response_model=InviteCreated, status_code=201)
def issue_invitation(org_id: UUID, case_id: UUID, db: Session = Depends(get_db),
                     access: OrgAccess = Depends(get_org_access)):
    allow(access, STAFF)
    case = ensure_staff_case(db, org_id, case_id)
    if case.status == 'closed':
        raise HTTPException(409, 'Closed cases cannot be invited')
    client = db.scalar(select(Client).where(Client.org_id == org_id, Client.id == case.client_id))
    email = clean_email(client.email if client else None)
    if not email or '@' not in email:
        raise HTTPException(422, 'Client must have a verified contact email in the case record')
    token = secrets.token_urlsafe(48)
    expiry = now() + timedelta(hours=48)
    invite = PortalInvitation(org_id=org_id, case_id=case_id, invited_email=email,
                              token_hash=hashlib.sha256(token.encode()).hexdigest(),
                              expires_at=expiry, created_by_sub=access.principal.sub)
    db.add(invite)
    db.flush()
    record_event(db, access, 'portal.invitation_created', 'portal_invitation', invite.id)
    db.commit()
    return InviteCreated(invitation_id=invite.id, invite_token=token, expires_at=expiry)


@staff_router.post('/invitations/{invitation_id}/revoke')
def revoke_invitation(org_id: UUID, case_id: UUID, invitation_id: UUID,
                      db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    allow(access, STAFF)
    ensure_staff_case(db, org_id, case_id)
    invite = db.scalar(select(PortalInvitation).where(PortalInvitation.org_id == org_id,
                       PortalInvitation.case_id == case_id, PortalInvitation.id == invitation_id).with_for_update())
    if not invite:
        raise HTTPException(404, 'Invitation not found')
    if invite.accepted_at or invite.revoked_at:
        raise HTTPException(409, 'Invitation is no longer pending')
    invite.revoked_at = now()
    record_event(db, access, 'portal.invitation_revoked', 'portal_invitation', invite.id)
    db.commit()
    return {'status': 'revoked'}


@staff_router.post('/requests', response_model=RequestRead, status_code=201)
def make_request(org_id: UUID, case_id: UUID, payload: DocumentRequestCreate,
                 db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    allow(access, INTAKE)
    case = ensure_staff_case(db, org_id, case_id)
    if case.status == 'closed':
        raise HTTPException(409, 'Closed case')
    request = DocumentRequest(org_id=org_id, case_id=case_id, created_by_sub=access.principal.sub,
                              **payload.model_dump())
    db.add(request)
    db.flush()
    record_event(db, access, 'portal.document_requested', 'document_request', request.id)
    db.commit()
    return request


@staff_router.get('/requests', response_model=list[RequestRead])
def staff_requests(org_id: UUID, case_id: UUID, db: Session = Depends(get_db),
                   access: OrgAccess = Depends(get_org_access)):
    ensure_staff_case(db, org_id, case_id)
    return db.scalars(select(DocumentRequest).where(DocumentRequest.org_id == org_id,
                      DocumentRequest.case_id == case_id).order_by(DocumentRequest.created_at)).all()


@staff_router.get('/submissions', response_model=list[SubmissionRead])
def staff_submissions(org_id: UUID, case_id: UUID, db: Session = Depends(get_db),
                      access: OrgAccess = Depends(get_org_access)):
    ensure_staff_case(db, org_id, case_id)
    return db.scalars(select(PortalSubmission).where(PortalSubmission.org_id == org_id,
                      PortalSubmission.case_id == case_id).order_by(PortalSubmission.created_at)).all()


@staff_router.post('/submissions/{submission_id}/scan', response_model=SubmissionRead)
def scan_portal_submission(org_id: UUID, case_id: UUID, submission_id: UUID,
                           db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    # DEV preview: scans one 8MB max file synchronously. Production requires a durable,
    # independently isolated scan worker and stronger CDR/retention guarantees.
    allow(access, STAFF)
    ensure_staff_case(db, org_id, case_id)
    submission = db.scalar(select(PortalSubmission).where(
        PortalSubmission.org_id == org_id, PortalSubmission.case_id == case_id,
        PortalSubmission.id == submission_id).with_for_update())
    if submission is None:
        raise HTTPException(404, 'Submission not found')
    if submission.scan_status != 'quarantined':
        raise HTTPException(409, 'Submission already has a final scanning decision')
    doc = db.scalar(select(CaseDocument).where(CaseDocument.org_id == org_id,
                    CaseDocument.case_id == case_id, CaseDocument.id == submission.document_id))
    if doc is None:
        raise HTTPException(404, 'Source document unavailable')
    raw = load_blob(doc.storage_key)
    if hashlib.sha256(raw).hexdigest() != doc.sha256:
        raise HTTPException(503, 'File integrity check failed; remains quarantined')
    try:
        verdict = scan_bytes(raw)
    except ScannerUnavailable:
        # Fail closed: retain quarantine, do not log confidential file contents.
        raise HTTPException(503, 'Scanning failed or is unavailable; file remains quarantined') from None
    submission.scan_status = verdict.status
    submission.scan_engine = verdict.engine
    submission.scanned_at = now()
    record_event(db, access, 'portal.malware_scan_' + verdict.status,
                 'portal_submission', submission.id, {'engine': verdict.engine})
    db.commit()
    return submission


@staff_router.post('/grants/{grant_id}/revoke')
def revoke_access(org_id: UUID, case_id: UUID, grant_id: UUID,
                  db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    allow(access, STAFF)
    ensure_staff_case(db, org_id, case_id)
    grant = db.scalar(select(PortalGrant).where(PortalGrant.org_id == org_id,
                      PortalGrant.case_id == case_id, PortalGrant.id == grant_id).with_for_update())
    if not grant:
        raise HTTPException(404, 'Grant not found')
    if grant.revoked_at:
        raise HTTPException(409, 'Already revoked')
    grant.revoked_at = now()
    record_event(db, access, 'portal.access_revoked', 'portal_grant', grant.id)
    db.commit()
    return {'status': 'revoked'}


@staff_router.get('/grants')
def staff_grants(org_id: UUID, case_id: UUID, db: Session = Depends(get_db),
                 access: OrgAccess = Depends(get_org_access)):
    allow(access, STAFF)
    ensure_staff_case(db, org_id, case_id)
    grants = db.scalars(select(PortalGrant).where(PortalGrant.org_id == org_id,
                        PortalGrant.case_id == case_id)).all()
    return [{'id': g.id, 'is_active': g.revoked_at is None, 'granted_at': g.granted_at} for g in grants]


@router.post('/invitations/accept', response_model=InviteAccepted)
def accept_invite(payload: InviteClaim, db: Session = Depends(get_db),
                  principal: Principal = Depends(get_principal)):
    email = db_verified_email(db, principal)
    digest = hashlib.sha256(payload.token.encode()).hexdigest()
    invitation = db.scalar(select(PortalInvitation).where(
        PortalInvitation.token_hash == digest, PortalInvitation.invited_email == email).with_for_update())
    expired = invitation is None or (invitation.expires_at.replace(tzinfo=timezone.utc) <= now())
    if invitation is None or invitation.revoked_at or invitation.accepted_at or expired:
        raise HTTPException(404, 'Invitation unavailable')
    invitation.accepted_at = now()
    invitation.accepted_by_sub = principal.sub
    db.flush()
    set_db_context(db, principal.sub, invitation.org_id)
    existing = db.scalar(select(PortalGrant).where(PortalGrant.org_id == invitation.org_id,
                          PortalGrant.case_id == invitation.case_id, PortalGrant.principal_sub == principal.sub))
    if existing is not None:
        if existing.revoked_at is not None:
            raise HTTPException(409, 'Prior access revoked; contact the practice')
        raise HTTPException(409, 'Access already granted')
    grant = PortalGrant(org_id=invitation.org_id, case_id=invitation.case_id, principal_sub=principal.sub)
    db.add(grant)
    db.flush()
    case = db.scalar(select(Case).where(Case.org_id == invitation.org_id,
                     Case.id == invitation.case_id))
    if case is None or case.status == 'closed':
        raise HTTPException(409, 'This case no longer accepts portal access')
    record_event(db, OrgAccess(invitation.org_id, principal, Role.viewer),
                 'portal.invitation_accepted', 'portal_grant', grant.id)
    db.commit()
    return InviteAccepted(case_id=invitation.case_id)


@router.get('/cases', response_model=list[PortalCaseRead])
def my_cases(db: Session = Depends(get_db), principal: Principal = Depends(get_principal)):
    db_verified_email(db, principal)
    grants = db.scalars(select(PortalGrant).where(PortalGrant.principal_sub == principal.sub,
                        PortalGrant.revoked_at.is_(None))).all()
    result = []
    for grant in grants:
        set_db_context(db, principal.sub, grant.org_id)
        case = db.scalar(select(Case).where(Case.org_id == grant.org_id,
                         Case.id == grant.case_id))
        if case is not None:
            result.append(PortalCaseRead(id=case.id, title=case.title,
                                        application_type=case.application_type, status=case.status))
    return result


@router.get('/cases/{case_id}/requests', response_model=list[RequestRead])
def my_requests(case_id: UUID, db: Session = Depends(get_db),
                principal: Principal = Depends(get_principal)):
    db_verified_email(db, principal)
    grant = active_grant(db, principal, case_id)
    return db.scalars(select(DocumentRequest).where(DocumentRequest.org_id == grant.org_id,
                      DocumentRequest.case_id == case_id).order_by(DocumentRequest.created_at)).all()


@router.post('/cases/{case_id}/requests/{request_id}/upload', response_model=SubmissionRead, status_code=201)
async def client_upload(case_id: UUID, request_id: UUID, file: UploadFile = File(...),
                        db: Session = Depends(get_db), principal: Principal = Depends(get_principal)):
    db_verified_email(db, principal)
    grant = active_grant(db, principal, case_id)
    case = db.scalar(select(Case).where(Case.org_id == grant.org_id, Case.id == case_id))
    if case is None or case.status == 'closed':
        raise HTTPException(409, 'Case is no longer accepting uploads')
    request = db.scalar(select(DocumentRequest).where(DocumentRequest.org_id == grant.org_id,
                        DocumentRequest.case_id == case_id, DocumentRequest.id == request_id).with_for_update())
    if request is None:
        raise HTTPException(404, 'Document request unavailable')
    if request.status != 'open':
        raise HTTPException(409, 'Request is not open')
    name = (file.filename or 'untitled').replace('\\','/').split('/')[-1]
    if not name or len(name) > 180 or any(ord(c) < 32 for c in name):
        raise HTTPException(422, 'Invalid filename')
    mime = (file.content_type or '').lower()
    blob = await file.read(MAX_BYTES + 1)
    storage_key, digest = save_blob(blob, mime)
    doc = CaseDocument(org_id=grant.org_id, case_id=case_id, filename=name,
                       document_type=request.document_type, mime_type=mime,
                       size_bytes=len(blob), sha256=digest, storage_key=storage_key,
                       uploaded_by_sub=principal.sub)
    try:
        db.add(doc)
        db.flush()
        submission = PortalSubmission(org_id=grant.org_id, case_id=case_id,
                                      request_id=request_id, document_id=doc.id,
                                      uploaded_by_sub=principal.sub, scan_status='quarantined')
        db.add(submission)
        request.status = 'received'
        db.flush()
        record_event(db, OrgAccess(grant.org_id, principal, Role.viewer),
                     'portal.document_received_quarantined', 'portal_submission', submission.id)
        db.commit()
    except Exception:
        db.rollback()
        delete_failed_blob(storage_key)
        raise
    return submission
