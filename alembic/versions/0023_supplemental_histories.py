"""Add safe supplemental history categories and versioned staff-owned records.

Revision ID: 0023_supplemental_histories
Revises: 0022_history_corrections
"""
from alembic import op
import sqlalchemy as sa

revision = "0023_supplemental_histories"
down_revision = "0022_history_corrections"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "applicant_supplemental_histories",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_by_sub", sa.String(255), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_id","client_id"], ["clients.org_id","clients.id"],
                                name="fk_supplemental_history_client"),
        sa.CheckConstraint("kind IN ('previous_relationship','foreign_residence')",
                           name="ck_supplemental_history_kind"),
    )
    op.create_index("ix_supplemental_history_client", "applicant_supplemental_histories",
                    ["org_id","client_id","kind"])
    # PostgreSQL cannot add new values to an existing CHECK implicitly.
    op.alter_column("client_repeatable_proposals", "kind",
                    existing_type=sa.String(20), type_=sa.String(30),
                    existing_nullable=False)
    op.drop_constraint("ck_repeatable_proposal_kind", "client_repeatable_proposals", type_="check")
    op.create_check_constraint("ck_repeatable_proposal_kind", "client_repeatable_proposals",
        "kind IN ('family','address','education','employment','travel',"
        "'previous_relationship','foreign_residence')")
    if op.get_bind().dialect.name != "postgresql":
        return
    t = "applicant_supplemental_histories"
    op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY")
    staff = f"""({t}.org_id::text=current_setting('app.tenant_id',true)
        AND EXISTS (SELECT 1 FROM memberships m WHERE m.org_id={t}.org_id
          AND m.subject=current_setting('app.principal_sub',true) AND m.is_active))"""
    writer = f"""({staff} AND {t}.updated_by_sub=current_setting('app.principal_sub',true)
        AND EXISTS (SELECT 1 FROM memberships m WHERE m.org_id={t}.org_id
          AND m.subject=current_setting('app.principal_sub',true)
          AND m.is_active AND m.role IN ('owner','admin','consultant')))"""
    op.execute(f"CREATE POLICY supplemental_history_staff_select ON {t} FOR SELECT USING ({staff})")
    op.execute(f"CREATE POLICY supplemental_history_staff_insert ON {t} FOR INSERT WITH CHECK ({writer})")
    op.execute(f"""DO $role$ BEGIN IF EXISTS (
        SELECT 1 FROM pg_roles WHERE rolname='immigrationos_app') THEN
        GRANT SELECT,INSERT ON applicant_supplemental_histories TO immigrationos_app;
        REVOKE UPDATE,DELETE ON applicant_supplemental_histories FROM immigrationos_app;
    END IF; END $role$""")


def downgrade():
    op.drop_constraint("ck_repeatable_proposal_kind", "client_repeatable_proposals", type_="check")
    op.create_check_constraint("ck_repeatable_proposal_kind", "client_repeatable_proposals",
        "kind IN ('family','address','education','employment','travel')")
    op.drop_index("ix_supplemental_history_client", table_name="applicant_supplemental_histories")
    op.drop_table("applicant_supplemental_histories")
