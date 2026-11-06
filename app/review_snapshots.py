"""Evidence-change-aware review history. No final IRCC/legal approval is implied."""
import hashlib
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.access import OrgAccess, READ_ROLES, allow, get_org_access
from app.db import get_db
from app.evidence_matrix import TEMPLATE_VERSION, _case, _matrix
from app.main import record_event
from app.models import (CaseDocument, CaseFact, CaseIssue, CaseTask, EvidenceReviewSnapshot)
from app.portal_models import DocumentRequest, PortalSubmission
from app.schemas import Role

router = APIRouter(prefix='/api/v1/orgs/{org_id}/cases/{case_id}/reviews', tags=['evidence-review-history'])
REVIEW_ROLES = {Role.owner, Role.admin, Role.consultant}


class RecordReview(BaseModel):
    filing_context: str = Field(pattern=r'^(inside_canada|outside_canada)$')
    expected_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    review_note: str = Field(min_length=20, max_length=1200)
    reviewed_current_ircc_sources: bool


def case_fingerprint(db: Session, org_id: UUID, case_id: UUID, filing_context: str) -> str:
    """Hash a consistent canonical representation; store no client facts in audit.

    An intervening write makes the saved hash stale on the next read,
    even if the previous reviewer was fully authorized at the time.
    """
    case = _case(db, org_id, case_id)
    def rows(model, fields):
        objects = db.scalars(select(model).where(model.org_id == org_id, model.case_id == case_id)).all()
        return sorted([[str(getattr(obj, key)) if getattr(obj, key) is not None else None
                        for key in fields] for obj in objects], key=lambda values: str(values[0]))
    payload = {
        'case_id': str(case.id), 'status': case.status, 'application_type': case.application_type,
        'filing_context': filing_context, 'template_version': TEMPLATE_VERSION,
        'documents': rows(CaseDocument, ('id', 'sha256', 'document_type')),
        'facts': rows(CaseFact, ('id', 'field_path', 'value', 'review_status', 'document_id', 'source_page')),
        'issues': rows(CaseIssue, ('id', 'status', 'resolution')),
        'tasks': rows(CaseTask, ('id', 'status')),
        'requests': rows(DocumentRequest, ('id', 'status', 'document_type')),
        'submissions': rows(PortalSubmission, ('id', 'scan_status', 'document_id')),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def _current(db, org_id, case_id, filing_context):
    sha = case_fingerprint(db, org_id, case_id, filing_context)
    matrix = _matrix(db, org_id, case_id, filing_context)
    return {'case_id': str(case_id), 'filing_context': filing_context,
            'case_sha256': sha, 'template_version': TEMPLATE_VERSION,
            'open_evidence_issue_count': matrix['open_evidence_issue_count'],
            'source_recheck_required': matrix['source_recheck_required'],
            'review_only': True, 'ircc_submission_authorized': False,
            'warning': 'Internal staff review only. The firm must independently verify RCIC credentials, '
                       'current IRCC instructions and legal requirements. This is not permission to submit.'}


@router.get('/current')
def current_review(org_id: UUID, case_id: UUID,
                   filing_context: str = Query(pattern=r'^(inside_canada|outside_canada)$'),
                   db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    allow(access, READ_ROLES)
    return _current(db, org_id, case_id, filing_context)


@router.get('/history')
def review_history(org_id: UUID, case_id: UUID,
                   filing_context: str = Query(pattern=r'^(inside_canada|outside_canada)$'),
                   db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    allow(access, READ_ROLES)
    current = _current(db, org_id, case_id, filing_context)
    snapshots = db.scalars(select(EvidenceReviewSnapshot).where(
        EvidenceReviewSnapshot.org_id == org_id,
        EvidenceReviewSnapshot.case_id == case_id,
        EvidenceReviewSnapshot.filing_context == filing_context,
    ).order_by(EvidenceReviewSnapshot.created_at.desc(), EvidenceReviewSnapshot.id.desc()).limit(25)).all()
    return {'current': current, 'history': [{
        'id': str(s.id), 'created_at': s.created_at, 'reviewer_sub': s.reviewer_sub,
        'review_note': s.review_note, 'open_issues_at_review': s.open_issues_at_review,
        'template_version': s.template_version, 'case_sha256': s.case_sha256,
        'is_current': (s.case_sha256 == current['case_sha256'] and s.template_version == TEMPLATE_VERSION),
        'review_only': True,
    } for s in snapshots]}


@router.post('/record', status_code=201)
def record_review(org_id: UUID, case_id: UUID, payload: RecordReview,
                  db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    allow(access, REVIEW_ROLES)
    case = _case(db, org_id, case_id, lock=True)
    if case.status == 'closed':
        raise HTTPException(409, 'Closed cases are read-only')
    if payload.reviewed_current_ircc_sources is not True:
        raise HTTPException(422, 'Reviewer must confirm checking current official sources independently')
    current = _current(db, org_id, case_id, payload.filing_context)
    if payload.expected_sha256 != current['case_sha256']:
        raise HTTPException(409, 'Case evidence changed; refresh and review the updated evidence')
    record = EvidenceReviewSnapshot(org_id=org_id, case_id=case_id,
        filing_context=payload.filing_context, template_version=TEMPLATE_VERSION,
        case_sha256=current['case_sha256'], reviewer_sub=access.principal.sub,
        review_note=payload.review_note,
        open_issues_at_review=current['open_evidence_issue_count'])
    db.add(record)
    db.flush()
    record_event(db, access, 'evidence.operational_review_recorded', 'evidence_review_snapshot', record.id,
                 {'case_id': str(case_id), 'filing_context': payload.filing_context})
    db.commit()
    return {'id': str(record.id), 'case_sha256': record.case_sha256,
            'review_only': True, 'ircc_submission_authorized': False}
