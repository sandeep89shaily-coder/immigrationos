"""Tenant-scoped case workspace endpoints. All routes require verified firm membership.

Human review is mandatory. Readiness endpoints produce operational warnings only.
"""
import hashlib
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.access import OrgAccess, READ_ROLES, WRITE_ROLES, allow, get_org_access
from app.db import get_db
from app.main import record_event
from app.models import Case, CaseDocument, CaseFact, CaseIssue, CaseTask, Client, FactSuggestion
from app.portal_models import PortalSubmission
from app.schemas import Role
from app.storage import MAX_BYTES, delete_failed_blob, load_blob, save_blob
from app.extraction import propose_facts
from app.workspace_schemas import (
    CaseReadiness, DashboardRead, DocumentRead, FactCreate, FactRead, FactReview,
    FactReviewStatus, IssueRead, IssueResolution, TaskCreate, TaskRead,
    SuggestionRead, SuggestionDecision,
)

router = APIRouter(prefix="/api/v1/orgs/{org_id}", tags=["workspace"])
INTAKE_ROLES = WRITE_ROLES | {Role.assistant}
REVIEW_ROLES = {Role.owner, Role.admin, Role.consultant}  # Credential verification is a future requirement.


def get_case(db: Session, org_id: UUID, case_id: UUID) -> Case:
    case = db.scalar(select(Case).where(Case.org_id == org_id, Case.id == case_id))
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


def ensure_case_open(db: Session, org_id: UUID, case_id: UUID) -> Case:
    case = get_case(db, org_id, case_id)
    if case.status == 'closed':
        raise HTTPException(status_code=409, detail='Closed cases are read-only')
    return case


def existing_document(db: Session, org_id: UUID, case_id: UUID, document_id: UUID) -> CaseDocument:
    doc = db.scalar(select(CaseDocument).where(CaseDocument.org_id == org_id,
                                               CaseDocument.case_id == case_id,
                                               CaseDocument.id == document_id))
    if doc is None:
        raise HTTPException(status_code=404, detail="Document not found in this case")
    quarantined = db.scalar(select(PortalSubmission).where(PortalSubmission.org_id == org_id,
        PortalSubmission.case_id == case_id, PortalSubmission.document_id == document_id,
        PortalSubmission.scan_status != "cleared"))
    if quarantined is not None:
        raise HTTPException(status_code=423, detail="Client document quarantined pending malware scanning")
    return doc


@router.get("/dashboard", response_model=DashboardRead)
def dashboard(org_id: UUID, db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    allow(access, READ_ROLES)
    def count(model, *conditions):
        return db.scalar(select(func.count()).select_from(model).where(model.org_id == org_id, *conditions)) or 0
    return DashboardRead(
        clients=count(Client), cases=count(Case), in_review=count(Case, Case.status == 'review'),
        open_tasks=count(CaseTask, CaseTask.status == 'open'),
        open_issues=count(CaseIssue, CaseIssue.status == 'open'),
        documents=count(CaseDocument),
    )


@router.get("/tasks", response_model=list[TaskRead])
def organization_tasks(org_id: UUID, status: str = Query('open', pattern=r'^(open|complete|all)$'),
                       db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    q = select(CaseTask).where(CaseTask.org_id == org_id)
    if status != 'all':
        q = q.where(CaseTask.status == status)
    return db.scalars(q.order_by(CaseTask.due_at, CaseTask.created_at).limit(200)).all()


@router.get("/issues", response_model=list[IssueRead])
def organization_issues(org_id: UUID, status: str = Query('open', pattern=r'^(open|resolved|dismissed|all)$'),
                        db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    q = select(CaseIssue).where(CaseIssue.org_id == org_id)
    if status != 'all':
        q = q.where(CaseIssue.status == status)
    return db.scalars(q.order_by(CaseIssue.created_at.desc()).limit(200)).all()


@router.get("/cases/{case_id}/tasks", response_model=list[TaskRead])
def case_tasks(org_id: UUID, case_id: UUID, db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    get_case(db, org_id, case_id)
    return db.scalars(select(CaseTask).where(CaseTask.org_id == org_id, CaseTask.case_id == case_id)
                      .order_by(CaseTask.created_at)).all()


@router.post("/cases/{case_id}/tasks", response_model=TaskRead, status_code=201)
def create_task(org_id: UUID, case_id: UUID, payload: TaskCreate, db: Session = Depends(get_db),
                access: OrgAccess = Depends(get_org_access)):
    allow(access, INTAKE_ROLES)
    ensure_case_open(db, org_id, case_id)
    task = CaseTask(org_id=org_id, case_id=case_id, created_by_sub=access.principal.sub, **payload.model_dump())
    db.add(task)
    db.flush()
    record_event(db, access, 'task.created', 'task', task.id)
    db.commit()
    return task


@router.post("/cases/{case_id}/tasks/{task_id}/complete", response_model=TaskRead)
def complete_task(org_id: UUID, case_id: UUID, task_id: UUID, db: Session = Depends(get_db),
                  access: OrgAccess = Depends(get_org_access)):
    allow(access, INTAKE_ROLES)
    ensure_case_open(db, org_id, case_id)
    task = db.scalar(select(CaseTask).where(CaseTask.org_id == org_id, CaseTask.case_id == case_id,
                                            CaseTask.id == task_id).with_for_update())
    if task is None:
        raise HTTPException(status_code=404, detail='Task not found')
    if task.status != 'open':
        raise HTTPException(status_code=409, detail='Task already complete')
    task.status = 'complete'
    task.completed_by_sub = access.principal.sub
    task.completed_at = datetime.now(timezone.utc)
    record_event(db, access, 'task.completed', 'task', task.id)
    db.commit()
    return task


@router.post("/cases/{case_id}/documents", response_model=DocumentRead, status_code=201)
async def upload_document(org_id: UUID, case_id: UUID, file: UploadFile = File(...),
                          document_type: str = Form(..., min_length=2, max_length=80),
                          db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    allow(access, INTAKE_ROLES)
    ensure_case_open(db, org_id, case_id)
    mime = (file.content_type or '').lower()
    filename = (file.filename or 'untitled').replace('\\', '/').split('/')[-1]
    if not filename or len(filename) > 180 or any(ord(ch) < 32 for ch in filename):
        raise HTTPException(status_code=422, detail='Invalid filename')
    # No content is persisted until size and type validation succeeds.
    blob = await file.read(MAX_BYTES + 1)
    storage_key, digest = save_blob(blob, mime)
    document = CaseDocument(org_id=org_id, case_id=case_id, filename=filename,
                            document_type=document_type, mime_type=mime, size_bytes=len(blob),
                            sha256=digest, storage_key=storage_key, uploaded_by_sub=access.principal.sub)
    try:
        db.add(document)
        db.flush()
        record_event(db, access, 'document.uploaded', 'document', document.id,
                     {'mime_type': mime, 'size_bytes': len(blob)})
        db.commit()
    except Exception:
        db.rollback()
        delete_failed_blob(storage_key)
        raise
    return document


@router.get("/cases/{case_id}/documents", response_model=list[DocumentRead])
def case_documents(org_id: UUID, case_id: UUID, db: Session = Depends(get_db),
                   access: OrgAccess = Depends(get_org_access)):
    get_case(db, org_id, case_id)
    return db.scalars(select(CaseDocument).where(CaseDocument.org_id == org_id,
                      CaseDocument.case_id == case_id).order_by(CaseDocument.created_at)).all()


@router.get("/cases/{case_id}/documents/{document_id}/download")
def download_document(org_id: UUID, case_id: UUID, document_id: UUID,
                      db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    # Note: browser downloads use a Blob and Authorization header; never put JWTs in URLs.
    doc = existing_document(db, org_id, case_id, document_id)
    data = load_blob(doc.storage_key)
    if hashlib.sha256(data).hexdigest() != doc.sha256:
        raise HTTPException(status_code=500, detail='Document integrity check failed')
    # No untrusted filename in Content-Disposition; callers can use metadata for local name.
    return Response(content=data, media_type='application/octet-stream', headers={
        'Content-Disposition': 'attachment; filename="immigrationos-document"',
        'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'
    })


@router.get("/cases/{case_id}/facts", response_model=list[FactRead])
def case_facts(org_id: UUID, case_id: UUID, db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    get_case(db, org_id, case_id)
    return db.scalars(select(CaseFact).where(CaseFact.org_id == org_id, CaseFact.case_id == case_id)
                      .order_by(CaseFact.created_at, CaseFact.id)).all()


def make_fingerprint(case_id: UUID, left: UUID, right: UUID) -> str:
    return hashlib.sha256(f'{case_id}:{min(str(left),str(right))}:{max(str(left),str(right))}'.encode()).hexdigest()


def insert_fact_with_conflicts(db: Session, access: OrgAccess, case_id: UUID, payload: FactCreate) -> CaseFact:
    org_id = access.org_id
    fact = CaseFact(org_id=org_id, case_id=case_id, created_by_sub=access.principal.sub,
                    **payload.model_dump())
    db.add(fact)
    db.flush()
    # Deterministic, auditable discrepancy detection. This is NOT AI or legal analysis.
    peers = db.scalars(select(CaseFact).where(
        CaseFact.org_id == org_id, CaseFact.case_id == case_id,
        CaseFact.field_path == fact.field_path, CaseFact.id != fact.id,
        CaseFact.review_status != 'rejected')).all()
    for peer in peers:
        if peer.value.strip().casefold() == fact.value.strip().casefold():
            continue
        fp = make_fingerprint(case_id, peer.id, fact.id)
        db.add(CaseIssue(org_id=org_id, case_id=case_id, fingerprint=fp,
                         issue_type='conflicting_evidence', field_path=fact.field_path,
                         description=f'Conflicting values recorded for {fact.field_path}. Review the source records.',
                         severity='review', status='open'))
    record_event(db, access, 'fact.added', 'fact', fact.id, {'field_path': fact.field_path})
    return fact


@router.post("/cases/{case_id}/facts", response_model=FactRead, status_code=201)
def add_fact(org_id: UUID, case_id: UUID, payload: FactCreate, db: Session = Depends(get_db),
             access: OrgAccess = Depends(get_org_access)):
    allow(access, INTAKE_ROLES)
    ensure_case_open(db, org_id, case_id)
    if payload.document_id is not None:
        existing_document(db, org_id, case_id, payload.document_id)
    fact = insert_fact_with_conflicts(db, access, case_id, payload)
    db.commit()
    return fact


@router.post("/cases/{case_id}/facts/{fact_id}/review", response_model=FactRead)
def review_fact(org_id: UUID, case_id: UUID, fact_id: UUID, payload: FactReview,
                db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    allow(access, REVIEW_ROLES)
    ensure_case_open(db, org_id, case_id)
    fact = db.scalar(select(CaseFact).where(CaseFact.org_id == org_id, CaseFact.case_id == case_id,
                                            CaseFact.id == fact_id).with_for_update())
    if fact is None:
        raise HTTPException(status_code=404, detail='Fact not found')
    if payload.status == FactReviewStatus.pending:
        raise HTTPException(status_code=422, detail='Cannot revert review to pending; add a new fact version')
    if fact.review_status != 'pending':
        raise HTTPException(status_code=409, detail='Fact has already been reviewed')
    fact.review_status = payload.status.value
    fact.reviewed_by_sub = access.principal.sub
    fact.reviewed_at = datetime.now(timezone.utc)
    record_event(db, access, 'fact.reviewed', 'fact', fact.id, {'decision': payload.status.value})
    db.commit()
    return fact


@router.get("/cases/{case_id}/issues", response_model=list[IssueRead])
def case_issues(org_id: UUID, case_id: UUID, db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    get_case(db, org_id, case_id)
    return db.scalars(select(CaseIssue).where(CaseIssue.org_id == org_id, CaseIssue.case_id == case_id)
                      .order_by(CaseIssue.created_at.desc())).all()


@router.post("/cases/{case_id}/issues/{issue_id}/resolve", response_model=IssueRead)
def resolve_issue(org_id: UUID, case_id: UUID, issue_id: UUID, payload: IssueResolution,
                  db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    allow(access, REVIEW_ROLES)
    ensure_case_open(db, org_id, case_id)
    issue = db.scalar(select(CaseIssue).where(CaseIssue.org_id == org_id,
                       CaseIssue.case_id == case_id, CaseIssue.id == issue_id).with_for_update())
    if issue is None:
        raise HTTPException(status_code=404, detail='Issue not found')
    if issue.status != 'open':
        raise HTTPException(status_code=409, detail='Issue already closed')
    issue.status = payload.status
    issue.resolution = payload.resolution
    issue.resolved_by_sub = access.principal.sub
    issue.resolved_at = datetime.now(timezone.utc)
    record_event(db, access, 'issue.resolved', 'issue', issue.id, {'decision': payload.status})
    db.commit()
    return issue


@router.get("/cases/{case_id}/readiness", response_model=CaseReadiness)
def readiness(org_id: UUID, case_id: UUID, db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    case = get_case(db, org_id, case_id)
    facts = db.scalars(select(CaseFact).where(CaseFact.org_id == org_id, CaseFact.case_id == case_id)).all()
    verified = sum(f.review_status == 'verified' for f in facts)
    pending = sum(f.review_status == 'pending' for f in facts)
    rejected = sum(f.review_status == 'rejected' for f in facts)
    issues = db.scalar(select(func.count()).select_from(CaseIssue).where(
        CaseIssue.org_id == org_id, CaseIssue.case_id == case_id, CaseIssue.status == 'open')) or 0
    tasks = db.scalar(select(func.count()).select_from(CaseTask).where(
        CaseTask.org_id == org_id, CaseTask.case_id == case_id, CaseTask.status == 'open')) or 0
    docs = db.scalar(select(func.count()).select_from(CaseDocument).where(
        CaseDocument.org_id == org_id, CaseDocument.case_id == case_id)) or 0
    quarantined = db.scalar(select(func.count()).select_from(PortalSubmission).where(
        PortalSubmission.org_id == org_id, PortalSubmission.case_id == case_id,
        PortalSubmission.scan_status != 'cleared')) or 0
    reasons = []
    if not docs: reasons.append('No documents uploaded')
    if quarantined: reasons.append(f'{quarantined} client uploads awaiting malware clearance')
    if pending: reasons.append(f'{pending} facts need professional review')
    if issues: reasons.append(f'{issues} open evidence conflicts')
    if tasks: reasons.append(f'{tasks} outstanding operational tasks')
    if not verified: reasons.append('No human-verified facts')
    return CaseReadiness(case_id=case_id, status=case.status, verified_facts=verified,
                         pending_facts=pending, rejected_facts=rejected,
                         open_issues=issues, open_tasks=tasks, documents=docs,
                         review_gate='review_required' if reasons else 'operational_checks_clear',
                         reasons=reasons)


@router.post("/cases/{case_id}/documents/{document_id}/extract", response_model=list[SuggestionRead])
def extract_document(org_id: UUID, case_id: UUID, document_id: UUID,
                     db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    """Local, deterministic extraction of synthetic documents. Does not call an AI model.

    Re-runs return the existing suggestions. An extracted fact requires both acceptance
    as a recorded claim and an independent human verification decision.
    """
    allow(access, INTAKE_ROLES)
    ensure_case_open(db, org_id, case_id)
    document = existing_document(db, org_id, case_id, document_id)
    existing = db.scalars(select(FactSuggestion).where(
        FactSuggestion.org_id == org_id, FactSuggestion.case_id == case_id,
        FactSuggestion.document_id == document_id)).all()
    if existing:
        return existing
    blob = load_blob(document.storage_key)
    if hashlib.sha256(blob).hexdigest() != document.sha256:
        raise HTTPException(status_code=500, detail='Document integrity check failed')
    candidates = propose_facts(blob, document.mime_type)
    for candidate in candidates:
        db.add(FactSuggestion(
            org_id=org_id, case_id=case_id, document_id=document_id,
            field_path=candidate.field_path, value=candidate.value,
            source_page=candidate.source_page, source_excerpt=candidate.source_excerpt,
            extraction_method=candidate.extraction_method, confidence=candidate.confidence,
            status='proposed'))
    record_event(db, access, 'document.extracted', 'document', document_id,
                 {'method': 'label_match_v1', 'suggestions': len(candidates)})
    db.commit()
    return db.scalars(select(FactSuggestion).where(
        FactSuggestion.org_id == org_id, FactSuggestion.case_id == case_id,
        FactSuggestion.document_id == document_id)).all()


@router.get("/cases/{case_id}/suggestions", response_model=list[SuggestionRead])
def case_suggestions(org_id: UUID, case_id: UUID,
                     db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    get_case(db, org_id, case_id)
    return db.scalars(select(FactSuggestion).where(
        FactSuggestion.org_id == org_id, FactSuggestion.case_id == case_id)
        .order_by(FactSuggestion.created_at, FactSuggestion.id)).all()


@router.post("/cases/{case_id}/suggestions/{suggestion_id}/decide", response_model=SuggestionRead)
def decide_suggestion(org_id: UUID, case_id: UUID, suggestion_id: UUID, payload: SuggestionDecision,
                      db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    allow(access, REVIEW_ROLES)
    ensure_case_open(db, org_id, case_id)
    suggestion = db.scalar(select(FactSuggestion).where(
        FactSuggestion.org_id == org_id, FactSuggestion.case_id == case_id,
        FactSuggestion.id == suggestion_id).with_for_update())
    if suggestion is None:
        raise HTTPException(status_code=404, detail='Suggestion not found')
    if suggestion.status != 'proposed':
        raise HTTPException(status_code=409, detail='Suggestion already reviewed')
    if payload.decision == 'accept':
        data = FactCreate(field_path=suggestion.field_path, value=suggestion.value,
                          document_id=suggestion.document_id, source_page=suggestion.source_page,
                          source_excerpt=suggestion.source_excerpt)
        fact = insert_fact_with_conflicts(db, access, case_id, data)
        suggestion.status = 'accepted'
        suggestion.accepted_fact_id = fact.id
    else:
        suggestion.status = 'dismissed'
    suggestion.reviewed_by_sub = access.principal.sub
    suggestion.reviewed_at = datetime.now(timezone.utc)
    record_event(db, access, 'suggestion.decided', 'suggestion', suggestion.id,
                 {'decision': payload.decision})
    db.commit()
    return suggestion


@router.get('/worksheets')
def list_worksheets(org_id: UUID, access: OrgAccess = Depends(get_org_access)):
    from app.forms_engine import WORKSHEETS
    return [{'id': key, 'title': tpl.title, 'version': tpl.version, 'official': False}
            for key,tpl in WORKSHEETS.items()]


@router.get('/cases/{case_id}/worksheets/{worksheet_id}')
def case_worksheet(org_id: UUID, case_id: UUID, worksheet_id: str,
                   db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    from app.forms_engine import build_worksheet
    get_case(db, org_id, case_id)
    facts = db.scalars(select(CaseFact).where(CaseFact.org_id==org_id, CaseFact.case_id==case_id)).all()
    open_issues=db.scalar(select(func.count()).select_from(CaseIssue).where(
        CaseIssue.org_id==org_id, CaseIssue.case_id==case_id, CaseIssue.status=='open')) or 0
    try:
        return build_worksheet(worksheet_id,facts,open_issues)
    except KeyError:
        raise HTTPException(status_code=404,detail='Worksheet not found') from None


@router.post('/cases/{case_id}/documents/{document_id}/analyze-ai', response_model=list[SuggestionRead])
def ai_analyze_document(org_id: UUID, case_id: UUID, document_id: UUID,
                        db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    """External-model experiment. Requires explicit deployment opt-in, synthetic data only."""
    allow(access, REVIEW_ROLES)
    ensure_case_open(db, org_id, case_id)
    from app.ai_extraction import extract_with_model
    document=existing_document(db, org_id, case_id, document_id)
    existing=db.scalars(select(FactSuggestion).where(
        FactSuggestion.org_id==org_id,FactSuggestion.case_id==case_id,
        FactSuggestion.document_id==document_id)).all()
    previous=[item for item in existing if item.extraction_method=='ai_model_v1']
    if previous: return previous
    blob=load_blob(document.storage_key)
    if hashlib.sha256(blob).hexdigest()!=document.sha256:
        raise HTTPException(status_code=500,detail='Document integrity check failed')
    proposed=extract_with_model(blob,document.mime_type)
    keys={(item.field_path,item.value.casefold(),item.source_page) for item in existing}
    new=[]
    for item in proposed:
        key=(item.field_path,item.value.casefold(),item.source_page)
        if key in keys: continue
        suggestion=FactSuggestion(org_id=org_id,case_id=case_id,document_id=document_id,
            field_path=item.field_path,value=item.value,source_page=item.source_page,
            source_excerpt=item.source_excerpt,extraction_method='ai_model_v1',confidence=0.45,
            status='proposed')
        db.add(suggestion)
        new.append(suggestion)
        keys.add(key)
    record_event(db,access,'document.ai_analyzed','document',document_id,
        {'method':'ai_model_v1','new_suggestions':len(new)})
    db.commit()
    return new


@router.post('/demo-seed', status_code=201)
def seed_synthetic_demo(org_id: UUID, db: Session = Depends(get_db),
                        access: OrgAccess = Depends(get_org_access)):
    """Local UX demo seed. Has no real people or legally authoritative requirements."""
    from app.settings import get_settings
    if get_settings().environment != 'development':
        raise HTTPException(status_code=404, detail='Not found')
    allow(access, {Role.owner, Role.admin})
    if db.scalar(select(func.count()).select_from(Case).where(Case.org_id==org_id)):
        raise HTTPException(status_code=409,detail='Demo seed only permitted for an empty practice')
    examples=(
        ('Avery','Example','study_permit','Fictional study permit · September intake','review'),
        ('Jordan','Sample','work_permit','Fictional work permit · Employer change','intake'),
        ('Taylor','Fiction','visitor_visa','Fictional visitor visa · Family visit','draft'),
    )
    result=[]
    for first,last,kind,title,status in examples:
        client=Client(org_id=org_id,first_name=first,last_name=last,
                      email=f'{first.lower()}@example.invalid')
        db.add(client);db.flush()
        case=Case(org_id=org_id,client_id=client.id,application_type=kind,title=title,status=status)
        db.add(case);db.flush()
        db.add(CaseTask(org_id=org_id,case_id=case.id,
            title='Review fictional supporting documents',status='open',created_by_sub=access.principal.sub))
        if kind=='study_permit':
            insert_fact_with_conflicts(db,access,case.id,FactCreate(
                field_path='employment.end_date',value='2024-03-31',source_excerpt='Fictional letter: 2024-03-31'))
            insert_fact_with_conflicts(db,access,case.id,FactCreate(
                field_path='employment.end_date',value='2024-06-30',source_excerpt='Fictional questionnaire: 2024-06-30'))
        result.append({'client_id':str(client.id),'case_id':str(case.id)})
    record_event(db,access,'demo.seeded','organization',org_id,{'sample_cases':len(result)})
    db.commit()
    return {'created':len(result),'records':result,'synthetic_only':True}
