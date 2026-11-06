"""Central authorization for every firm-scoped case route.

Firm membership alone does not authorize another consultant's case. This
gate is invoked by get_org_access using FastAPI's resolved path_params, so
nested workspace/evidence/portal/preflight/intake routes share the same rule.

Case-scoped API authorization is not yet row-level authorization for raw SQL.
Production use still needs independent privacy, security and regulatory review.
"""
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, exists, or_, select
from sqlalchemy.orm import Session

from app.case_scope_models import CaseAccessGrant
from app.engagement_models import (EngagementScreen, MatterAssignment,
                                   ServiceAgreementDraft, ServiceSignedCopy)
from app.models import Case
from app.schemas import Role
from app.settings import get_settings

MANAGERS = {Role.owner, Role.admin}
MUTATIONS = {"POST", "PATCH", "PUT", "DELETE"}


def visible_case_filter(org_id: UUID, sub: str, role: Role):
    """SQL expression usable for cases and case-linked work queues."""
    if role in MANAGERS:
        return Case.org_id == org_id
    if role == Role.consultant:
        return and_(
            Case.org_id == org_id,
            exists(select(MatterAssignment.id).where(
                MatterAssignment.org_id == org_id,
                MatterAssignment.case_id == Case.id,
                MatterAssignment.professional_sub == sub,
            )),
        )
    if role == Role.assistant:
        return and_(
            Case.org_id == org_id,
            exists(select(CaseAccessGrant.id).where(
                CaseAccessGrant.org_id == org_id,
                CaseAccessGrant.case_id == Case.id,
                CaseAccessGrant.subject == sub,
                CaseAccessGrant.revoked_at.is_(None),
            )),
        )
    # Viewers do not get case access merely by firm membership.
    return and_(Case.org_id == org_id, Case.id.is_(None))


def visible_case_ids(org_id: UUID, sub: str, role: Role):
    return select(Case.id).where(visible_case_filter(org_id, sub, role))


def current_signed_engagement(db: Session, case: Case) -> bool:
    """Conservative source-snapshot signal, NOT a regulator authorization."""
    assignment = db.scalar(select(MatterAssignment).where(
        MatterAssignment.org_id == case.org_id, MatterAssignment.case_id == case.id,
        MatterAssignment.client_id == case.client_id,
    ))
    if assignment is None:
        return False
    latest = db.scalar(select(ServiceAgreementDraft).where(
        ServiceAgreementDraft.org_id == case.org_id,
        ServiceAgreementDraft.client_id == case.client_id,
    ).order_by(ServiceAgreementDraft.version.desc()).limit(1))
    if latest is None or latest.id != assignment.draft_id:
        return False
    review = db.scalar(select(EngagementScreen).where(
        EngagementScreen.org_id == case.org_id,
        EngagementScreen.client_id == case.client_id
    ).order_by(EngagementScreen.created_at.desc(), EngagementScreen.id.desc()).limit(1))
    if (review is None or latest.screen_id != review.id
            or not review.client_identity_verified
            or not review.previous_rep_checked
            or review.prior_rep not in ("none", "ended_in_writing")
            or review.conflict_status != "none_identified"):
        return False
    evidence = db.scalar(select(ServiceSignedCopy).where(
        ServiceSignedCopy.org_id == case.org_id,
        ServiceSignedCopy.client_id == case.client_id,
        ServiceSignedCopy.draft_id == latest.id,
    ))
    return bool(evidence and evidence.scan_status == "cleared"
                and evidence.review_status == "accepted")


def require_case_permission(db: Session, access, case_id: UUID, http_method: str):
    """Return 404 for out-of-scope cases, 403 for attempted excess privileges."""
    case = db.scalar(select(Case).where(
        Case.org_id == access.org_id, Case.id == case_id))
    if case is None:
        raise HTTPException(404, "Case not available")
    write = http_method.upper() in MUTATIONS

    if access.role in MANAGERS:
        pass  # Firm owners/admins have audited firm-wide management access.
    elif access.role == Role.consultant:
        assigned = db.scalar(select(MatterAssignment.id).where(
            MatterAssignment.org_id == access.org_id,
            MatterAssignment.case_id == case_id,
            MatterAssignment.professional_sub == access.principal.sub,
        ))
        if assigned is None:
            raise HTTPException(404, "Case not available")
    elif access.role == Role.assistant:
        grant = db.scalar(select(CaseAccessGrant).where(
            CaseAccessGrant.org_id == access.org_id,
            CaseAccessGrant.case_id == case_id,
            CaseAccessGrant.subject == access.principal.sub,
            CaseAccessGrant.revoked_at.is_(None),
        ))
        if grant is None:
            raise HTTPException(404, "Case not available")
        if write and grant.scope != "intake":
            raise HTTPException(403, "Case access is read-only")
    else:
        raise HTTPException(404, "Case not available")

    # Production never permits an older demo route to act on an unengaged or
    # superseded case. Dev/test can still exercise expressly synthetic legacy
    # cases, but all role-based case boundaries apply in every environment.
    if write and get_settings().environment == "production":
        if not current_signed_engagement(db, case):
            raise HTTPException(409, "Matter requires current reviewed service engagement")
    return case
