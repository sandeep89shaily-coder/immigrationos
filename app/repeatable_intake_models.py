"""Append-only, case-bound client proposals for family and applicant history.

Client proposals never mutate the master profile. Staff decision is separately
recorded, and import creates only unverified reusable claims.
"""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint,
                        Index, JSON, String, UniqueConstraint, Uuid)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models import utcnow


class ClientRepeatableProposal(Base):
    __tablename__ = "client_repeatable_proposals"
    __table_args__ = (
        ForeignKeyConstraint(["org_id", "case_id"], ["cases.org_id", "cases.id"],
                             name="fk_repeatable_proposal_case"),
        UniqueConstraint("org_id", "case_id", "id", name="uq_repeatable_proposal_case_id"),
        CheckConstraint("kind IN ('family','address','education','employment','travel','previous_relationship','foreign_residence')",
                        name="ck_repeatable_proposal_kind"),
        Index("ix_repeatable_proposals_case", "org_id", "case_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    case_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    details: Mapped[dict] = mapped_column(JSON, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    template_version: Mapped[str] = mapped_column(String(80), nullable=False)
    notice_version: Mapped[str] = mapped_column(String(80), nullable=False)
    created_by_sub: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ClientRepeatableDecision(Base):
    __tablename__ = "client_repeatable_decisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["org_id", "case_id", "proposal_id"],
            ["client_repeatable_proposals.org_id",
             "client_repeatable_proposals.case_id", "client_repeatable_proposals.id"],
            name="fk_repeatable_decision_proposal"),
        UniqueConstraint("org_id", "proposal_id", name="uq_repeatable_decision_once"),
        CheckConstraint("decision IN ('accept','dismiss')", name="ck_repeatable_decision"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    case_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    proposal_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    decision: Mapped[str] = mapped_column(String(12), nullable=False)
    created_record_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    reviewed_by_sub: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
