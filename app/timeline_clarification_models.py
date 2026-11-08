"""Immutable timeline clarification requests, replies and consultant decisions."""
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import (CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint,
                        Index, String, UniqueConstraint, Uuid)
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base
from app.models import utcnow


class TimelineClarification(Base):
    __tablename__ = "timeline_clarifications"
    __table_args__ = (
        ForeignKeyConstraint(["org_id","case_id"], ["cases.org_id","cases.id"],
                             name="fk_timeline_clarification_case"),
        UniqueConstraint("org_id","case_id","id",name="uq_timeline_clarification_case"),
        CheckConstraint("kind IN ('address','employment','education')",
                        name="ck_timeline_clarification_kind"),
        CheckConstraint("flag_type IN ('uncovered_period_for_review','overlap_for_review','end_date_not_supplied','invalid_date','reversed_period')",
                        name="ck_timeline_clarification_flag"),
        Index("ix_timeline_clarification_case", "org_id","case_id","created_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"),nullable=False)
    case_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True),nullable=False)
    kind: Mapped[str] = mapped_column(String(20),nullable=False)
    flag_type: Mapped[str] = mapped_column(String(50),nullable=False)
    flag_sha256: Mapped[str] = mapped_column(String(64),nullable=False)
    snapshot_sha256: Mapped[str] = mapped_column(String(64),nullable=False)
    window_start: Mapped[str] = mapped_column(String(10),nullable=False)
    window_end: Mapped[str] = mapped_column(String(10),nullable=False)
    question: Mapped[str] = mapped_column(String(600),nullable=False)
    created_by_sub: Mapped[str] = mapped_column(String(255),nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=utcnow,nullable=False)


class TimelineClarificationReply(Base):
    __tablename__ = "timeline_clarification_replies"
    __table_args__ = (
        ForeignKeyConstraint(["org_id","case_id","request_id"],
            ["timeline_clarifications.org_id","timeline_clarifications.case_id","timeline_clarifications.id"],
            name="fk_timeline_clarification_reply_request"),
        UniqueConstraint("org_id","request_id",name="uq_timeline_reply_once"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True),primary_key=True,default=uuid4)
    org_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True),ForeignKey("organizations.id"),nullable=False)
    case_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True),nullable=False)
    request_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True),nullable=False)
    answer: Mapped[str] = mapped_column(String(1600),nullable=False)
    answered_by_sub: Mapped[str] = mapped_column(String(255),nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=utcnow,nullable=False)


class TimelineClarificationDecision(Base):
    __tablename__ = "timeline_clarification_decisions"
    __table_args__ = (
        ForeignKeyConstraint(["org_id","case_id","request_id"],
            ["timeline_clarifications.org_id","timeline_clarifications.case_id","timeline_clarifications.id"],
            name="fk_timeline_clarification_decision_request"),
        UniqueConstraint("org_id","request_id",name="uq_timeline_decision_once"),
        CheckConstraint("decision IN ('reviewed','needs_more_information')",
                        name="ck_timeline_clarification_decision"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True),primary_key=True,default=uuid4)
    org_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True),ForeignKey("organizations.id"),nullable=False)
    case_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True),nullable=False)
    request_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True),nullable=False)
    decision: Mapped[str] = mapped_column(String(30),nullable=False)
    reviewed_by_sub: Mapped[str] = mapped_column(String(255),nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=utcnow,nullable=False)
