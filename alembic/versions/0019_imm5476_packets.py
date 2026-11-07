"""Append-only IMM5476 reviewed-evidence checkpoints with strict RLS.

Revision ID: 0019_imm5476_packets
Revises: 0018_form_preparation
"""
from alembic import op
import sqlalchemy as sa

revision = "0019_imm5476_packets"
down_revision = "0018_form_preparation"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "imm5476_review_packets",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.Uuid(), sa.ForeignKey("organizations.id"),
                  nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("package_id", sa.Uuid(), nullable=False),
        sa.Column("source_revision", sa.String(32), nullable=False),
        sa.Column("mapping_version", sa.String(100), nullable=False),
        sa.Column("snapshot_sha256", sa.String(64), nullable=False),
        sa.Column("field_snapshot", sa.JSON(), nullable=False),
        sa.Column("blocker_snapshot", sa.JSON(), nullable=False),
        sa.Column("verified_observed_subset", sa.Boolean(), nullable=False),
        sa.Column("created_by_sub", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["org_id", "case_id"], ["cases.org_id", "cases.id"],
            name="fk_imm5476_packet_case"),
        sa.ForeignKeyConstraint(
            ["org_id", "case_id", "package_id"],
            ["case_application_packages.org_id",
             "case_application_packages.case_id", "case_application_packages.id"],
            name="fk_imm5476_packet_package"),
    )
    op.create_index(
        "ix_imm5476_packet_case_created", "imm5476_review_packets",
        ["org_id", "case_id", "created_at"])
    if op.get_bind().dialect.name != "postgresql":
        return
    table = "imm5476_review_packets"
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    scope = """(org_id::text=current_setting('app.tenant_id',true)
        AND EXISTS (SELECT 1 FROM memberships m
          WHERE m.org_id=imm5476_review_packets.org_id
            AND m.subject=current_setting('app.principal_sub',true)
            AND m.is_active))"""
    writers = """EXISTS (SELECT 1 FROM memberships m
          WHERE m.org_id=imm5476_review_packets.org_id
            AND m.subject=current_setting('app.principal_sub',true)
            AND m.is_active AND m.role IN ('owner','admin','consultant'))"""
    op.execute(f"CREATE POLICY {table}_read ON {table} FOR SELECT USING ({scope})")
    op.execute(f"""CREATE POLICY {table}_insert ON {table} FOR INSERT
        WITH CHECK ({scope} AND {writers}
            AND created_by_sub=current_setting('app.principal_sub',true))""")
    op.execute("""DO $grants$ BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='immigrationos_app') THEN
            GRANT SELECT,INSERT ON imm5476_review_packets TO immigrationos_app;
        END IF;
    END $grants$""")


def downgrade():
    op.drop_index(
        "ix_imm5476_packet_case_created",
        table_name="imm5476_review_packets")
    op.drop_table("imm5476_review_packets")
