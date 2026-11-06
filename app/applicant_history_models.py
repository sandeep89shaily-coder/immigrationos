"""Versioned applicant history; one row per period or journey, never auto-verified."""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, JSON, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models import utcnow


class ApplicantHistory(Base):
    __tablename__ = "applicant_histories"
    __table_args__ = (
        ForeignKeyConstraint(["org_id", "client_id"], ["clients.org_id", "clients.id"],
                             name="fk_applicant_history_client"),
        CheckConstraint("kind IN ('address','education','employment','travel')",
                        name="ck_applicant_history_kind"),
        Index("ix_applicant_history_client", "org_id", "client_id", "kind"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    client_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    details: Mapped[dict] = mapped_column(JSON, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_by_sub: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow,
                                                  onupdate=utcnow, nullable=False)
