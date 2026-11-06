"""One-use, identity-provider-email-bound RCIC firm staff invitation records.

No email is sent by the application. Invitations are shown once and must be
delivered through a separately approved secure channel.
"""
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import (CheckConstraint, DateTime, ForeignKey, Index, String,
                        UniqueConstraint, Uuid)
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base
from app.models import utcnow


class StaffInvitation(Base):
    __tablename__ = "staff_invitations"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_staff_invitation_token_hash"),
        CheckConstraint("role IN ('admin','consultant','assistant','viewer')",
                        name="ck_staff_invitation_role"),
        CheckConstraint("""NOT (accepted_at IS NOT NULL AND revoked_at IS NOT NULL)
            AND (accepted_at IS NULL OR accepted_by_sub IS NOT NULL)
            AND (revoked_at IS NULL OR revoked_by_sub IS NOT NULL)""",
                        name="ck_staff_invitation_terminal"),
        Index("ix_staff_invitation_org_email", "org_id", "invited_email", "expires_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"),
                                        nullable=False)
    invited_email: Mapped[str] = mapped_column(String(254), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_sub: Mapped[str] = mapped_column(String(255), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow,
                                                nullable=False)
    accepted_by_sub: Mapped[str | None] = mapped_column(String(255))
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_by_sub: Mapped[str | None] = mapped_column(String(255))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
