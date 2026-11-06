"""Client portal domain. Only opaque identity subjects link across the staff/client boundary."""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models import utcnow


class PortalInvitation(Base):
    __tablename__ = 'portal_invitations'
    __table_args__ = (
        UniqueConstraint('org_id', 'id', name='uq_portal_invite_org_id'),
        ForeignKeyConstraint(['org_id', 'case_id'], ['cases.org_id', 'cases.id'], name='fk_portal_invite_case'),
        Index('ix_portal_invites_case', 'org_id', 'case_id'),
        UniqueConstraint('token_hash', name='uq_portal_invite_hash'),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey('organizations.id'), nullable=False)
    case_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    invited_email: Mapped[str] = mapped_column(String(254), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_sub: Mapped[str] = mapped_column(String(255), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    accepted_by_sub: Mapped[str | None] = mapped_column(String(255))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class PortalGrant(Base):
    __tablename__ = 'portal_grants'
    __table_args__ = (
        ForeignKeyConstraint(['org_id', 'case_id'], ['cases.org_id', 'cases.id'], name='fk_portal_grant_case'),
        UniqueConstraint('org_id', 'case_id', 'principal_sub', name='uq_portal_grant_subject_case'),
        Index('ix_portal_grants_subject', 'principal_sub'),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey('organizations.id'), nullable=False)
    case_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    principal_sub: Mapped[str] = mapped_column(String(255), nullable=False)
    granted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DocumentRequest(Base):
    __tablename__ = 'document_requests'
    __table_args__ = (
        ForeignKeyConstraint(['org_id', 'case_id'], ['cases.org_id', 'cases.id'], name='fk_doc_request_case'),
        UniqueConstraint('org_id', 'id', name='uq_doc_request_org_id'),
        UniqueConstraint('org_id', 'case_id', 'id', name='uq_doc_request_org_case_id'),
        CheckConstraint("status IN ('open','received','cancelled')", name='ck_doc_request_status'),
        Index('ix_doc_requests_case', 'org_id', 'case_id'),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey('organizations.id'), nullable=False)
    case_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    instructions: Mapped[str] = mapped_column(String(1200), nullable=False, default='')
    document_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default='open', nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_sub: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class PortalSubmission(Base):
    __tablename__ = 'portal_submissions'
    __table_args__ = (
        ForeignKeyConstraint(['org_id', 'case_id'], ['cases.org_id', 'cases.id'], name='fk_portal_submission_case'),
        ForeignKeyConstraint(['org_id', 'case_id', 'request_id'], ['document_requests.org_id', 'document_requests.case_id', 'document_requests.id'], name='fk_portal_submission_request'),
        ForeignKeyConstraint(['org_id', 'document_id'], ['case_documents.org_id', 'case_documents.id'], name='fk_portal_submission_document'),
        UniqueConstraint('org_id', 'request_id', name='uq_portal_submission_request'),
        UniqueConstraint('org_id', 'document_id', name='uq_portal_submission_document'),
        CheckConstraint("scan_status IN ('quarantined','cleared','rejected')", name='ck_portal_scan_status'),
        Index('ix_portal_submissions_case', 'org_id', 'case_id'),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    org_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey('organizations.id'), nullable=False)
    case_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    request_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    document_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    uploaded_by_sub: Mapped[str] = mapped_column(String(255), nullable=False)
    scan_status: Mapped[str] = mapped_column(String(16), nullable=False, default='quarantined')
    scan_engine: Mapped[str | None] = mapped_column(String(60))
    scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
