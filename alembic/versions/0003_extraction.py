"""Reviewable source-grounded extraction proposals.
Revision ID: 0003_extraction
Revises: 0002_workspace
"""
from alembic import op
import sqlalchemy as sa
revision='0003_extraction'
down_revision='0002_workspace'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('fact_suggestions',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('org_id',sa.Uuid(),sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('case_id',sa.Uuid(),nullable=False),
        sa.Column('document_id',sa.Uuid(),nullable=False),
        sa.Column('field_path',sa.String(160),nullable=False),
        sa.Column('value',sa.String(1200),nullable=False),
        sa.Column('source_page',sa.Integer(),nullable=False),
        sa.Column('source_excerpt',sa.String(500),nullable=False),
        sa.Column('extraction_method',sa.String(40),nullable=False),
        sa.Column('confidence',sa.Float(),nullable=False),
        sa.Column('status',sa.String(20),nullable=False),
        sa.Column('accepted_fact_id',sa.Uuid(),nullable=True),
        sa.Column('reviewed_by_sub',sa.String(255),nullable=True),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('reviewed_at',sa.DateTime(timezone=True),nullable=True),
        sa.ForeignKeyConstraint(['org_id','case_id'], ['cases.org_id','cases.id'],name='fk_suggestion_case_same_tenant'),
        sa.ForeignKeyConstraint(['org_id','document_id'], ['case_documents.org_id','case_documents.id'],name='fk_suggestion_doc_same_tenant'),
        sa.CheckConstraint("status IN ('proposed','accepted','dismissed')",name='ck_suggestion_status'),
        sa.UniqueConstraint('org_id','document_id','field_path','value','source_page',name='uq_suggestion_provenance'),
    )
    op.create_index('ix_suggestion_document','fact_suggestions',['org_id','case_id','document_id'])
    if op.get_bind().dialect.name=='postgresql':
        op.execute('ALTER TABLE fact_suggestions ENABLE ROW LEVEL SECURITY')
        op.execute('ALTER TABLE fact_suggestions FORCE ROW LEVEL SECURITY')
        op.execute('''CREATE POLICY fact_suggestions_tenant_policy ON fact_suggestions FOR ALL
            USING (org_id::text = current_setting('app.tenant_id',true))
            WITH CHECK (org_id::text = current_setting('app.tenant_id',true))''')
        op.execute('''DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='immigrationos_app') THEN
            GRANT SELECT,INSERT,UPDATE ON fact_suggestions TO immigrationos_app;
            REVOKE DELETE ON fact_suggestions FROM immigrationos_app;
        END IF; END $$''')

def downgrade():
    op.drop_table('fact_suggestions')
