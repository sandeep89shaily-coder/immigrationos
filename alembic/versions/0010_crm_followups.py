"""Tenant-scoped, manually actioned CRM follow-ups (no automated delivery).

Revision ID: 0010_crm_followups
Revises: 0009_crm_intake
"""
from alembic import op
import sqlalchemy as sa

revision = "0010_crm_followups"
down_revision = "0009_crm_intake"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "crm_followups",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("prospect_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("priority", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("assigned_to_sub", sa.String(255), nullable=False),
        sa.Column("created_by_sub", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_by_sub", sa.String(255)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("cancelled_by_sub", sa.String(255)),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["org_id","prospect_id"], ["crm_prospects.org_id","crm_prospects.id"],
                                name="fk_crm_followup_prospect"),
        sa.CheckConstraint("status IN ('open','completed','cancelled')", name="ck_crm_followup_status"),
        sa.CheckConstraint("priority IN ('normal','urgent')", name="ck_crm_followup_priority"),
        sa.CheckConstraint("""(status = 'open' AND completed_by_sub IS NULL AND completed_at IS NULL
                                               AND cancelled_by_sub IS NULL AND cancelled_at IS NULL)
                 OR (status = 'completed' AND completed_by_sub IS NOT NULL AND completed_at IS NOT NULL
                                               AND cancelled_by_sub IS NULL AND cancelled_at IS NULL)
                 OR (status = 'cancelled' AND cancelled_by_sub IS NOT NULL AND cancelled_at IS NOT NULL
                                               AND completed_by_sub IS NULL AND completed_at IS NULL)""",
                           name="ck_crm_followup_terminal_metadata"),
    )
    op.create_index("ix_crm_followups_due", "crm_followups", ["org_id", "status", "due_at"])
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute("ALTER TABLE crm_followups ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE crm_followups FORCE ROW LEVEL SECURITY")
    base = """(crm_followups.org_id::text = current_setting('app.tenant_id', true)
        AND EXISTS (SELECT 1 FROM memberships m WHERE m.org_id = crm_followups.org_id
        AND m.subject = current_setting('app.principal_sub', true) AND m.is_active))"""
    staff = """(crm_followups.org_id::text = current_setting('app.tenant_id', true)
        AND EXISTS (SELECT 1 FROM memberships m WHERE m.org_id = crm_followups.org_id
        AND m.subject = current_setting('app.principal_sub', true)
        AND m.is_active AND m.role IN ('owner','admin','consultant','assistant')))"""
    op.execute(f"CREATE POLICY crm_followups_read ON crm_followups FOR SELECT USING ({base})")
    op.execute(f"""CREATE POLICY crm_followups_insert ON crm_followups FOR INSERT WITH CHECK (
        {staff} AND assigned_to_sub = current_setting('app.principal_sub', true)
        AND created_by_sub = current_setting('app.principal_sub', true)
        AND status = 'open')""")
    op.execute(f"""CREATE POLICY crm_followups_finish ON crm_followups FOR UPDATE
        USING ({staff} AND status = 'open')
        WITH CHECK ({staff} AND (
        (status = 'completed' AND completed_by_sub = current_setting('app.principal_sub', true))
        OR (status = 'cancelled' AND cancelled_by_sub = current_setting('app.principal_sub', true))
        ))""")
    op.execute("""DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles
        WHERE rolname = 'immigrationos_app') THEN
        GRANT SELECT, INSERT ON crm_followups TO immigrationos_app;
        GRANT UPDATE (status, completed_by_sub, completed_at, cancelled_by_sub, cancelled_at)
            ON crm_followups TO immigrationos_app;
        END IF; END $$""")


def downgrade():
    op.drop_index("ix_crm_followups_due", table_name="crm_followups")
    op.drop_table("crm_followups")
