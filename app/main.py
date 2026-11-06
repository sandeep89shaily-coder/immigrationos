from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.access import AUDIT_ROLES, READ_ROLES, WRITE_ROLES, OrgAccess, allow, get_org_access
from app.auth import Principal, get_principal
from app.db import get_db, set_db_context
from app.models import AuditEvent, Case, Client, Membership, Organization
from app.schemas import (
    AuditRead, CaseCreate, CaseRead, CaseStatus, CaseStatusUpdate,
    ClientCreate, ClientRead, OrganizationCreate, OrganizationMembershipRead,
    OrganizationRead, Role,
)
from app.settings import get_settings

settings = get_settings()
app = FastAPI(
    title="ImmigrationOS Workspace API",
    version="0.3.0",
    description="Internal, development-stage multi-tenant case-management API. Not approved for real client data.",
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Authorization", "Content-Type"],
)


def record_event(db: Session, access: OrgAccess, action: str, resource_type: str, resource_id: UUID, details: dict | None = None):
    # Metadata only: never put client names, emails, documents or raw model prompts into the audit log.
    db.add(AuditEvent(
        id=uuid4(), org_id=access.org_id, actor_sub=access.principal.sub,
        action=action, resource_type=resource_type, resource_id=resource_id,
        details=details or {},
    ))


@app.get("/health/live", tags=["health"])
def live():
    return {"status": "ok", "version": "0.3.0"}


@app.post("/api/v1/orgs", response_model=OrganizationRead, status_code=status.HTTP_201_CREATED, tags=["organizations"])
def create_organization(payload: OrganizationCreate, db: Session = Depends(get_db), principal: Principal = Depends(get_principal)):
    org_id = uuid4()
    set_db_context(db, principal.sub, org_id)
    org = Organization(id=org_id, slug=payload.slug, name=payload.name, created_by_sub=principal.sub)
    try:
        db.add(org)
        db.flush()
        db.add(Membership(org_id=org_id, subject=principal.sub, role=Role.owner.value, is_active=True))
        # Audit RLS requires an active membership to exist before its INSERT.
        db.flush()
        record_event(db, OrgAccess(org_id, principal, Role.owner), "organization.created", "organization", org_id)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Organization slug already in use") from None
    return org


@app.get("/api/v1/me/orgs", response_model=list[OrganizationMembershipRead], tags=["organizations"])
def my_organizations(db: Session = Depends(get_db), principal: Principal = Depends(get_principal)):
    set_db_context(db, principal.sub)
    rows = db.execute(
        select(Organization, Membership.role)
        .join(Membership, Membership.org_id == Organization.id)
        .where(Membership.subject == principal.sub, Membership.is_active.is_(True))
        .order_by(Organization.name)
    ).all()
    return [OrganizationMembershipRead(id=org.id, name=org.name, slug=org.slug,
                                       created_at=org.created_at, role=Role(role))
            for org, role in rows]


@app.post("/api/v1/orgs/{org_id}/clients", response_model=ClientRead, status_code=201, tags=["clients"])
def create_client(org_id: UUID, payload: ClientCreate, db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    allow(access, WRITE_ROLES)
    client = Client(org_id=org_id, **payload.model_dump())
    db.add(client)
    db.flush()
    record_event(db, access, "client.created", "client", client.id)
    db.commit()
    return client


@app.get("/api/v1/orgs/{org_id}/clients", response_model=list[ClientRead], tags=["clients"])
def list_clients(org_id: UUID, limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0, le=10000),
                 db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    allow(access, READ_ROLES)
    return db.scalars(select(Client).where(Client.org_id == org_id)
                      .order_by(Client.created_at, Client.id).offset(offset).limit(limit)).all()


@app.get("/api/v1/orgs/{org_id}/clients/{client_id}", response_model=ClientRead, tags=["clients"])
def get_client(org_id: UUID, client_id: UUID, db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    client = db.scalar(select(Client).where(Client.org_id == org_id, Client.id == client_id))
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@app.post("/api/v1/orgs/{org_id}/cases", response_model=CaseRead, status_code=201, tags=["cases"])
def create_case(org_id: UUID, payload: CaseCreate, db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    allow(access, WRITE_ROLES)
    client = db.scalar(select(Client.id).where(Client.org_id == org_id, Client.id == payload.client_id))
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found in this organization")
    case = Case(org_id=org_id, **payload.model_dump())
    db.add(case)
    db.flush()
    record_event(db, access, "case.created", "case", case.id, {"status": "draft"})
    db.commit()
    return case


@app.get("/api/v1/orgs/{org_id}/cases", response_model=list[CaseRead], tags=["cases"])
def list_cases(org_id: UUID, limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0, le=10000),
               db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    return db.scalars(select(Case).where(Case.org_id == org_id)
                      .order_by(Case.created_at, Case.id).offset(offset).limit(limit)).all()


ALLOWED_TRANSITIONS: dict[CaseStatus, set[CaseStatus]] = {
    CaseStatus.draft: {CaseStatus.intake, CaseStatus.closed},
    CaseStatus.intake: {CaseStatus.review, CaseStatus.on_hold, CaseStatus.closed},
    CaseStatus.review: {CaseStatus.intake, CaseStatus.on_hold, CaseStatus.closed},
    CaseStatus.on_hold: {CaseStatus.intake, CaseStatus.review, CaseStatus.closed},
    CaseStatus.closed: set(),
}


@app.patch("/api/v1/orgs/{org_id}/cases/{case_id}/status", response_model=CaseRead, tags=["cases"])
def update_case_status(org_id: UUID, case_id: UUID, payload: CaseStatusUpdate,
                       db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    allow(access, WRITE_ROLES)
    case = db.scalar(select(Case).where(Case.org_id == org_id, Case.id == case_id).with_for_update())
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found")
    current = CaseStatus(case.status)
    if payload.status not in ALLOWED_TRANSITIONS[current]:
        raise HTTPException(status_code=409, detail="Invalid case status transition")
    previous = case.status
    case.status = payload.status.value
    # Reason is validated but deliberately not logged: it may contain sensitive narrative.
    record_event(db, access, "case.status_changed", "case", case.id,
                 {"from_status": previous, "to_status": payload.status.value})
    db.commit()
    return case


@app.get("/api/v1/orgs/{org_id}/audit", response_model=list[AuditRead], tags=["audit"])
def audit_events(org_id: UUID, limit: int = Query(50, ge=1, le=100), db: Session = Depends(get_db),
                 access: OrgAccess = Depends(get_org_access)):
    allow(access, AUDIT_ROLES)
    return db.scalars(select(AuditEvent).where(AuditEvent.org_id == org_id)
                      .order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc()).limit(limit)).all()

# Workspace API and the bundled dependency-free consultant UI.
# Import after record_event is defined; workspace calls that shared audit helper.
from pathlib import Path
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from app.workspace import router as workspace_router
from app.portal import router as portal_router, staff_router as portal_staff_router
from app.ircc_registry import router as ircc_registry_router
from app.evidence_matrix import router as evidence_router

app.include_router(workspace_router)
app.include_router(portal_router)
app.include_router(portal_staff_router)
app.include_router(ircc_registry_router)
app.include_router(evidence_router)
STATIC_DIR = Path(__file__).resolve().parent / 'static'
app.mount('/app/static', StaticFiles(directory=STATIC_DIR), name='workspace-static')

@app.get('/app', include_in_schema=False)
def consultant_workspace():
    return FileResponse(STATIC_DIR / 'index.html', headers={
        'X-Content-Type-Options': 'nosniff',
        'Cache-Control': 'no-store',
        'Content-Security-Policy': "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self' http://localhost:8080 http://127.0.0.1:8080; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; form-action 'self'",
    })

@app.get('/app/config', include_in_schema=False)
def workspace_public_config():
    # Issuer and client ID are public OIDC metadata, never credentials.
    return {'issuer': get_settings().auth_issuer,
            'client_id': 'immigrationos-web', 'environment': get_settings().environment,
            'ai_enabled': get_settings().experimental_ai_enabled}


@app.get('/client', include_in_schema=False)
def client_portal_page():
    return FileResponse(STATIC_DIR / 'client.html', headers={
        'X-Content-Type-Options': 'nosniff',
        'Cache-Control': 'no-store',
        'Content-Security-Policy': "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self' http://localhost:8080 http://127.0.0.1:8080; base-uri 'none'; object-src 'none'; frame-ancestors 'none'; form-action 'self'",
    })
