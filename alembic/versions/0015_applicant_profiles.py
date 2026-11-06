"""Applicant/family master data and immutable internal answer drafts.

Revision ID: 0015_applicant_profiles
Revises: 0014_application_package
"""
from alembic import op
import sqlalchemy as sa

revision = "0015_applicant_profiles"
down_revision = "0014_application_package"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "applicant_profiles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_by_sub", sa.String(255), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("org_id", "client_id", name="uq_applicant_profile_client"),
        sa.ForeignKeyConstraint(["org_id", "client_id"], ["clients.org_id", "clients.id"],
                                name="fk_applicant_profile_client"),
    )
    op.create_table(
        "applicant_family_members",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("relationship", sa.String(32), nullable=False),
        sa.Column("given_name", sa.String(100), nullable=False),
        sa.Column("family_name", sa.String(100), nullable=False),
        sa.Column("date_of_birth", sa.String(10)),
        sa.Column("citizenship", sa.String(100)),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_by_sub", sa.String(255), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("org_id", "client_id", "id", name="uq_applicant_family_client_id"),
        sa.ForeignKeyConstraint(["org_id", "client_id"], ["clients.org_id", "clients.id"],
                                name="fk_applicant_family_client"),
        sa.CheckConstraint(
            "relationship IN ('spouse','common_law_partner','child','parent','sibling','other')",
            name="ck_applicant_family_relationship"),
    )
    op.create_index("ix_applicant_family_client", "applicant_family_members", ["org_id", "client_id"])
    op.create_table(
        "case_answer_drafts",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("form_code", sa.String(20), nullable=False),
        sa.Column("source_revision", sa.String(120), nullable=False),
        sa.Column("profile_version", sa.Integer(), nullable=False),
        sa.Column("answers", sa.JSON(), nullable=False),
        sa.Column("unresolved_fields", sa.JSON(), nullable=False),
        sa.Column("created_by_sub", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_id", "client_id", "case_id"],
                                ["cases.org_id", "cases.client_id", "cases.id"],
                                name="fk_answer_draft_case_client"),
        sa.ForeignKeyConstraint(["org_id", "client_id"], ["clients.org_id", "clients.id"],
                                name="fk_answer_draft_client"),
        sa.CheckConstraint("form_code IN ('IMM1294','IMM5709')", name="ck_answer_draft_form"),
    )
    op.create_index("ix_answer_draft_case", "case_answer_drafts",
                    ["org_id", "case_id", "created_at"])
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in ("applicant_profiles", "applicant_family_members", "case_answer_drafts"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        subject = "updated_by_sub" if table != "case_answer_drafts" else "created_by_sub"
        scope = f"""(org_id::text=current_setting('app.tenant_id',true)
            AND EXISTS (SELECT 1 FROM memberships m
                WHERE m.org_id={table}.org_id
                  AND m.subject=current_setting('app.principal_sub',true)
                  AND m.is_active))"""
        rights = f"""EXISTS (SELECT 1 FROM memberships m
             WHERE m.org_id={table}.org_id
               AND m.subject=current_setting('app.principal_sub',true)
               AND m.is_active AND m.role IN ('owner','admin','consultant'))"""
        op.execute(f"CREATE POLICY {table}_read ON {table} FOR SELECT USING ({scope})")
        op.execute(f"""CREATE POLICY {table}_insert ON {table} FOR INSERT
            WITH CHECK ({scope} AND {rights}
                AND {subject}=current_setting('app.principal_sub',true))""")
        if table != "case_answer_drafts":
            op.execute(f"""CREATE POLICY {table}_update ON {table} FOR UPDATE
                USING ({scope} AND {rights}) WITH CHECK ({scope} AND {rights}
                AND updated_by_sub=current_setting('app.principal_sub',true))""")
    op.execute("""DO $grants$ BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='immigrationos_app') THEN
            GRANT SELECT,INSERT,UPDATE(data,version,updated_by_sub,updated_at)
                ON applicant_profiles TO immigrationos_app;
            GRANT SELECT,INSERT,UPDATE(relationship,given_name,family_name,date_of_birth,
                citizenship,version,updated_by_sub,updated_at)
                ON applicant_family_members TO immigrationos_app;
            GRANT SELECT,INSERT ON case_answer_drafts TO immigrationos_app;
        END IF;
    END $grants$""")


def downgrade():
    op.drop_index("ix_answer_draft_case", table_name="case_answer_drafts")
    op.drop_table("case_answer_drafts")
    op.drop_index("ix_applicant_family_client", table_name="applicant_family_members")
    op.drop_table("applicant_family_members")
    op.drop_table("applicant_profiles")
