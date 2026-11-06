"""Initial PostgreSQL schema with FORCE RLS and an append-only audit log.

Revision ID: 0001_initial
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("organizations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("created_by_sub", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table("memberships",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("org_id", "subject", name="uq_membership_org_subject"),
        sa.CheckConstraint("role IN ('owner','admin','consultant','assistant','viewer')", name="ck_membership_role"),
    )
    op.create_index("ix_memberships_subject", "memberships", ["subject"])
    op.create_table("clients",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("email", sa.String(254), nullable=True),
        sa.Column("phone", sa.String(40), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("org_id", "id", name="uq_client_org_id"),
    )
    op.create_index("ix_clients_org_created", "clients", ["org_id", "created_at"])
    op.create_table("cases",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("client_id", sa.Uuid(), nullable=False),
        sa.Column("application_type", sa.String(80), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_id", "client_id"], ["clients.org_id", "clients.id"], name="fk_case_client_same_tenant"),
        sa.CheckConstraint("status IN ('draft','intake','review','on_hold','closed')", name="ck_case_status"),
    )
    op.create_index("ix_cases_org_status", "cases", ["org_id", "status"])
    op.create_table("audit_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("actor_sub", sa.String(255), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_org_occurred", "audit_events", ["org_id", "occurred_at"])

    if op.get_bind().dialect.name == "postgresql":
        # FORCE RLS protects owner-executed queries too (superusers still bypass RLS).
        for name in ("organizations", "memberships", "clients", "cases", "audit_events"):
            op.execute(f"ALTER TABLE {name} ENABLE ROW LEVEL SECURITY")
            op.execute(f"ALTER TABLE {name} FORCE ROW LEVEL SECURITY")
        op.execute("""CREATE POLICY org_select ON organizations FOR SELECT USING (
            EXISTS (SELECT 1 FROM memberships m WHERE m.org_id = organizations.id
            AND m.subject = current_setting('app.principal_sub', true) AND m.is_active = true)
        )""")
        op.execute("""CREATE POLICY org_insert ON organizations FOR INSERT WITH CHECK (
            created_by_sub = current_setting('app.principal_sub', true)
        )""")
        op.execute("""CREATE POLICY membership_select ON memberships FOR SELECT USING (
            subject = current_setting('app.principal_sub', true)
        )""")
        op.execute("""CREATE POLICY membership_insert ON memberships FOR INSERT WITH CHECK (
            subject = current_setting('app.principal_sub', true)
            AND org_id::text = current_setting('app.tenant_id', true)
        )""")
        for name in ("clients", "cases"):
            op.execute(f"""CREATE POLICY {name}_tenant_all ON {name} FOR ALL
                USING (org_id::text = current_setting('app.tenant_id', true))
                WITH CHECK (org_id::text = current_setting('app.tenant_id', true))""")
        op.execute("""CREATE POLICY audit_select ON audit_events FOR SELECT USING (
            org_id::text = current_setting('app.tenant_id', true)
        )""")
        op.execute("""CREATE POLICY audit_insert ON audit_events FOR INSERT WITH CHECK (
            org_id::text = current_setting('app.tenant_id', true)
        )""")
        op.execute("""CREATE FUNCTION forbid_audit_mutation() RETURNS trigger AS $$
            BEGIN RAISE EXCEPTION 'audit_events is append-only'; END; $$ LANGUAGE plpgsql""")
        op.execute("""CREATE TRIGGER audit_immutable BEFORE UPDATE OR DELETE ON audit_events
            FOR EACH ROW EXECUTE FUNCTION forbid_audit_mutation()""")
        # Least privilege: no direct DELETE on business records; no UPDATE/DELETE of audit records.
        op.execute("""DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='immigrationos_app') THEN
            GRANT SELECT, INSERT ON organizations TO immigrationos_app;
            GRANT SELECT, INSERT ON memberships TO immigrationos_app;
            GRANT SELECT, INSERT, UPDATE ON clients TO immigrationos_app;
            GRANT SELECT, INSERT, UPDATE ON cases TO immigrationos_app;
            GRANT SELECT, INSERT ON audit_events TO immigrationos_app;
            REVOKE DELETE ON organizations, memberships, clients, cases, audit_events FROM immigrationos_app;
            REVOKE UPDATE ON audit_events, organizations, memberships FROM immigrationos_app;
        END IF; END $$""")


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS audit_immutable ON audit_events")
        op.execute("DROP FUNCTION IF EXISTS forbid_audit_mutation()")
    for name in ("audit_events", "cases", "clients", "memberships", "organizations"):
        op.drop_table(name)
