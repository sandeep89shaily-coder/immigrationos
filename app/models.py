from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    created_by_sub: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (UniqueConstraint("org_id", "subject", name="uq_membership_org_subject"),
                      CheckConstraint("role IN ('owner','admin','consultant','assistant','viewer')", name="ck_membership_role"),
                      Index("ix_memberships_subject", "subject"))
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Client(Base):
    __tablename__ = "clients"
    __table_args__ = (UniqueConstraint("org_id", "id", name="uq_client_org_id"),
                      Index("ix_clients_org_created", "org_id", "created_at"))
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str | None] = mapped_column(String(254))
    phone: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class Case(Base):
    __tablename__ = "cases"
    __table_args__ = (
        UniqueConstraint("org_id", "id", name="uq_case_org_id"),
        ForeignKeyConstraint(["org_id", "client_id"], ["clients.org_id", "clients.id"], name="fk_case_client_same_tenant"),
        Index("ix_cases_org_status", "org_id", "status"),
        CheckConstraint("status IN ('draft','intake','review','on_hold','closed')", name="ck_case_status"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    client_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    application_type: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_org_occurred", "org_id", "occurred_at"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    actor_sub: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

# The case-evidence domain. Each FK includes the organization discriminator, ensuring
# tenant separation is enforced by the database in addition to API authorization.
class CaseDocument(Base):
    __tablename__ = "case_documents"
    __table_args__ = (
        UniqueConstraint("org_id", "id", name="uq_case_document_org_id"),
        ForeignKeyConstraint(["org_id", "case_id"], ["cases.org_id", "cases.id"], name="fk_doc_case_same_tenant"),
        Index("ix_documents_case", "org_id", "case_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    case_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    filename: Mapped[str] = mapped_column(String(180), nullable=False)
    document_type: Mapped[str] = mapped_column(String(80), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    uploaded_by_sub: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class CaseFact(Base):
    __tablename__ = "case_facts"
    __table_args__ = (
        UniqueConstraint("org_id", "id", name="uq_case_fact_org_id"),
        ForeignKeyConstraint(["org_id", "case_id"], ["cases.org_id", "cases.id"], name="fk_fact_case_same_tenant"),
        ForeignKeyConstraint(["org_id", "document_id"], ["case_documents.org_id", "case_documents.id"], name="fk_fact_doc_same_tenant"),
        CheckConstraint("review_status IN ('pending','verified','rejected')", name="ck_fact_review"),
        Index("ix_facts_case_path", "org_id", "case_id", "field_path"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    case_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    document_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    field_path: Mapped[str] = mapped_column(String(160), nullable=False)
    value: Mapped[str] = mapped_column(String(1200), nullable=False)
    source_page: Mapped[int | None] = mapped_column(nullable=True)
    source_excerpt: Mapped[str | None] = mapped_column(String(500), nullable=True)
    review_status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)
    created_by_sub: Mapped[str] = mapped_column(String(255), nullable=False)
    reviewed_by_sub: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CaseIssue(Base):
    __tablename__ = "case_issues"
    __table_args__ = (
        ForeignKeyConstraint(["org_id", "case_id"], ["cases.org_id", "cases.id"], name="fk_issue_case_same_tenant"),
        CheckConstraint("status IN ('open','resolved','dismissed')", name="ck_issue_status"),
        Index("ix_issues_case", "org_id", "case_id", "status"),
        UniqueConstraint("org_id", "case_id", "fingerprint", name="uq_issue_fingerprint"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    case_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    issue_type: Mapped[str] = mapped_column(String(80), nullable=False)
    field_path: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), default="review", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)
    resolution: Mapped[str | None] = mapped_column(String(1200), nullable=True)
    resolved_by_sub: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CaseTask(Base):
    __tablename__ = "case_tasks"
    __table_args__ = (
        ForeignKeyConstraint(["org_id", "case_id"], ["cases.org_id", "cases.id"], name="fk_task_case_same_tenant"),
        CheckConstraint("status IN ('open','complete')", name="ck_task_status"),
        Index("ix_tasks_case_status", "org_id", "case_id", "status"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    case_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    assigned_to_sub: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_by_sub: Mapped[str] = mapped_column(String(255), nullable=False)
    completed_by_sub: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class FactSuggestion(Base):
    """Untrusted extraction result until an authorized human explicitly accepts it."""
    __tablename__ = 'fact_suggestions'
    __table_args__ = (
        ForeignKeyConstraint(['org_id','case_id'], ['cases.org_id','cases.id'], name='fk_suggestion_case_same_tenant'),
        ForeignKeyConstraint(['org_id','document_id'], ['case_documents.org_id','case_documents.id'], name='fk_suggestion_doc_same_tenant'),
        CheckConstraint("status IN ('proposed','accepted','dismissed')", name='ck_suggestion_status'),
        UniqueConstraint('org_id','document_id','field_path','value','source_page',name='uq_suggestion_provenance'),
        Index('ix_suggestion_document', 'org_id','case_id','document_id'),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey('organizations.id'), nullable=False)
    case_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    document_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    field_path: Mapped[str] = mapped_column(String(160), nullable=False)
    value: Mapped[str] = mapped_column(String(1200), nullable=False)
    source_page: Mapped[int] = mapped_column(nullable=False)
    source_excerpt: Mapped[str] = mapped_column(String(500), nullable=False)
    extraction_method: Mapped[str] = mapped_column(String(40), nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(20), default='proposed', nullable=False)
    accepted_fact_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    reviewed_by_sub: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class EvidenceReviewSnapshot(Base):
    """Append-only record of what an authorized *staff* reviewer examined.

    This records an operational review, NOT an RCIC credential verification,
    IRCC approval, submission authority, or final eligibility determination.
    """
    __tablename__ = 'evidence_review_snapshots'
    __table_args__ = (
        ForeignKeyConstraint(['org_id', 'case_id'], ['cases.org_id', 'cases.id'], name='fk_review_snapshot_case'),
        Index('ix_review_snapshots_case', 'org_id', 'case_id', 'created_at'),
        CheckConstraint("filing_context IN ('inside_canada','outside_canada')", name='ck_review_snapshot_context'),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey('organizations.id'), nullable=False)
    case_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    filing_context: Mapped[str] = mapped_column(String(32), nullable=False)
    template_version: Mapped[str] = mapped_column(String(100), nullable=False)
    case_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    reviewer_sub: Mapped[str] = mapped_column(String(255), nullable=False)
    review_note: Mapped[str] = mapped_column(String(1200), nullable=False)
    open_issues_at_review: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
