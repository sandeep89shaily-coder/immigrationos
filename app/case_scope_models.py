"""Case-specific staff permissions with revocable assistant access.

This model adds an assignment-scoped gate to legacy firm-wide case routes.
An individual grant is historic; its revocation cannot be erased.
"""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, ForeignKeyConstraint, Index, String, Uuid, CheckConstraint, text
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base
from app.models import utcnow


class CaseAccessGrant(Base):
    __tablename__ = "case_access_grants"
    __table_args__ = (
        ForeignKeyConstraint(["org_id", "case_id"], ["cases.org_id", "cases.id"],
                             name="fk_case_access_grant_case_tenant"),
        CheckConstraint("scope IN ('read','intake')", name="ck_case_access_scope"),
        Index("uq_case_access_active_subject", "org_id", "case_id", "subject",
              unique=True, postgresql_where=text("revoked_at IS NULL"),
              sqlite_where=text("revoked_at IS NULL")),
        Index("ix_case_access_subject_active", "org_id", "subject", "revoked_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    case_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    granted_by_sub: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by_sub: Mapped[str | None] = mapped_column(String(255))
