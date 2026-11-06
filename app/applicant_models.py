"""Reusable firm-bound applicant identity and family connections, with case draft snapshots."""
from uuid import UUID, uuid4
from datetime import datetime
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, JSON, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from app.db import Base
from app.models import utcnow


class ApplicantProfile(Base):
    __tablename__ = "applicant_profiles"
    __table_args__ = (
        UniqueConstraint("org_id", "client_id", name="uq_applicant_profile_client"),
        ForeignKeyConstraint(["org_id", "client_id"], ["clients.org_id", "clients.id"], name="fk_applicant_profile_client"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    client_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_by_sub: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class FamilyMember(Base):
    __tablename__ = "applicant_family_members"
    __table_args__ = (
        UniqueConstraint("org_id", "client_id", "id", name="uq_applicant_family_client_id"),
        ForeignKeyConstraint(["org_id", "client_id"], ["clients.org_id", "clients.id"], name="fk_applicant_family_client"),
        CheckConstraint("relationship IN ('spouse','common_law_partner','child','parent','sibling','other')", name="ck_applicant_family_relationship"),
        Index("ix_applicant_family_client", "org_id", "client_id"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    client_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    relationship: Mapped[str] = mapped_column(String(32), nullable=False)
    given_name: Mapped[str] = mapped_column(String(100), nullable=False)
    family_name: Mapped[str] = mapped_column(String(100), nullable=False)
    date_of_birth: Mapped[str | None] = mapped_column(String(10))
    citizenship: Mapped[str | None] = mapped_column(String(100))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_by_sub: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class CaseAnswerDraft(Base):
    __tablename__ = "case_answer_drafts"
    __table_args__ = (
        ForeignKeyConstraint(["org_id", "client_id", "case_id"], ["cases.org_id", "cases.client_id", "cases.id"], name="fk_answer_draft_case_client"),
        ForeignKeyConstraint(["org_id", "client_id"], ["clients.org_id", "clients.id"], name="fk_answer_draft_client"),
        CheckConstraint("form_code IN ('IMM1294','IMM5709')", name="ck_answer_draft_form"),
        Index("ix_answer_draft_case", "org_id", "case_id", "created_at"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    case_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    client_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    form_code: Mapped[str] = mapped_column(String(20), nullable=False)
    source_revision: Mapped[str] = mapped_column(String(120), nullable=False)
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False)
    answers: Mapped[dict] = mapped_column(JSON, nullable=False)
    unresolved_fields: Mapped[list] = mapped_column(JSON, nullable=False)
    created_by_sub: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
