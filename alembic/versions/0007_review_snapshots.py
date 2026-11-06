"""Append-only evidence review history with strict staff membership RLS.

Revision ID: 0007_review_snapshots
Revises: 0006_malware_scan
"""
from alembic import op
import sqlalchemy as sa

revision = '0007_review_snapshots'
down_revision = '0006_malware_scan'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('evidence_review_snapshots',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('org_id', sa.Uuid(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('case_id', sa.Uuid(), nullable=False),
        sa.Column('filing_context', sa.String(32), nullable=False),
        sa.Column('template_version', sa.String(100), nullable=False),
        sa.Column('case_sha256', sa.String(64), nullable=False),
        sa.Column('reviewer_sub', sa.String(255), nullable=False),
        sa.Column('review_note', sa.String(1200), nullable=False),
        sa.Column('open_issues_at_review', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['org_id', 'case_id'], ['cases.org_id', 'cases.id'], name='fk_review_snapshot_case'),
        sa.CheckConstraint("filing_context IN ('inside_canada','outside_canada')", name='ck_review_snapshot_context'))
    op.create_index('ix_review_snapshots_case', 'evidence_review_snapshots', ['org_id','case_id','created_at'])
    if op.get_bind().dialect.name != 'postgresql':
        return
    op.execute('ALTER TABLE evidence_review_snapshots ENABLE ROW LEVEL SECURITY')
    op.execute('ALTER TABLE evidence_review_snapshots FORCE ROW LEVEL SECURITY')
    staff = """(evidence_review_snapshots.org_id::text = current_setting('app.tenant_id', true)
        AND EXISTS (SELECT 1 FROM memberships m WHERE m.org_id = evidence_review_snapshots.org_id
        AND m.subject = current_setting('app.principal_sub', true) AND m.is_active))"""
    op.execute(f'CREATE POLICY review_read_staff ON evidence_review_snapshots FOR SELECT USING ({staff})')
    op.execute(f'''CREATE POLICY review_insert_consultant ON evidence_review_snapshots FOR INSERT WITH CHECK (
        {staff} AND reviewer_sub = current_setting('app.principal_sub', true)
        AND EXISTS (SELECT 1 FROM memberships m WHERE m.org_id = evidence_review_snapshots.org_id
        AND m.subject = current_setting('app.principal_sub', true)
        AND m.is_active AND m.role IN ('owner','admin','consultant')))''')
    op.execute('''DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'immigrationos_app') THEN
        GRANT SELECT, INSERT ON evidence_review_snapshots TO immigrationos_app;
        END IF; END $$''')


def downgrade():
    op.drop_index('ix_review_snapshots_case', table_name='evidence_review_snapshots')
    op.drop_table('evidence_review_snapshots')
