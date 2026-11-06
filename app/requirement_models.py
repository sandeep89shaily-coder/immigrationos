"""Case-specific requirements: reviewed applicability and documentary evidence attestations.

These are operational decisions, never immigration eligibility or IRCC approval.
"""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (CheckConstraint, Date, DateTime, ForeignKey, ForeignKeyConstraint,
                        Index, String, UniqueConstraint, Uuid)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models import utcnow


class RequirementDecision(Base):
    __tablename__ = "requirement_decisions"
    __table_args__ = (
        ForeignKeyConstraint(["org_id", "case_id"], ["cases.org_id", "cases.id"],
                             name="fk_requirement_decision_case"),
        UniqueConstraint("org_id", "case_id", "requirement_key", "revision",
                         name="uq_requirement_decision_revision"),
        CheckConstraint("decision IN ('required','not_applicable')",
                        name="ck_requirement_decision"),
        Index("ix_requirement_decisions_case", "org_id", "case_id", "requirement_key"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    case_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    requirement_key: Mapped[str] = mapped_column(String(80), nullable=False)
    revision: Mapped[int] = mapped_column(nullable=False)
    decision: Mapped[str] = mapped_column(String(24), nullable=False)
    reason: Mapped[str] = mapped_column(String(900), nullable=False)
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)
    source_template_version: Mapped[str] = mapped_column(String(100), nullable=False)
    source_observed_on: Mapped[datetime] = mapped_column(Date, nullable=False)
    reviewed_by_sub: Mapped[str] = mapped_column(String(255), nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class RequirementDocumentReview(Base):
    __tablename__ = "requirement_document_reviews"
    __table_args__ = (
        ForeignKeyConstraint(["org_id", "case_id"], ["cases.org_id", "cases.id"],
                             name="fk_requirement_doc_review_case"),
        ForeignKeyConstraint(["org_id", "case_id", "document_id"],
                             ["case_documents.org_id", "case_documents.case_id", "case_documents.id"],
                             name="fk_requirement_doc_review_same_case"),
        UniqueConstraint("org_id", "case_id", "requirement_key", "document_id",
                         name="uq_requirement_doc_once"),
        CheckConstraint("decision IN ('accepted','rejected')",
                        name="ck_requirement_doc_decision"),
        Index("ix_requirement_doc_reviews_case", "org_id", "case_id", "requirement_key"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    case_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    requirement_key: Mapped[str] = mapped_column(String(80), nullable=False)
    document_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    document_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(String(900), nullable=False)
    source_template_version: Mapped[str] = mapped_column(String(100), nullable=False)
    reviewed_by_sub: Mapped[str] = mapped_column(String(255), nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
