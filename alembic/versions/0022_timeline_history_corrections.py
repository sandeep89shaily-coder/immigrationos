"""Append-only timeline-to-history correction provenance.

Revision ID: 0022_timeline_history_corrections
Revises: 0021_timeline_clarifications
"""
from alembic import op
import sqlalchemy as sa

revision="0022_timeline_history_corrections"
down_revision="0021_timeline_clarifications"
branch_labels=None
depends_on=None


def upgrade():
    op.create_table("timeline_history_corrections",
        sa.Column("id",sa.Uuid(),primary_key=True),
        sa.Column("org_id",sa.Uuid(),sa.ForeignKey("organizations.id"),nullable=False),
        sa.Column("case_id",sa.Uuid(),nullable=False),
        sa.Column("client_id",sa.Uuid(),nullable=False),
        sa.Column("request_id",sa.Uuid(),nullable=False),
        sa.Column("decision_id",sa.Uuid(),nullable=False),
        sa.Column("reply_id",sa.Uuid(),nullable=False),
        sa.Column("record_id",sa.Uuid(),nullable=False),
        sa.Column("operation",sa.String(12),nullable=False),
        sa.Column("kind",sa.String(20),nullable=False),
        sa.Column("prior_version",sa.Integer()),
        sa.Column("new_version",sa.Integer(),nullable=False),
        sa.Column("prior_details",sa.JSON()),
        sa.Column("new_details",sa.JSON(),nullable=False),
        sa.Column("correction_reason",sa.String(600),nullable=False),
        sa.Column("created_by_sub",sa.String(255),nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
        sa.ForeignKeyConstraint(["org_id","case_id","request_id"],
            ["timeline_clarifications.org_id","timeline_clarifications.case_id",
             "timeline_clarifications.id"],name="fk_timeline_correction_request"),
        sa.ForeignKeyConstraint(["org_id","client_id"],["clients.org_id","clients.id"],
                                name="fk_timeline_correction_client"),
        sa.UniqueConstraint("org_id","request_id",name="uq_timeline_correction_once"),
        sa.CheckConstraint("operation IN ('create','update')",
                           name="ck_timeline_correction_operation"))
    op.create_index("ix_timeline_correction_case","timeline_history_corrections",
                    ["org_id","case_id","created_at"])
    if op.get_bind().dialect.name!="postgresql":
        return
    table="timeline_history_corrections"
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    common=f"""({table}.org_id::text=current_setting('app.tenant_id',true)
        AND EXISTS (SELECT 1 FROM memberships m
          WHERE m.org_id={table}.org_id
          AND m.subject=current_setting('app.principal_sub',true) AND m.is_active))"""
    writers=f"""({common} AND {table}.created_by_sub=current_setting('app.principal_sub',true)
        AND EXISTS (SELECT 1 FROM memberships m
          WHERE m.org_id={table}.org_id AND m.subject=current_setting('app.principal_sub',true)
          AND m.is_active AND m.role IN ('owner','admin','consultant')))"""
    op.execute(f"CREATE POLICY timeline_history_correction_select ON {table} FOR SELECT USING ({common})")
    op.execute(f"CREATE POLICY timeline_history_correction_insert ON {table} FOR INSERT WITH CHECK ({writers})")
    op.execute("""DO $grant$ BEGIN IF EXISTS (
        SELECT 1 FROM pg_roles WHERE rolname='immigrationos_app') THEN
        GRANT SELECT,INSERT ON timeline_history_corrections TO immigrationos_app;
        REVOKE UPDATE,DELETE ON timeline_history_corrections FROM immigrationos_app;
    END IF; END $grant$""")


def downgrade():
    op.drop_index("ix_timeline_correction_case",table_name="timeline_history_corrections")
    op.drop_table("timeline_history_corrections")
