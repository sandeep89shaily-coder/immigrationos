"""Append-only client questionnaire submissions and staff review decisions.

A client's answer is never automatically a verified CaseFact. Decisions that
accept a response field create a PENDING fact for separate professional review.
"""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models import utcnow


class StudyIntakeSubmission(Base):
    __tablename__ = "study_intake_submissions"
    __table_args__ = (
        UniqueConstraint("org_id", "case_id", "id", name="uq_study_intake_org_case_id"),
        ForeignKeyConstraint(["org_id", "case_id"], ["cases.org_id", "cases.id"],
                             name="fk_study_intake_same_tenant"),
        Index("ix_study_intake_case_created", "org_id", "case_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    case_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_by_sub: Mapped[str] = mapped_column(String(255), nullable=False)
    template_version: Mapped[str] = mapped_column(String(80), nullable=False)
    notice_version: Mapped[str] = mapped_column(String(80), nullable=False)
    answers: Mapped[dict] = mapped_column(JSON, nullable=False)
    answer_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class StudyIntakeDecision(Base):
    __tablename__ = "study_intake_decisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["org_id", "case_id", "submission_id"],
            ["study_intake_submissions.org_id", "study_intake_submissions.case_id",
             "study_intake_submissions.id"],
            name="fk_study_intake_decision_same_case"),
        ForeignKeyConstraint(["org_id", "case_id"], ["cases.org_id", "cases.id"],
                             name="fk_study_intake_decision_case"),
        UniqueConstraint("org_id", "submission_id", "field_path",
                         name="uq_study_intake_review_once"),
        Index("ix_study_intake_decisions_case", "org_id", "case_id"),
        CheckConstraint("decision IN ('accept','dismiss')", name="ck_study_intake_decision"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    case_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    submission_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    field_path: Mapped[str] = mapped_column(String(160), nullable=False)
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    created_fact_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    reviewed_by_sub: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
