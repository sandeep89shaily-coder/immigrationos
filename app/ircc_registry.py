"""Conservative, observed-source registry for IRCC form *preparation*.

This is NOT an IRCC-validated PDF mapping or legal decision engine. All source
revisions are observations at a given date; they are not auto-authoritative.
"""
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.access import OrgAccess, READ_ROLES, allow, get_org_access
from app.db import get_db
from app.models import Case, CaseDocument, CaseFact, CaseIssue
from app.portal_models import PortalSubmission


@dataclass(frozen=True)
class ObservedForm:
    code: str
    title: str
    ircc_source_url: str
    revision_label: str
    last_checked: date
    application_type: str
    filing_context: str
    # These are a deliberately incomplete *internal* subset, not PDF field IDs.
    preview_fields: tuple[tuple[str, str], ...]


COMMON_FIELDS = (
    ('Given name', 'identity.given_name'),
    ('Family name', 'identity.family_name'),
    ('Date of birth', 'identity.date_of_birth'),
    ('Citizenship', 'identity.citizenship'),
    ('Passport number', 'identity.passport_number'),
)

REGISTRY: dict[str, ObservedForm] = {
    'IMM1294': ObservedForm(
        code='IMM1294', title='Application for a Study Permit Made Outside of Canada',
        ircc_source_url='https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm1294.html',
        revision_label='June 2026 (observed on official IRCC page)', last_checked=date(2026, 11, 5),
        application_type='study_permit', filing_context='outside_canada',
        preview_fields=COMMON_FIELDS + (('School or institution', 'education.institution'),),
    ),
    'IMM5709': ObservedForm(
        code='IMM5709', title='Application to Change Conditions, Extend my Stay or Remain in Canada as a Student',
        ircc_source_url='https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm5709.html',
        revision_label='June 2026 (observed on official IRCC page)', last_checked=date(2026, 11, 5),
        application_type='study_permit', filing_context='inside_canada',
        preview_fields=COMMON_FIELDS + (('School or institution', 'education.institution'),),
    ),
}

router = APIRouter(prefix='/api/v1/orgs/{org_id}/ircc', tags=['ircc-form-registry'])


def source_metadata(source: ObservedForm, today: date | None = None) -> dict:
    today = today or date.today()
    days = max(0, (today - source.last_checked).days)
    return {
        'code': source.code, 'title': source.title,
        'ircc_source_url': source.ircc_source_url,
        'observed_revision': source.revision_label,
        'observed_on': source.last_checked.isoformat(),
        'days_since_source_review': days,
        'source_recheck_required': days > 30,
        'application_type': source.application_type,
        'filing_context': source.filing_context,
        'mapping_status': 'internal_preview_only',
        'official_pdf_generation_supported': False,
        'submission_supported': False,
    }


def preview(source: ObservedForm, facts: list[CaseFact], open_issues: int, today: date | None = None) -> dict:
    verified: dict[str, list[CaseFact]] = {}
    for fact in facts:
        if fact.review_status == 'verified':
            verified.setdefault(fact.field_path, []).append(fact)
    fields = []
    for label, path in source.preview_fields:
        candidates = verified.get(path, [])
        distinct = {f.value.strip() for f in candidates}
        if len(distinct) == 1:
            value = next(iter(distinct))
            status = 'verified'
        else:
            value = None
            status = 'ambiguous' if len(distinct) > 1 else 'missing'
        fields.append({
            'label': label, 'canonical_path': path, 'value': value,
            'status': status,
            'fact_ids': sorted(str(f.id) for f in candidates),
            'document_ids': sorted({str(f.document_id) for f in candidates if f.document_id}),
        })
    return {
        **source_metadata(source, today=today),
        'fields': fields,
        'open_case_evidence_issues': open_issues,
        'review_required': True,
        'release_status': 'blocked_no_validated_ircc_pdf_adapter',
        'warnings': [
            'Internal field coverage preview only: incomplete mapping, not an official IRCC form.',
            'A licensed professional must check the applicable IRCC instructions, contextual requirements and form revision.',
            *(['Unresolved evidence contradictions require review.'] if open_issues else []),
            *(['Last recorded official source review is more than 30 days old.']
              if source_metadata(source, today=today)['source_recheck_required'] else []),
        ],
    }


@router.get('/forms')
def list_form_sources(org_id: UUID, access: OrgAccess = Depends(get_org_access)):
    allow(access, READ_ROLES)
    return [source_metadata(source) for source in REGISTRY.values()]


@router.get('/cases/{case_id}/forms/{form_code}/preview')
def preview_form_data(org_id: UUID, case_id: UUID, form_code: str,
                      filing_context: str = Query(min_length=3, max_length=40),
                      db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    allow(access, READ_ROLES)
    case = db.scalar(select(Case).where(Case.org_id == org_id, Case.id == case_id))
    if case is None:
        raise HTTPException(404, 'Matter not found')
    source = REGISTRY.get(form_code.upper())
    if source is None:
        raise HTTPException(404, 'Form not in the reviewed registry')
    if source.application_type != case.application_type or source.filing_context != filing_context:
        raise HTTPException(409, 'Form does not match the case application type and declared filing context')
    # Preview must not surface even a previously verified fact from a client
    # document that is still quarantined, rejected, or linked to another case.
    all_facts = db.scalars(select(CaseFact).where(
        CaseFact.org_id == org_id, CaseFact.case_id == case_id)).all()
    document_ids = set(db.scalars(select(CaseDocument.id).where(
        CaseDocument.org_id == org_id, CaseDocument.case_id == case_id)).all())
    blocked_ids = set(db.scalars(select(PortalSubmission.document_id).where(
        PortalSubmission.org_id == org_id, PortalSubmission.case_id == case_id,
        PortalSubmission.scan_status != 'cleared')).all())
    facts = [f for f in all_facts if f.document_id is None or
             (f.document_id in document_ids and f.document_id not in blocked_ids)]
    issues = db.scalar(select(func.count()).select_from(CaseIssue).where(
        CaseIssue.org_id == org_id, CaseIssue.case_id == case_id, CaseIssue.status == 'open')) or 0
    result = preview(source, facts, issues)
    excluded = len(all_facts) - len(facts)
    result['excluded_untrusted_document_facts'] = excluded
    if excluded:
        result['warnings'].append('Facts linked to quarantined or cross-case documents were excluded.')
    return result
