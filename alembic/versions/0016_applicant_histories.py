"""Reusable histories and frozen case-history context in internal answer drafts.

Revision ID: 0016_applicant_histories
Revises: 0015_applicant_profiles
"""
from alembic import op
import sqlalchemy as sa

revision = "0016_applicant_histories"
down_revision = "0015_applicant_profiles"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "applicant_histories",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_by_sub", sa.String(255), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_id", "client_id"], ["clients.org_id", "clients.id"],
                                name="fk_applicant_history_client"),
        sa.CheckConstraint("kind IN ('address','education','employment','travel')",
                           name="ck_applicant_history_kind"),
    )
    op.create_index("ix_applicant_history_client", "applicant_histories",
                    ["org_id", "client_id", "kind"])
    op.add_column("case_answer_drafts", sa.Column(
        "history_snapshot", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    if op.get_bind().dialect.name != "postgresql":
        return
    table = "applicant_histories"
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    scope = """(org_id::text=current_setting('app.tenant_id',true)
       AND EXISTS (SELECT 1 FROM memberships m WHERE m.org_id=applicant_histories.org_id
          AND m.subject=current_setting('app.principal_sub',true) AND m.is_active))"""
    editors = """EXISTS (SELECT 1 FROM memberships m WHERE m.org_id=applicant_histories.org_id
       AND m.subject=current_setting('app.principal_sub',true)
       AND m.is_active AND m.role IN ('owner','admin','consultant'))"""
    op.execute(f"CREATE POLICY applicant_histories_read ON {table} FOR SELECT USING ({scope})")
    op.execute(f"""CREATE POLICY applicant_histories_insert ON {table} FOR INSERT
       WITH CHECK ({scope} AND {editors}
          AND updated_by_sub=current_setting('app.principal_sub',true))""")
    op.execute(f"""CREATE POLICY applicant_histories_update ON {table} FOR UPDATE
       USING ({scope} AND {editors})
       WITH CHECK ({scope} AND {editors}
          AND updated_by_sub=current_setting('app.principal_sub',true))""")
    op.execute("""DO $grants$ BEGIN
       IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='immigrationos_app') THEN
          GRANT SELECT,INSERT,UPDATE(details,version,updated_by_sub,updated_at)
             ON applicant_histories TO immigrationos_app;
       END IF;
    END $grants$""")


def downgrade():
    op.drop_column("case_answer_drafts", "history_snapshot")
    op.drop_index("ix_applicant_history_client", table_name="applicant_histories")
    op.drop_table("applicant_histories")
