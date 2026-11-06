"""Development-stage RCIC engagement controls. These are not legal approvals.

Conflict screens and agreement revisions are append-only. An accepted signed
copy is a staff attestation; signatures and CICC credentials are not verified.
"""
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import (JSON, CheckConstraint, DateTime, ForeignKey,
                        ForeignKeyConstraint, Index, String, UniqueConstraint, Uuid)
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base
from app.models import utcnow


class EngagementScreen(Base):
    """Staff-reviewed client and prior-representation/conflict snapshot."""
    __tablename__ = "engagement_screens"
    __table_args__ = (
        UniqueConstraint("org_id", "client_id", "id", name="uq_engagement_screen_client"),
        ForeignKeyConstraint(["org_id", "client_id"], ["clients.org_id", "clients.id"],
                             name="fk_engagement_screen_client"),
        CheckConstraint("prior_rep IN ('none','ended_in_writing','concurrent','unknown')",
                        name="ck_engagement_prior_rep"),
        CheckConstraint("conflict_status IN ('none_identified','potential','prohibited','unresolved')",
                        name="ck_engagement_conflict"),
        Index("ix_engagement_screen_client_date", "org_id", "client_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    client_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    prior_rep: Mapped[str] = mapped_column(String(32), nullable=False)
    conflict_status: Mapped[str] = mapped_column(String(32), nullable=False)
    client_identity_verified: Mapped[bool] = mapped_column(nullable=False)
    previous_rep_checked: Mapped[bool] = mapped_column(nullable=False)
    details: Mapped[str] = mapped_column(String(1200), nullable=False)
    reviewer_sub: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ServiceAgreementDraft(Base):
    """Immutable reviewed draft with 26 Code s24 headings, no auto-signing."""
    __tablename__ = "service_agreement_drafts"
    __table_args__ = (
        UniqueConstraint("org_id", "client_id", "id", name="uq_service_draft_client"),
        UniqueConstraint("org_id", "client_id", "version", name="uq_service_draft_version"),
        ForeignKeyConstraint(["org_id", "client_id"], ["clients.org_id", "clients.id"],
                             name="fk_service_draft_client"),
        ForeignKeyConstraint(["org_id", "client_id", "screen_id"],
                             ["engagement_screens.org_id", "engagement_screens.client_id",
                              "engagement_screens.id"], name="fk_service_draft_screen"),
        Index("ix_service_draft_client_version", "org_id", "client_id", "version"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    client_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    screen_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False)
    clauses: Mapped[dict] = mapped_column(JSON, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_sub: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ServiceSignedCopy(Base):
    """Encrypted untrusted PDF with scanner outcome and attributed human review."""
    __tablename__ = "service_signed_copies"
    __table_args__ = (
        UniqueConstraint("org_id", "draft_id", name="uq_service_signed_draft"),
        ForeignKeyConstraint(["org_id", "client_id"], ["clients.org_id", "clients.id"],
                             name="fk_service_signed_client"),
        ForeignKeyConstraint(["org_id", "client_id", "draft_id"],
                             ["service_agreement_drafts.org_id", "service_agreement_drafts.client_id",
                              "service_agreement_drafts.id"], name="fk_service_signed_draft"),
        CheckConstraint("scan_status IN ('quarantined','cleared','rejected')",
                        name="ck_service_signed_scan"),
        CheckConstraint("review_status IN ('pending','accepted','rejected')",
                        name="ck_service_signed_review"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    client_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    draft_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(nullable=False)
    draft_provided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    client_copy_provided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scan_status: Mapped[str] = mapped_column(String(16), default="quarantined", nullable=False)
    review_status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    review_note: Mapped[str | None] = mapped_column(String(1000))
    reviewed_by_sub: Mapped[str | None] = mapped_column(String(255))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_sub: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class MatterAssignment(Base):
    """An engagement-gated case opening, separate from legacy draft-case API."""
    __tablename__ = "matter_assignments"
    __table_args__ = (
        UniqueConstraint("org_id", "case_id", name="uq_matter_assignment_case"),
        ForeignKeyConstraint(["org_id", "client_id"], ["clients.org_id", "clients.id"],
                             name="fk_matter_assignment_client"),
        ForeignKeyConstraint(["org_id", "client_id", "case_id"],
                             ["cases.org_id", "cases.client_id", "cases.id"],
                             name="fk_matter_assignment_matching_case_client"),
        ForeignKeyConstraint(["org_id", "client_id", "draft_id"],
                             ["service_agreement_drafts.org_id", "service_agreement_drafts.client_id",
                              "service_agreement_drafts.id"], name="fk_matter_assignment_draft"),
        Index("ix_matter_assignment_professional", "org_id", "professional_sub"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    client_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    case_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    draft_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    professional_sub: Mapped[str] = mapped_column(String(255), nullable=False)
    assigned_by_sub: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
