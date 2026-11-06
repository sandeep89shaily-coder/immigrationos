"""Verified-email, single-use staff onboarding and narrow manager privilege helpers.

Revision ID: 0013_verified_staff_invites
Revises: 0012_case_access_scope

All SECURITY DEFINER functions belong to migration role, not runtime app role.
The app cannot directly INSERT/UPDATE invited Membership records.
"""
from alembic import op
import sqlalchemy as sa

revision = "0013_verified_staff_invites"
down_revision = "0012_case_access_scope"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("memberships", sa.Column("verified_email", sa.String(254), nullable=True))
    op.create_index(
        "uq_membership_org_verified_email", "memberships",
        ["org_id", sa.text("lower(verified_email)")],
        unique=True,
        postgresql_where=sa.text("verified_email IS NOT NULL"),
        sqlite_where=sa.text("verified_email IS NOT NULL"),
    )
    op.create_table(
        "staff_invitations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("invited_email", sa.String(254), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("created_by_sub", sa.String(255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_by_sub", sa.String(255)),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_by_sub", sa.String(255)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("token_hash", name="uq_staff_invitation_token_hash"),
        sa.CheckConstraint("role IN ('admin','consultant','assistant','viewer')",
                           name="ck_staff_invitation_role"),
        sa.CheckConstraint("""NOT (accepted_at IS NOT NULL AND revoked_at IS NOT NULL)
            AND (accepted_at IS NULL OR accepted_by_sub IS NOT NULL)
            AND (revoked_at IS NULL OR revoked_by_sub IS NOT NULL)""",
                           name="ck_staff_invitation_terminal"),
    )
    op.create_index("ix_staff_invitation_org_email", "staff_invitations",
                    ["org_id", "invited_email", "expires_at"])
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute("""CREATE FUNCTION ios_staff_is_manager(p_org uuid, p_owner_only boolean)
        RETURNS boolean
        LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $manager$
          SELECT p_org::text = current_setting('app.tenant_id', true)
             AND EXISTS (SELECT 1 FROM public.memberships m
                WHERE m.org_id = p_org
                  AND m.subject = current_setting('app.principal_sub', true)
                  AND m.is_active
                  AND (m.role = 'owner' OR (NOT p_owner_only AND m.role='admin')))
        $manager$""")
    op.execute("REVOKE ALL ON FUNCTION ios_staff_is_manager(uuid,boolean) FROM PUBLIC")
    op.execute("""CREATE FUNCTION ios_accept_staff_invitation(p_digest text)
        RETURNS TABLE(org_id uuid, invitation_id uuid, assigned_role text)
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $accept$
        DECLARE
            invited public.staff_invitations%ROWTYPE;
            assigned_id uuid;
            principal text := current_setting('app.principal_sub', true);
            verified text := lower(current_setting('app.verified_email', true));
        BEGIN
            IF principal IS NULL OR length(principal) < 1
                OR verified IS NULL OR position('@' IN verified) < 2
                OR p_digest !~ '^[0-9a-f]{64}$' THEN
                RETURN;
            END IF;
            SELECT * INTO invited FROM public.staff_invitations si
                WHERE si.token_hash = p_digest
                  AND si.invited_email = verified
                  AND si.accepted_at IS NULL AND si.revoked_at IS NULL
                  AND si.expires_at > now()
                FOR UPDATE;
            IF NOT FOUND THEN RETURN; END IF;
            IF EXISTS (SELECT 1 FROM public.memberships m
                WHERE m.org_id = invited.org_id
                  AND (m.subject = principal
                       OR lower(m.verified_email) = verified))
                THEN RETURN;
            END IF;
            INSERT INTO public.memberships
                (id, org_id, subject, role, is_active, verified_email, created_at)
            VALUES (gen_random_uuid(), invited.org_id, principal,
                    invited.role, TRUE, verified, now())
            ON CONFLICT (org_id,subject) DO NOTHING
            RETURNING id INTO assigned_id;
            IF assigned_id IS NULL THEN RETURN; END IF;
            UPDATE public.staff_invitations si
                SET accepted_at = now(), accepted_by_sub = principal
                WHERE si.id = invited.id;
            org_id := invited.org_id;
            invitation_id := invited.id;
            assigned_role := invited.role;
            RETURN NEXT;
        END
        $accept$""")
    op.execute("REVOKE ALL ON FUNCTION ios_accept_staff_invitation(text) FROM PUBLIC")
    op.execute("""CREATE FUNCTION ios_change_staff_role(
            p_org uuid, p_target text, p_role text
        ) RETURNS boolean
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $change$
        DECLARE old_role text;
        BEGIN
            IF NOT public.ios_staff_is_manager(p_org, FALSE)
                OR p_target = current_setting('app.principal_sub', true)
                OR p_role NOT IN ('admin','consultant','assistant','viewer') THEN
                RETURN FALSE;
            END IF;
            SELECT m.role INTO old_role FROM public.memberships m
                WHERE m.org_id=p_org AND m.subject=p_target AND m.is_active
                FOR UPDATE;
            IF NOT FOUND OR old_role='owner' THEN RETURN FALSE; END IF;
            IF (old_role='admin' OR p_role='admin')
                AND NOT public.ios_staff_is_manager(p_org, TRUE) THEN
                RETURN FALSE;
            END IF;
            UPDATE public.memberships m SET role=p_role
                WHERE m.org_id=p_org AND m.subject=p_target AND m.is_active;
            RETURN FOUND;
        END
        $change$""")
    op.execute("REVOKE ALL ON FUNCTION ios_change_staff_role(uuid,text,text) FROM PUBLIC")
    op.execute("""CREATE FUNCTION ios_revoke_staff(p_org uuid, p_target text)
        RETURNS boolean
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $revoke$
        DECLARE old_role text;
        BEGIN
            IF NOT public.ios_staff_is_manager(p_org, FALSE)
               OR p_target=current_setting('app.principal_sub', true) THEN
                RETURN FALSE;
            END IF;
            SELECT m.role INTO old_role FROM public.memberships m
                WHERE m.org_id=p_org AND m.subject=p_target AND m.is_active
                FOR UPDATE;
            IF NOT FOUND OR old_role='owner' THEN RETURN FALSE; END IF;
            IF old_role='admin'
                AND NOT public.ios_staff_is_manager(p_org, TRUE) THEN
                RETURN FALSE;
            END IF;
            UPDATE public.memberships m SET is_active=FALSE
                WHERE m.org_id=p_org AND m.subject=p_target AND m.is_active;
            RETURN FOUND;
        END
        $revoke$""")
    op.execute("REVOKE ALL ON FUNCTION ios_revoke_staff(uuid,text) FROM PUBLIC")
    op.execute("""DO $grants$ BEGIN
        IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='immigrationos_app') THEN
            GRANT EXECUTE ON FUNCTION ios_staff_is_manager(uuid,boolean),
                ios_accept_staff_invitation(text),
                ios_change_staff_role(uuid,text,text),
                ios_revoke_staff(uuid,text) TO immigrationos_app;
            GRANT SELECT, INSERT ON staff_invitations TO immigrationos_app;
            GRANT UPDATE (revoked_at,revoked_by_sub) ON staff_invitations
                TO immigrationos_app;
        END IF;
        END $grants$""")

    op.execute("DROP POLICY membership_select ON memberships")
    op.execute("""CREATE POLICY membership_select ON memberships FOR SELECT USING (
        subject = current_setting('app.principal_sub', true)
        OR ios_staff_is_manager(org_id,FALSE))""")

    op.execute("ALTER TABLE staff_invitations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE staff_invitations FORCE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY staff_invitation_read ON staff_invitations
        FOR SELECT USING (
           ios_staff_is_manager(staff_invitations.org_id,FALSE))""")
    op.execute("""CREATE POLICY staff_invitation_insert ON staff_invitations
        FOR INSERT WITH CHECK (
            ios_staff_is_manager(staff_invitations.org_id,FALSE)
            AND created_by_sub=current_setting('app.principal_sub', true)
            AND revoked_at IS NULL AND accepted_at IS NULL
            AND revoked_by_sub IS NULL AND accepted_by_sub IS NULL
            AND expires_at > now() AND expires_at <= now() + interval '7 days'
            AND (role <> 'admin'
                 OR ios_staff_is_manager(staff_invitations.org_id,TRUE)))""")
    op.execute("""CREATE POLICY staff_invitation_revoke ON staff_invitations
        FOR UPDATE
        USING (ios_staff_is_manager(staff_invitations.org_id,FALSE)
               AND revoked_at IS NULL AND accepted_at IS NULL
               AND (role <> 'admin'
                    OR ios_staff_is_manager(staff_invitations.org_id,TRUE)))
        WITH CHECK (ios_staff_is_manager(staff_invitations.org_id,FALSE)
            AND revoked_at IS NOT NULL
            AND revoked_by_sub=current_setting('app.principal_sub', true))""")


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP POLICY membership_select ON memberships")
        op.execute("""CREATE POLICY membership_select ON memberships FOR SELECT USING (
            subject=current_setting('app.principal_sub',true))""")
    op.drop_index("ix_staff_invitation_org_email", table_name="staff_invitations")
    op.drop_table("staff_invitations")
    op.drop_index("uq_membership_org_verified_email", table_name="memberships")
    op.drop_column("memberships", "verified_email")
    if op.get_bind().dialect.name == "postgresql":
        for f in ("ios_revoke_staff(uuid,text)",
                  "ios_change_staff_role(uuid,text,text)",
                  "ios_accept_staff_invitation(text)",
                  "ios_staff_is_manager(uuid,boolean)"):
            op.execute("DROP FUNCTION " + f)
