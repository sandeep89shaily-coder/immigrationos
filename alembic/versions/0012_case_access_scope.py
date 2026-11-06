"""Add revocable, case-scoped assistant grants without mutating case history.

Revision ID: 0012_case_access_scope
Revises: 0011_service_engagement
"""
from alembic import op
import sqlalchemy as sa

revision = "0012_case_access_scope"
down_revision = "0011_service_engagement"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('clients', sa.Column('created_by_sub', sa.String(255)))
    op.create_table(
        "case_access_grants",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("scope", sa.String(16), nullable=False),
        sa.Column("granted_by_sub", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_by_sub", sa.String(255)),
        sa.ForeignKeyConstraint(["org_id", "case_id"], ["cases.org_id", "cases.id"],
                                name="fk_case_access_grant_case_tenant"),
        sa.CheckConstraint("scope IN ('read','intake')", name="ck_case_access_scope"),
    )
    op.create_index("uq_case_access_active_subject", "case_access_grants",
                    ["org_id", "case_id", "subject"], unique=True,
                    postgresql_where=sa.text("revoked_at IS NULL"),
                    sqlite_where=sa.text("revoked_at IS NULL"))
    op.create_index("ix_case_access_subject_active", "case_access_grants",
                    ["org_id", "subject", "revoked_at"])
    if op.get_bind().dialect.name != "postgresql":
        return

    # Narrow SECURITY DEFINER helper: the runtime role can normally SELECT only
    # its own membership row. Checking a prospective teammate requires a
    # reviewer-scoped lookup without granting unrestricted membership reads.
    # The migration owner (not the app role) owns this function.
    op.execute("""CREATE FUNCTION crm_active_member_in_roles(
        p_org uuid, p_target text, p_roles text[]
    ) RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path = pg_catalog, public
    AS $member_check$
        SELECT
            p_org::text = current_setting('app.tenant_id', true)
            AND EXISTS (
                SELECT 1 FROM public.memberships actor
                WHERE actor.org_id = p_org
                  AND actor.subject = current_setting('app.principal_sub', true)
                  AND actor.is_active
                  AND actor.role IN ('owner','admin','consultant')
            )
            AND EXISTS (
                SELECT 1 FROM public.memberships target
                WHERE target.org_id = p_org
                  AND target.subject = p_target
                  AND target.is_active
                  AND target.role = ANY (p_roles)
            )
    $member_check$""")
    op.execute("REVOKE ALL ON FUNCTION crm_active_member_in_roles(uuid,text,text[]) FROM PUBLIC")
    op.execute("""DO $grant_role$ BEGIN IF EXISTS(SELECT 1 FROM pg_roles
        WHERE rolname='immigrationos_app') THEN
        GRANT EXECUTE ON FUNCTION crm_active_member_in_roles(uuid,text,text[])
            TO immigrationos_app;
        END IF; END $grant_role$""")
    # The older membership INSERT policy let a DB session self-enrol into an
    # arbitrary firm by setting tenant_id. Restrict bootstrap to the org creator
    # and to its FIRST owner, before any membership exists. Future team joining
    # must use a separately reviewed invitation workflow.
    op.execute("""CREATE FUNCTION crm_can_bootstrap_owner(
        p_org uuid, p_subject text
    ) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path = pg_catalog, public
    AS $bootstrap$
        SELECT
            p_org::text = current_setting('app.tenant_id', true)
            AND p_subject = current_setting('app.principal_sub', true)
            AND EXISTS (
                SELECT 1 FROM public.organizations org
                WHERE org.id = p_org AND org.created_by_sub = p_subject
            )
            AND NOT EXISTS (
                SELECT 1 FROM public.memberships m WHERE m.org_id = p_org
            )
    $bootstrap$""")
    op.execute("REVOKE ALL ON FUNCTION crm_can_bootstrap_owner(uuid,text) FROM PUBLIC")
    op.execute("""DO $grant_bootstrap$ BEGIN
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='immigrationos_app') THEN
            GRANT EXECUTE ON FUNCTION crm_can_bootstrap_owner(uuid,text)
                TO immigrationos_app;
        END IF;
    END $grant_bootstrap$""")
    op.execute("DROP POLICY membership_insert ON memberships")
    op.execute("""CREATE POLICY membership_insert ON memberships FOR INSERT
        WITH CHECK (role='owner' AND is_active
          AND subject = current_setting('app.principal_sub', true)
          AND crm_can_bootstrap_owner(org_id, subject))""")
    op.execute("ALTER TABLE case_access_grants ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE case_access_grants FORCE ROW LEVEL SECURITY")
    base = """(case_access_grants.org_id::text = current_setting('app.tenant_id', true)
        AND EXISTS (SELECT 1 FROM memberships m
        WHERE m.org_id = case_access_grants.org_id
          AND m.subject = current_setting('app.principal_sub', true)
          AND m.is_active))"""
    reviewers = """(case_access_grants.org_id::text = current_setting('app.tenant_id', true)
        AND EXISTS (SELECT 1 FROM memberships m
        WHERE m.org_id = case_access_grants.org_id
          AND m.subject = current_setting('app.principal_sub', true)
          AND m.is_active AND m.role IN ('owner','admin','consultant')))"""
    op.execute(f"CREATE POLICY case_access_read ON case_access_grants FOR SELECT USING ({base})")
    op.execute(f"""CREATE POLICY case_access_insert ON case_access_grants FOR INSERT WITH CHECK
        ({reviewers} AND granted_by_sub = current_setting('app.principal_sub', true)
         AND revoked_at IS NULL AND revoked_by_sub IS NULL
         AND crm_active_member_in_roles(case_access_grants.org_id,
             case_access_grants.subject, ARRAY['assistant']::text[]))""")
    op.execute(f"""CREATE POLICY case_access_revoke ON case_access_grants FOR UPDATE
        USING ({reviewers} AND revoked_at IS NULL)
        WITH CHECK ({reviewers} AND revoked_at IS NOT NULL
                    AND revoked_by_sub = current_setting('app.principal_sub', true))""")
    op.execute("""DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles
        WHERE rolname='immigrationos_app') THEN
        GRANT SELECT, INSERT ON case_access_grants TO immigrationos_app;
        GRANT UPDATE (revoked_at, revoked_by_sub) ON case_access_grants TO immigrationos_app;
        END IF; END $$""")


def downgrade():
    op.drop_index("ix_case_access_subject_active", table_name="case_access_grants")
    op.drop_index("uq_case_access_active_subject", table_name="case_access_grants")
    op.drop_table("case_access_grants")
    op.drop_column("clients", "created_by_sub")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP FUNCTION IF EXISTS crm_active_member_in_roles(uuid,text,text[])")
        op.execute("DROP POLICY IF EXISTS membership_insert ON memberships")
        op.execute("""CREATE POLICY membership_insert ON memberships FOR INSERT
            WITH CHECK (subject = current_setting('app.principal_sub', true)
              AND org_id::text = current_setting('app.tenant_id', true))""")
        op.execute("DROP FUNCTION IF EXISTS crm_can_bootstrap_owner(uuid,text)")
