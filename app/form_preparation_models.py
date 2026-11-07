"""Immutable case-bound form preparation snapshots (never official IRCC PDF output)."""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (Boolean, CheckConstraint, DateTime, ForeignKey,
                        ForeignKeyConstraint, Index, JSON, String, Uuid)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models import utcnow


class FormPreparationPacket(Base):
    __tablename__ = "form_preparation_packets"
    __table_args__ = (
        ForeignKeyConstraint(["org_id", "case_id"], ["cases.org_id", "cases.id"],
                             name="fk_form_preparation_case"),
        ForeignKeyConstraint(["org_id", "case_id", "package_id"],
                             ["case_application_packages.org_id",
                              "case_application_packages.case_id",
                              "case_application_packages.id"],
                             name="fk_form_preparation_package"),
        CheckConstraint("form_code IN ('IMM1294','IMM5709')",
                        name="ck_form_preparation_code"),
        Index("ix_form_preparation_case", "org_id", "case_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True),
                                        ForeignKey("organizations.id"), nullable=False)
    case_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    package_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    form_code: Mapped[str] = mapped_column(String(20), nullable=False)
    source_revision: Mapped[str] = mapped_column(String(120), nullable=False)
    mapping_version: Mapped[str] = mapped_column(String(100), nullable=False)
    snapshot_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    field_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    blocker_snapshot: Mapped[list] = mapped_column(JSON, nullable=False)
    verified_subset_complete: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_by_sub: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
