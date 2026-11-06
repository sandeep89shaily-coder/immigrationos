"""Client portal invitation, grants, requests and quarantined uploads.

Revision ID: 0005_client_portal
Revises: 0004_member_guard
"""
from alembic import op
import sqlalchemy as sa

revision = '0005_client_portal'
down_revision = '0004_member_guard'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('portal_invitations',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('org_id', sa.Uuid(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('case_id', sa.Uuid(), nullable=False),
        sa.Column('invited_email', sa.String(254), nullable=False),
        sa.Column('token_hash', sa.String(64), nullable=False),
        sa.Column('created_by_sub', sa.String(255), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('accepted_at', sa.DateTime(timezone=True)),
        sa.Column('accepted_by_sub', sa.String(255)),
        sa.Column('revoked_at', sa.DateTime(timezone=True)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['org_id', 'case_id'], ['cases.org_id', 'cases.id'], name='fk_portal_invite_case'),
        sa.UniqueConstraint('org_id', 'id', name='uq_portal_invite_org_id'),
        sa.UniqueConstraint('token_hash', name='uq_portal_invite_hash'))
    op.create_index('ix_portal_invites_case', 'portal_invitations', ['org_id', 'case_id'])
    op.create_table('portal_grants',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('org_id', sa.Uuid(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('case_id', sa.Uuid(), nullable=False),
        sa.Column('principal_sub', sa.String(255), nullable=False),
        sa.Column('granted_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(['org_id','case_id'], ['cases.org_id','cases.id'], name='fk_portal_grant_case'),
        sa.UniqueConstraint('org_id', 'case_id', 'principal_sub', name='uq_portal_grant_subject_case'))
    op.create_index('ix_portal_grants_subject', 'portal_grants', ['principal_sub'])
    op.create_table('document_requests',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('org_id', sa.Uuid(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('case_id', sa.Uuid(), nullable=False),
        sa.Column('title', sa.String(180), nullable=False),
        sa.Column('instructions', sa.String(1200), nullable=False),
        sa.Column('document_type', sa.String(80), nullable=False),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('due_at', sa.DateTime(timezone=True)),
        sa.Column('created_by_sub', sa.String(255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['org_id','case_id'], ['cases.org_id','cases.id'], name='fk_doc_request_case'),
        sa.UniqueConstraint('org_id','id',name='uq_doc_request_org_id'),
        sa.UniqueConstraint('org_id','case_id','id',name='uq_doc_request_org_case_id'),
        sa.CheckConstraint("status IN ('open','received','cancelled')", name='ck_doc_request_status'))
    op.create_index('ix_doc_requests_case', 'document_requests', ['org_id','case_id'])
    op.create_table('portal_submissions',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('org_id', sa.Uuid(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('case_id', sa.Uuid(), nullable=False),
        sa.Column('request_id', sa.Uuid(), nullable=False),
        sa.Column('document_id', sa.Uuid(), nullable=False),
        sa.Column('uploaded_by_sub', sa.String(255), nullable=False),
        sa.Column('scan_status', sa.String(16), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['org_id','case_id'], ['cases.org_id','cases.id'], name='fk_portal_submission_case'),
        sa.ForeignKeyConstraint(['org_id','case_id','request_id'], ['document_requests.org_id','document_requests.case_id','document_requests.id'], name='fk_portal_submission_request'),
        sa.ForeignKeyConstraint(['org_id','document_id'], ['case_documents.org_id','case_documents.id'], name='fk_portal_submission_document'),
        sa.UniqueConstraint('org_id','request_id',name='uq_portal_submission_request'),
        sa.UniqueConstraint('org_id','document_id',name='uq_portal_submission_document'),
        sa.CheckConstraint("scan_status IN ('quarantined','cleared','rejected')", name='ck_portal_scan_status'))
    op.create_index('ix_portal_submissions_case', 'portal_submissions', ['org_id','case_id'])
    if op.get_bind().dialect.name != 'postgresql':
        return
    tables = ('portal_invitations','portal_grants','document_requests','portal_submissions')
    for table in tables:
        op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')

    # Membership checks refer only to self-visible membership rows; no tenant-id-only access.
    def staff(table):
        return f'''({table}.org_id::text = current_setting('app.tenant_id', true)
            AND EXISTS (SELECT 1 FROM memberships m WHERE m.org_id = {table}.org_id
                AND m.subject = current_setting('app.principal_sub', true) AND m.is_active))'''
    for table in tables:
        cond = staff(table)
        op.execute(f'CREATE POLICY {table}_staff ON {table} FOR ALL USING ({cond}) WITH CHECK ({cond})')

    op.execute('''CREATE POLICY portal_invite_recipient_select ON portal_invitations FOR SELECT USING (
        invited_email = current_setting('app.verified_email', true)
        AND current_setting('app.verified_email', true) <> '')''')
    op.execute('''CREATE POLICY portal_invite_recipient_update ON portal_invitations FOR UPDATE USING (
        invited_email = current_setting('app.verified_email', true)
        AND current_setting('app.verified_email', true) <> '')
        WITH CHECK (invited_email = current_setting('app.verified_email', true))''')
    op.execute('''CREATE POLICY portal_grants_self_read ON portal_grants FOR SELECT USING (
        principal_sub = current_setting('app.principal_sub', true))''')
    op.execute('''CREATE POLICY portal_grants_claim ON portal_grants FOR INSERT WITH CHECK (
        principal_sub = current_setting('app.principal_sub', true)
        AND EXISTS (SELECT 1 FROM portal_invitations inv WHERE
            inv.org_id = portal_grants.org_id AND inv.case_id = portal_grants.case_id
            AND inv.accepted_by_sub = current_setting('app.principal_sub', true)
            AND inv.accepted_at IS NOT NULL AND inv.revoked_at IS NULL))''')
    op.execute('''CREATE POLICY portal_case_read ON cases FOR SELECT USING (
        EXISTS (SELECT 1 FROM portal_grants g WHERE g.org_id = cases.org_id AND g.case_id = cases.id
            AND g.principal_sub = current_setting('app.principal_sub', true) AND g.revoked_at IS NULL))''')
    op.execute('''CREATE POLICY portal_doc_requests_read ON document_requests FOR SELECT USING (
        EXISTS (SELECT 1 FROM portal_grants g WHERE g.org_id = document_requests.org_id
            AND g.case_id = document_requests.case_id AND g.principal_sub = current_setting('app.principal_sub', true)
            AND g.revoked_at IS NULL))''')
    op.execute('''CREATE POLICY portal_doc_requests_receive ON document_requests FOR UPDATE USING (
        status = 'open' AND EXISTS (SELECT 1 FROM portal_grants g
            WHERE g.org_id = document_requests.org_id AND g.case_id = document_requests.case_id
            AND g.principal_sub = current_setting('app.principal_sub', true) AND g.revoked_at IS NULL))
        WITH CHECK (EXISTS (SELECT 1 FROM portal_grants g
            WHERE g.org_id = document_requests.org_id AND g.case_id = document_requests.case_id
            AND g.principal_sub = current_setting('app.principal_sub', true) AND g.revoked_at IS NULL))''')
    op.execute('''CREATE POLICY portal_document_insert ON case_documents FOR INSERT WITH CHECK (
        uploaded_by_sub = current_setting('app.principal_sub', true)
        AND EXISTS (SELECT 1 FROM portal_grants g WHERE g.org_id = case_documents.org_id
            AND g.case_id = case_documents.case_id AND g.principal_sub = current_setting('app.principal_sub', true)
            AND g.revoked_at IS NULL))''')
    op.execute('''CREATE POLICY portal_document_select_own ON case_documents FOR SELECT USING (
        uploaded_by_sub = current_setting('app.principal_sub', true)
        AND EXISTS (SELECT 1 FROM portal_grants g WHERE g.org_id = case_documents.org_id
            AND g.case_id = case_documents.case_id AND g.principal_sub = current_setting('app.principal_sub', true)
            AND g.revoked_at IS NULL))''')
    op.execute('''CREATE POLICY portal_submission_self_select ON portal_submissions FOR SELECT USING (
        uploaded_by_sub = current_setting('app.principal_sub', true)
        AND EXISTS (SELECT 1 FROM portal_grants g WHERE g.org_id = portal_submissions.org_id
            AND g.case_id = portal_submissions.case_id AND g.principal_sub = current_setting('app.principal_sub', true)
            AND g.revoked_at IS NULL))''')
    op.execute('''CREATE POLICY portal_submission_self_insert ON portal_submissions FOR INSERT WITH CHECK (
        uploaded_by_sub = current_setting('app.principal_sub', true)
        AND EXISTS (SELECT 1 FROM portal_grants g WHERE g.org_id = portal_submissions.org_id
            AND g.case_id = portal_submissions.case_id AND g.principal_sub = current_setting('app.principal_sub', true)
            AND g.revoked_at IS NULL))''')
    op.execute('''CREATE POLICY portal_audit_insert ON audit_events FOR INSERT WITH CHECK (
        actor_sub = current_setting('app.principal_sub', true)
        AND action IN ('portal.invitation_accepted', 'portal.document_received_quarantined')
        AND EXISTS (SELECT 1 FROM portal_grants g WHERE g.org_id = audit_events.org_id
            AND g.principal_sub = current_setting('app.principal_sub', true) AND g.revoked_at IS NULL))''')
    op.execute('''DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'immigrationos_app') THEN
        GRANT SELECT, INSERT, UPDATE ON portal_invitations TO immigrationos_app;
        GRANT SELECT, INSERT, UPDATE ON portal_grants TO immigrationos_app;
        GRANT SELECT, INSERT, UPDATE ON document_requests TO immigrationos_app;
        GRANT SELECT, INSERT ON portal_submissions TO immigrationos_app;
        END IF; END $$''')


def downgrade():
    if op.get_bind().dialect.name == 'postgresql':
        op.execute('DROP POLICY portal_audit_insert ON audit_events')
        op.execute('DROP POLICY portal_document_insert ON case_documents')
        op.execute('DROP POLICY portal_document_select_own ON case_documents')
        op.execute('DROP POLICY portal_case_read ON cases')
    op.drop_table('portal_submissions')
    op.drop_index('ix_doc_requests_case', table_name='document_requests')
    op.drop_table('document_requests')
    op.drop_index('ix_portal_grants_subject', table_name='portal_grants')
    op.drop_table('portal_grants')
    op.drop_index('ix_portal_invites_case', table_name='portal_invitations')
    op.drop_table('portal_invitations')
