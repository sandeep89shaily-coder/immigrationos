"""Core application package: one filing route, form requirements and reviewed copies.

No form in this model is represented as officially autofilled or IRCC validated.
"""
from datetime import datetime, date
from uuid import UUID, uuid4

from sqlalchemy import (Boolean, CheckConstraint, Date, DateTime, ForeignKey,
                        ForeignKeyConstraint, Index, String, UniqueConstraint, Uuid)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models import utcnow


class CaseApplicationPackage(Base):
    __tablename__ = "case_application_packages"
    __table_args__ = (
        UniqueConstraint("org_id", "case_id", name="uq_application_package_case"),
        UniqueConstraint("org_id", "case_id", "id", name="uq_application_package_case_id"),
        ForeignKeyConstraint(["org_id", "case_id"], ["cases.org_id", "cases.id"],
                             name="fk_application_package_case"),
        CheckConstraint("filing_context IN ('inside_canada','outside_canada')",
                        name="ck_application_package_context"),
        CheckConstraint("application_type = 'study_permit'",
                        name="ck_application_package_type_v1"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"),
                                        nullable=False)
    case_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    application_type: Mapped[str] = mapped_column(String(80), nullable=False)
    filing_context: Mapped[str] = mapped_column(String(32), nullable=False)
    include_representative_form: Mapped[bool] = mapped_column(Boolean, nullable=False)
    profile_version: Mapped[str] = mapped_column(String(80), nullable=False)
    created_by_sub: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 default=utcnow, nullable=False)


class PackageFormCopy(Base):
    """Append one record for every manually supplied candidate form PDF."""
    __tablename__ = "package_form_copies"
    __table_args__ = (
        ForeignKeyConstraint(["org_id", "case_id", "package_id"],
                             ["case_application_packages.org_id",
                              "case_application_packages.case_id",
                              "case_application_packages.id"],
                             name="fk_package_form_package_case"),
        ForeignKeyConstraint(["org_id", "case_id", "document_id"],
                             ["case_documents.org_id", "case_documents.case_id",
                              "case_documents.id"], name="fk_package_form_doc_same_case"),
        UniqueConstraint("org_id", "case_id", "document_id",
                         name="uq_package_form_document_once"),
        CheckConstraint("scan_status IN ('cleared','quarantined','rejected')",
                        name="ck_package_form_scan"),
        CheckConstraint("review_status IN ('pending','accepted','rejected')",
                        name="ck_package_form_review"),
        Index("ix_package_form_copies_latest", "org_id", "case_id", "form_code", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"),
                                        nullable=False)
    case_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    package_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    document_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    form_code: Mapped[str] = mapped_column(String(20), nullable=False)
    source_revision: Mapped[str] = mapped_column(String(120), nullable=False)
    source_observed_on: Mapped[date] = mapped_column(Date, nullable=False)
    linked_document_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    scan_status: Mapped[str] = mapped_column(String(16), nullable=False)
    review_status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    review_note: Mapped[str | None] = mapped_column(String(900))
    reviewed_by_sub: Mapped[str | None] = mapped_column(String(255))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_sub: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),
                                                 default=utcnow, nullable=False)
