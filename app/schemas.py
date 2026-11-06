from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Role(str, Enum):
    owner = "owner"
    admin = "admin"
    consultant = "consultant"
    assistant = "assistant"
    viewer = "viewer"


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    slug: str = Field(min_length=3, max_length=64, pattern=r"^[a-z][a-z0-9-]*$")


class OrganizationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    name: str
    slug: str
    created_at: datetime


class OrganizationMembershipRead(OrganizationRead):
    role: Role


class ClientCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: str | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=40)


class ClientRead(ClientCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    org_id: UUID
    created_at: datetime
    updated_at: datetime


class CaseStatus(str, Enum):
    draft = "draft"
    intake = "intake"
    review = "review"
    on_hold = "on_hold"
    closed = "closed"


class CaseCreate(BaseModel):
    client_id: UUID
    application_type: str = Field(min_length=2, max_length=80)
    title: str = Field(min_length=2, max_length=160)


class CaseRead(CaseCreate):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    org_id: UUID
    status: CaseStatus
    created_at: datetime
    updated_at: datetime


class CaseStatusUpdate(BaseModel):
    status: CaseStatus
    reason: str = Field(min_length=10, max_length=250)


class AuditRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    org_id: UUID
    actor_sub: str
    action: str
    resource_type: str
    resource_id: UUID
    details: dict
    occurred_at: datetime
