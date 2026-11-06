from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException
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


def get_org_access(org_id: UUID, db: Session = Depends(get_db), principal: Principal = Depends(get_principal)) -> OrgAccess:
    set_db_context(db, principal.sub, org_id)
    member = db.scalar(select(Membership).where(
        Membership.org_id == org_id,
        Membership.subject == principal.sub,
        Membership.is_active.is_(True),
    ))
    if member is None:
        # Do not distinguish an unknown firm from an inaccessible one.
        raise HTTPException(status_code=404, detail="Organization not found")
    return OrgAccess(org_id=org_id, principal=principal, role=Role(member.role))


def allow(access: OrgAccess, roles: set[Role]) -> None:
    if access.role not in roles:
        raise HTTPException(status_code=403, detail="Insufficient organization permissions")


READ_ROLES = set(Role)
WRITE_ROLES = {Role.owner, Role.admin, Role.consultant}
AUDIT_ROLES = {Role.owner, Role.admin}
