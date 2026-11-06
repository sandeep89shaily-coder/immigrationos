"""Synthetic-data prospect-to-consultation CRM models.

Separation of leads, appointments, terms and signed-copy evidence is deliberate.
An uploaded file or staff note does not establish the legal validity of a
consultation agreement or a CICC licence.
"""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (JSON, CheckConstraint, DateTime, ForeignKey,
                        ForeignKeyConstraint, Index, String, UniqueConstraint, Uuid)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models import utcnow


class Prospect(Base):
    __tablename__ = "crm_prospects"
    __table_args__ = (
        UniqueConstraint("org_id", "id", name="uq_crm_prospect_org_id"),
        ForeignKeyConstraint(["org_id", "converted_client_id"], ["clients.org_id", "clients.id"],
                             name="fk_crm_converted_client_tenant"),
        CheckConstraint("stage IN ('new','contacted','consultation_scheduled','consulted','converted','closed')",
                        name="ck_crm_prospect_stage"),
        Index("ix_crm_prospects_org_stage", "org_id", "stage", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str | None] = mapped_column(String(254))
    phone: Mapped[str | None] = mapped_column(String(40))
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    stage: Mapped[str] = mapped_column(String(32), nullable=False, default="new")
    assigned_to_sub: Mapped[str | None] = mapped_column(String(255))
    outreach_consent: Mapped[bool] = mapped_column(nullable=False, default=False)
    consent_source: Mapped[str | None] = mapped_column(String(200))
    converted_client_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    created_by_sub: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class ProspectActivity(Base):
    """Append-only staff-entered interaction; recording ≠ delivering a message."""
    __tablename__ = "crm_prospect_activities"
    __table_args__ = (
        ForeignKeyConstraint(["org_id", "prospect_id"], ["crm_prospects.org_id", "crm_prospects.id"],
                             name="fk_crm_activity_prospect"),
        CheckConstraint("kind IN ('call','email','meeting','note')", name="ck_crm_activity_kind"),
        Index("ix_crm_activity_prospect", "org_id", "prospect_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    prospect_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(String(1200), nullable=False)
    created_by_sub: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class Consultation(Base):
    __tablename__ = "crm_consultations"
    __table_args__ = (
        UniqueConstraint("org_id", "id", name="uq_crm_consultation_org_id"),
        UniqueConstraint("org_id", "prospect_id", "id", name="uq_crm_consultation_prospect_id"),
        ForeignKeyConstraint(["org_id", "prospect_id"], ["crm_prospects.org_id", "crm_prospects.id"],
                             name="fk_crm_consultation_prospect"),
        CheckConstraint("status IN ('scheduled','completed','cancelled')", name="ck_crm_consultation_status"),
        Index("ix_crm_consultations_org_date", "org_id", "starts_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    prospect_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    professional_sub: Mapped[str] = mapped_column(String(255), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="scheduled")
    created_by_sub: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ConsultationAgreement(Base):
    """Immutable versioned terms. Separate signed copy is required for gate."""
    __tablename__ = "crm_consultation_agreements"
    __table_args__ = (
        UniqueConstraint("org_id", "id", name="uq_crm_agreement_org_id"),
        UniqueConstraint("org_id", "prospect_id", "id", name="uq_crm_agreement_prospect_id"),
        ForeignKeyConstraint(["org_id", "prospect_id"], ["crm_prospects.org_id", "crm_prospects.id"],
                             name="fk_crm_agreement_prospect"),
        ForeignKeyConstraint(["org_id", "prospect_id", "consultation_id"], ["crm_consultations.org_id", "crm_consultations.prospect_id", "crm_consultations.id"],
                             name="fk_crm_agreement_consultation"),
        Index("ix_crm_agreement_consultation", "org_id", "consultation_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    prospect_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    consultation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(nullable=False)
    terms: Mapped[dict] = mapped_column(JSON, nullable=False)
    terms_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_sub: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ConsultationSignedCopy(Base):
    """Encrypted development PDF; cleared scan and manual signoff are separate."""
    __tablename__ = "crm_consultation_signed_copies"
    __table_args__ = (
        UniqueConstraint("org_id", "agreement_id", name="uq_crm_signed_copy_agreement"),
        ForeignKeyConstraint(["org_id", "prospect_id"], ["crm_prospects.org_id", "crm_prospects.id"],
                             name="fk_crm_signed_copy_prospect"),
        ForeignKeyConstraint(["org_id", "prospect_id", "agreement_id"], ["crm_consultation_agreements.org_id",
                                                          "crm_consultation_agreements.prospect_id", "crm_consultation_agreements.id"],
                             name="fk_crm_signed_copy_agreement"),
        CheckConstraint("scan_status IN ('quarantined','cleared','rejected')", name="ck_crm_copy_scan"),
        CheckConstraint("review_status IN ('pending','accepted','rejected')", name="ck_crm_copy_review"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    prospect_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    agreement_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(nullable=False)
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    client_copy_provided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scan_status: Mapped[str] = mapped_column(String(16), nullable=False, default="quarantined")
    review_status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    review_note: Mapped[str | None] = mapped_column(String(800))
    reviewed_by_sub: Mapped[str | None] = mapped_column(String(255))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_sub: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ProspectFollowUp(Base):
    """Firm-internal next action. No external message delivery is implied."""
    __tablename__ = "crm_followups"
    __table_args__ = (
        ForeignKeyConstraint(["org_id", "prospect_id"], ["crm_prospects.org_id", "crm_prospects.id"],
                             name="fk_crm_followup_prospect"),
        CheckConstraint("status IN ('open','completed','cancelled')", name="ck_crm_followup_status"),
        CheckConstraint("priority IN ('normal','urgent')", name="ck_crm_followup_priority"),
        Index("ix_crm_followups_due", "org_id", "status", "due_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    prospect_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default="normal")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="open")
    assigned_to_sub: Mapped[str] = mapped_column(String(255), nullable=False)
    created_by_sub: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    completed_by_sub: Mapped[str | None] = mapped_column(String(255))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_by_sub: Mapped[str | None] = mapped_column(String(255))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
