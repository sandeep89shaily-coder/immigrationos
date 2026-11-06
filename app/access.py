from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import Principal, get_principal
from app.db import get_db, set_db_context
from app.models import Membership
from app.schemas import Role


@dataclass(frozen=True)
class OrgAccess:
    org_id: UUID
    principal: Principal
    role: Role


def get_org_access(org_id: UUID, request: Request, db: Session = Depends(get_db), principal: Principal = Depends(get_principal)) -> OrgAccess:
    set_db_context(db, principal.sub, org_id)
    member = db.scalar(select(Membership).where(
        Membership.org_id == org_id,
        Membership.subject == principal.sub,
        Membership.is_active.is_(True),
    ))
    if member is None:
        # Do not distinguish an unknown firm from an inaccessible one.
        raise HTTPException(status_code=404, detail="Organization not found")
    access = OrgAccess(org_id=org_id, principal=principal, role=Role(member.role))
    case_id = request.path_params.get('case_id')
    if case_id is not None:
        # Covers all nested staff case routes, not just the original /cases API.
        from app.case_scope import require_case_permission
        try:
            resolved_id = UUID(str(case_id))
        except ValueError:
            raise HTTPException(status_code=404, detail='Case not available') from None
        require_case_permission(db, access, resolved_id, request.method)
    client_id = request.path_params.get('client_id')
    if client_id is not None:
        from app.case_scope import require_client_permission
        try:
            resolved_client = UUID(str(client_id))
        except ValueError:
            raise HTTPException(status_code=404, detail='Client not available') from None
        require_client_permission(db, access, resolved_client, request.url.path)
    return access


def allow(access: OrgAccess, roles: set[Role]) -> None:
    if access.role not in roles:
        raise HTTPException(status_code=403, detail="Insufficient organization permissions")


READ_ROLES = set(Role)
WRITE_ROLES = {Role.owner, Role.admin, Role.consultant}
AUDIT_ROLES = {Role.owner, Role.admin}
