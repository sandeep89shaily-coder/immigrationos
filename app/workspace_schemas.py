"""Evidence intake, review and task API contracts."""
from datetime import datetime
from enum import Enum
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

class FactReviewStatus(str, Enum):
    pending = 'pending'
    verified = 'verified'
    rejected = 'rejected'

class FactCreate(BaseModel):
    field_path: str = Field(pattern=r'^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*){1,5}$', max_length=160)
    value: str = Field(min_length=1, max_length=1200)
    document_id: UUID | None = None
    source_page: int | None = Field(default=None, ge=1, le=10000)
    source_excerpt: str | None = Field(default=None, max_length=500)

class FactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    org_id: UUID
    case_id: UUID
    document_id: UUID | None
    field_path: str
    value: str
    source_page: int | None
    source_excerpt: str | None
    review_status: FactReviewStatus
    created_by_sub: str
    reviewed_by_sub: str | None
    created_at: datetime

class FactReview(BaseModel):
    status: FactReviewStatus

class IssueRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    case_id: UUID
    field_path: str
    issue_type: str
    description: str
    severity: str
    status: str
    resolution: str | None
    created_at: datetime

class IssueResolution(BaseModel):
    status: str = Field(pattern=r'^(resolved|dismissed)$')
    resolution: str = Field(min_length=10, max_length=1200)

class TaskCreate(BaseModel):
    title: str = Field(min_length=3, max_length=180)
    due_at: datetime | None = None
    assigned_to_sub: str | None = Field(default=None, max_length=255)

class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    case_id: UUID
    title: str
    status: str
    due_at: datetime | None
    assigned_to_sub: str | None
    created_at: datetime

class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    case_id: UUID
    filename: str
    document_type: str
    mime_type: str
    size_bytes: int
    sha256: str
    created_at: datetime

class DashboardRead(BaseModel):
    clients: int
    cases: int
    in_review: int
    open_tasks: int
    open_issues: int
    documents: int

class CaseReadiness(BaseModel):
    case_id: UUID
    status: str
    verified_facts: int
    pending_facts: int
    rejected_facts: int
    open_issues: int
    open_tasks: int
    documents: int
    review_gate: str
    reasons: list[str]
    disclaimer: str = 'Operational quality checks only; not an immigration eligibility or submission approval.'


class SuggestionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    case_id: UUID
    document_id: UUID
    field_path: str
    value: str
    source_page: int
    source_excerpt: str
    extraction_method: str
    confidence: float
    status: str
    accepted_fact_id: UUID | None
    created_at: datetime

class SuggestionDecision(BaseModel):
    decision: str = Field(pattern=r'^(accept|dismiss)$')
