"""Append-only provenance of consultant-applied applicant history corrections."""
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import (CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint,
                        Index, Integer, JSON, String, UniqueConstraint, Uuid)
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base
from app.models import utcnow


class TimelineHistoryCorrection(Base):
    __tablename__ = "timeline_history_corrections"
    __table_args__ = (
        ForeignKeyConstraint(["org_id", "case_id", "request_id"],
            ["timeline_clarifications.org_id", "timeline_clarifications.case_id",
             "timeline_clarifications.id"], name="fk_timeline_correction_request"),
        ForeignKeyConstraint(["org_id", "client_id"],
            ["clients.org_id", "clients.id"], name="fk_timeline_correction_client"),
        UniqueConstraint("org_id", "request_id", name="uq_timeline_correction_once"),
        CheckConstraint("operation IN ('create','update')",
                        name="ck_timeline_correction_operation"),
        Index("ix_timeline_correction_case", "org_id", "case_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True),primary_key=True,default=uuid4)
    org_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True),ForeignKey("organizations.id"),nullable=False)
    case_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True),nullable=False)
    client_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True),nullable=False)
    request_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True),nullable=False)
    decision_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True),nullable=False)
    reply_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True),nullable=False)
    record_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True),nullable=False)
    operation: Mapped[str] = mapped_column(String(12),nullable=False)
    kind: Mapped[str] = mapped_column(String(20),nullable=False)
    prior_version: Mapped[int | None] = mapped_column(Integer)
    new_version: Mapped[int] = mapped_column(Integer,nullable=False)
    prior_details: Mapped[dict | None] = mapped_column(JSON)
    new_details: Mapped[dict] = mapped_column(JSON,nullable=False)
    correction_reason: Mapped[str] = mapped_column(String(600),nullable=False)
    created_by_sub: Mapped[str] = mapped_column(String(255),nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=utcnow,nullable=False)
