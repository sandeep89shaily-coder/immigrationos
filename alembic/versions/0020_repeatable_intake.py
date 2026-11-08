"""Client repeatable proposals, append-only and scoped by portal grant.

Revision ID: 0020_repeatable_intake
Revises: 0019_imm5476_packets
"""
from alembic import op
import sqlalchemy as sa

revision = "0020_repeatable_intake"
down_revision = "0019_imm5476_packets"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "client_repeatable_proposals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("template_version", sa.String(80), nullable=False),
        sa.Column("notice_version", sa.String(80), nullable=False),
        sa.Column("created_by_sub", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_id", "case_id"], ["cases.org_id", "cases.id"],
                                name="fk_repeatable_proposal_case"),
        sa.UniqueConstraint("org_id", "case_id", "id",
                            name="uq_repeatable_proposal_case_id"),
        sa.CheckConstraint("kind IN ('family','address','education','employment','travel')",
                           name="ck_repeatable_proposal_kind"),
    )
    op.create_index("ix_repeatable_proposals_case", "client_repeatable_proposals",
                    ["org_id", "case_id", "created_at"])
    op.create_table(
        "client_repeatable_decisions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("proposal_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(12), nullable=False),
        sa.Column("created_record_id", sa.Uuid()),
        sa.Column("reviewed_by_sub", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["org_id", "case_id", "proposal_id"],
            ["client_repeatable_proposals.org_id",
             "client_repeatable_proposals.case_id", "client_repeatable_proposals.id"],
            name="fk_repeatable_decision_proposal"),
        sa.UniqueConstraint("org_id", "proposal_id", name="uq_repeatable_decision_once"),
        sa.CheckConstraint("decision IN ('accept','dismiss')",
                           name="ck_repeatable_decision"),
    )
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in ("client_repeatable_proposals", "client_repeatable_decisions"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

    staff_proposals = """(client_repeatable_proposals.org_id::text =
        current_setting('app.tenant_id', true)
        AND EXISTS (SELECT 1 FROM memberships m
          WHERE m.org_id=client_repeatable_proposals.org_id
            AND m.subject=current_setting('app.principal_sub',true)
            AND m.is_active))"""
    client = """(client_repeatable_proposals.created_by_sub =
        current_setting('app.principal_sub',true)
        AND current_setting('app.verified_email',true) <> ''
        AND EXISTS (SELECT 1 FROM portal_grants g
          WHERE g.org_id=client_repeatable_proposals.org_id
            AND g.case_id=client_repeatable_proposals.case_id
            AND g.principal_sub=current_setting('app.principal_sub',true)
            AND g.revoked_at IS NULL))"""
    op.execute(f"""CREATE POLICY repeatable_proposal_staff_select
        ON client_repeatable_proposals FOR SELECT USING ({staff_proposals})""")
    op.execute(f"""CREATE POLICY repeatable_proposal_client_select
        ON client_repeatable_proposals FOR SELECT USING ({client})""")
    op.execute(f"""CREATE POLICY repeatable_proposal_client_insert
        ON client_repeatable_proposals FOR INSERT WITH CHECK ({client})""")

    staff_decision = """(client_repeatable_decisions.org_id::text =
        current_setting('app.tenant_id',true)
        AND EXISTS (SELECT 1 FROM memberships m
          WHERE m.org_id=client_repeatable_decisions.org_id
            AND m.subject=current_setting('app.principal_sub',true)
            AND m.is_active))"""
    reviewer = """(client_repeatable_decisions.org_id::text =
        current_setting('app.tenant_id',true)
        AND client_repeatable_decisions.reviewed_by_sub =
            current_setting('app.principal_sub',true)
        AND EXISTS (SELECT 1 FROM memberships m
          WHERE m.org_id=client_repeatable_decisions.org_id
            AND m.subject=current_setting('app.principal_sub',true)
            AND m.is_active AND m.role IN ('owner','admin','consultant')))"""
    op.execute(f"""CREATE POLICY repeatable_decision_staff_select
        ON client_repeatable_decisions FOR SELECT USING ({staff_decision})""")
    op.execute(f"""CREATE POLICY repeatable_decision_staff_insert
        ON client_repeatable_decisions FOR INSERT WITH CHECK ({reviewer})""")

    # Preserve the existing portal audit action allowlist, extend narrowly.
    op.execute("DROP POLICY portal_audit_insert ON audit_events")
    op.execute("""CREATE POLICY portal_audit_insert ON audit_events FOR INSERT WITH CHECK (
        actor_sub = current_setting('app.principal_sub', true)
        AND action IN ('portal.invitation_accepted',
                       'portal.document_received_quarantined',
                       'portal.study_intake_submitted',
                       'portal.repeatable_proposal_submitted')
        AND EXISTS (SELECT 1 FROM portal_grants g WHERE g.org_id = audit_events.org_id
            AND g.principal_sub = current_setting('app.principal_sub', true)
            AND g.revoked_at IS NULL))""")

    op.execute("""DO $grants$ BEGIN
       IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='immigrationos_app') THEN
           GRANT SELECT,INSERT ON client_repeatable_proposals TO immigrationos_app;
           GRANT SELECT,INSERT ON client_repeatable_decisions TO immigrationos_app;
           REVOKE UPDATE,DELETE ON client_repeatable_proposals FROM immigrationos_app;
           REVOKE UPDATE,DELETE ON client_repeatable_decisions FROM immigrationos_app;
       END IF;
    END $grants$""")


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP POLICY portal_audit_insert ON audit_events")
        op.execute("""CREATE POLICY portal_audit_insert ON audit_events FOR INSERT WITH CHECK (
            actor_sub = current_setting('app.principal_sub', true)
            AND action IN ('portal.invitation_accepted',
                           'portal.document_received_quarantined',
                           'portal.study_intake_submitted')
            AND EXISTS (SELECT 1 FROM portal_grants g WHERE g.org_id = audit_events.org_id
                AND g.principal_sub = current_setting('app.principal_sub', true)
                AND g.revoked_at IS NULL))""")
    op.drop_table("client_repeatable_decisions")
    op.drop_index("ix_repeatable_proposals_case", table_name="client_repeatable_proposals")
    op.drop_table("client_repeatable_proposals")
