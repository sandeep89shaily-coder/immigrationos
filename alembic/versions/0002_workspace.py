"""Evidence graph, document manifest, workflow tasks, with strict tenant RLS.
Revision ID: 0002_workspace
Revises: 0001_initial
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_workspace"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('cases') as batch:
        batch.create_unique_constraint('uq_case_org_id', ['org_id', 'id'])
    op.create_table('case_documents',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('org_id', sa.Uuid(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('case_id', sa.Uuid(), nullable=False),
        sa.Column('filename', sa.String(180), nullable=False),
        sa.Column('document_type', sa.String(80), nullable=False),
        sa.Column('mime_type', sa.String(100), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column('sha256', sa.String(64), nullable=False),
        sa.Column('storage_key', sa.String(128), nullable=False, unique=True),
        sa.Column('uploaded_by_sub', sa.String(255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['org_id','case_id'], ['cases.org_id','cases.id'], name='fk_doc_case_same_tenant'),
        sa.UniqueConstraint('org_id', 'id', name='uq_case_document_org_id'),
    )
    op.create_index('ix_documents_case', 'case_documents', ['org_id','case_id'])
    op.create_table('case_facts',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('org_id', sa.Uuid(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('case_id', sa.Uuid(), nullable=False),
        sa.Column('document_id', sa.Uuid(), nullable=True),
        sa.Column('field_path', sa.String(160), nullable=False),
        sa.Column('value', sa.String(1200), nullable=False),
        sa.Column('source_page', sa.Integer(), nullable=True),
        sa.Column('source_excerpt', sa.String(500), nullable=True),
        sa.Column('review_status', sa.String(24), nullable=False),
        sa.Column('created_by_sub', sa.String(255), nullable=False),
        sa.Column('reviewed_by_sub', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['org_id','case_id'], ['cases.org_id','cases.id'], name='fk_fact_case_same_tenant'),
        sa.ForeignKeyConstraint(['org_id','document_id'], ['case_documents.org_id','case_documents.id'], name='fk_fact_doc_same_tenant'),
        sa.UniqueConstraint('org_id','id',name='uq_case_fact_org_id'),
        sa.CheckConstraint("review_status IN ('pending','verified','rejected')", name='ck_fact_review'),
    )
    op.create_index('ix_facts_case_path','case_facts',['org_id','case_id','field_path'])
    op.create_table('case_issues',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('org_id', sa.Uuid(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('case_id', sa.Uuid(), nullable=False),
        sa.Column('fingerprint',sa.String(64),nullable=False),
        sa.Column('issue_type',sa.String(80),nullable=False),
        sa.Column('field_path',sa.String(160),nullable=False),
        sa.Column('description',sa.String(500),nullable=False),
        sa.Column('severity',sa.String(16),nullable=False),
        sa.Column('status',sa.String(20),nullable=False),
        sa.Column('resolution',sa.String(1200),nullable=True),
        sa.Column('resolved_by_sub',sa.String(255),nullable=True),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('resolved_at',sa.DateTime(timezone=True),nullable=True),
        sa.ForeignKeyConstraint(['org_id','case_id'], ['cases.org_id','cases.id'], name='fk_issue_case_same_tenant'),
        sa.UniqueConstraint('org_id','case_id','fingerprint',name='uq_issue_fingerprint'),
        sa.CheckConstraint("status IN ('open','resolved','dismissed')", name='ck_issue_status'),
    )
    op.create_index('ix_issues_case','case_issues',['org_id','case_id','status'])
    op.create_table('case_tasks',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('org_id', sa.Uuid(), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('case_id', sa.Uuid(), nullable=False),
        sa.Column('title',sa.String(180),nullable=False),
        sa.Column('status',sa.String(20),nullable=False),
        sa.Column('due_at',sa.DateTime(timezone=True),nullable=True),
        sa.Column('assigned_to_sub',sa.String(255),nullable=True),
        sa.Column('created_by_sub',sa.String(255),nullable=False),
        sa.Column('completed_by_sub',sa.String(255),nullable=True),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('completed_at',sa.DateTime(timezone=True),nullable=True),
        sa.ForeignKeyConstraint(['org_id','case_id'], ['cases.org_id','cases.id'], name='fk_task_case_same_tenant'),
        sa.CheckConstraint("status IN ('open','complete')", name='ck_task_status'),
    )
    op.create_index('ix_tasks_case_status','case_tasks',['org_id','case_id','status'])
    if op.get_bind().dialect.name == 'postgresql':
        for name in ('case_documents','case_facts','case_issues','case_tasks'):
            op.execute(f'ALTER TABLE {name} ENABLE ROW LEVEL SECURITY')
            op.execute(f'ALTER TABLE {name} FORCE ROW LEVEL SECURITY')
            op.execute(f'''CREATE POLICY {name}_tenant_policy ON {name} FOR ALL
                USING (org_id::text = current_setting('app.tenant_id', true))
                WITH CHECK (org_id::text = current_setting('app.tenant_id', true))''')
            op.execute(f'''DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='immigrationos_app') THEN
                GRANT SELECT, INSERT, UPDATE ON {name} TO immigrationos_app;
                REVOKE DELETE ON {name} FROM immigrationos_app;
            END IF; END $$''')
        # Evidence documents are immutable once uploaded. Deletions require future policy-based retention work.
        op.execute('REVOKE UPDATE ON case_documents FROM immigrationos_app')


def downgrade():
    for name in ('case_tasks','case_issues','case_facts','case_documents'):
        op.drop_table(name)
    with op.batch_alter_table('cases') as batch:
        batch.drop_constraint('uq_case_org_id', type_='unique')
