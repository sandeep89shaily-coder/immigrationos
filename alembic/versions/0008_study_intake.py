"""Case-scoped, append-only study-permit client intake.

Revision ID: 0008_study_intake
Revises: 0007_review_snapshots
Synthetic/development data only. The runtime role is not granted UPDATE/DELETE.
"""
from alembic import op
import sqlalchemy as sa

revision = "0008_study_intake"
down_revision = "0007_review_snapshots"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "study_intake_submissions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_sub", sa.String(255), nullable=False),
        sa.Column("template_version", sa.String(80), nullable=False),
        sa.Column("notice_version", sa.String(80), nullable=False),
        sa.Column("answers", sa.JSON(), nullable=False),
        sa.Column("answer_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_id", "case_id"], ["cases.org_id", "cases.id"],
                                name="fk_study_intake_same_tenant"),
        sa.UniqueConstraint("org_id", "case_id", "id", name="uq_study_intake_org_case_id"),
    )
    op.create_index("ix_study_intake_case_created", "study_intake_submissions",
                    ["org_id", "case_id", "created_at"])
    op.create_table(
        "study_intake_decisions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("submission_id", sa.Uuid(), nullable=False),
        sa.Column("field_path", sa.String(160), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("created_fact_id", sa.Uuid()),
        sa.Column("reviewed_by_sub", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["org_id", "case_id", "submission_id"],
            ["study_intake_submissions.org_id", "study_intake_submissions.case_id",
             "study_intake_submissions.id"], name="fk_study_intake_decision_same_case"),
        sa.ForeignKeyConstraint(["org_id", "case_id"], ["cases.org_id", "cases.id"],
                                name="fk_study_intake_decision_case"),
        sa.UniqueConstraint("org_id", "submission_id", "field_path",
                            name="uq_study_intake_review_once"),
        sa.CheckConstraint("decision IN ('accept','dismiss')", name="ck_study_intake_decision"),
    )
    op.create_index("ix_study_intake_decisions_case", "study_intake_decisions",
                    ["org_id", "case_id"])

    if op.get_bind().dialect.name != "postgresql":
        return

    for table in ("study_intake_submissions", "study_intake_decisions"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

    def staff(table):
        return f"""({table}.org_id::text = current_setting('app.tenant_id', true)
            AND EXISTS (SELECT 1 FROM memberships m WHERE m.org_id = {table}.org_id
            AND m.subject = current_setting('app.principal_sub', true) AND m.is_active))"""

    for table in ("study_intake_submissions", "study_intake_decisions"):
        predicate = staff(table)
        op.execute(f"""CREATE POLICY {table}_staff ON {table} FOR ALL
            USING ({predicate}) WITH CHECK ({predicate})""")

    client = """(
        created_by_sub = current_setting('app.principal_sub', true)
        AND current_setting('app.verified_email', true) <> ''
        AND EXISTS (SELECT 1 FROM portal_grants g
          WHERE g.org_id = study_intake_submissions.org_id
          AND g.case_id = study_intake_submissions.case_id
          AND g.principal_sub = current_setting('app.principal_sub', true)
          AND g.revoked_at IS NULL)
    )"""
    op.execute(f"CREATE POLICY intake_client_select ON study_intake_submissions FOR SELECT USING ({client})")
    op.execute(f"CREATE POLICY intake_client_insert ON study_intake_submissions FOR INSERT WITH CHECK ({client})")

    # Explicitly add ONLY the new client-side event action to the portal audit allowlist.
    op.execute("DROP POLICY portal_audit_insert ON audit_events")
    op.execute("""CREATE POLICY portal_audit_insert ON audit_events FOR INSERT WITH CHECK (
        actor_sub = current_setting('app.principal_sub', true)
        AND action IN ('portal.invitation_accepted',
                       'portal.document_received_quarantined',
                       'portal.study_intake_submitted')
        AND EXISTS (SELECT 1 FROM portal_grants g WHERE g.org_id = audit_events.org_id
            AND g.principal_sub = current_setting('app.principal_sub', true)
            AND g.revoked_at IS NULL))""")

    op.execute("""DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles
        WHERE rolname = 'immigrationos_app') THEN
        GRANT SELECT, INSERT ON study_intake_submissions TO immigrationos_app;
        GRANT SELECT, INSERT ON study_intake_decisions TO immigrationos_app;
        REVOKE UPDATE, DELETE ON study_intake_submissions FROM immigrationos_app;
        REVOKE UPDATE, DELETE ON study_intake_decisions FROM immigrationos_app;
        END IF; END $$""")


def downgrade():
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP POLICY portal_audit_insert ON audit_events")
        op.execute("""CREATE POLICY portal_audit_insert ON audit_events FOR INSERT WITH CHECK (
            actor_sub = current_setting('app.principal_sub', true)
            AND action IN ('portal.invitation_accepted', 'portal.document_received_quarantined')
            AND EXISTS (SELECT 1 FROM portal_grants g WHERE g.org_id = audit_events.org_id
              AND g.principal_sub = current_setting('app.principal_sub', true)
              AND g.revoked_at IS NULL))""")
    op.drop_index("ix_study_intake_decisions_case", table_name="study_intake_decisions")
    op.drop_table("study_intake_decisions")
    op.drop_index("ix_study_intake_case_created", table_name="study_intake_submissions")
    op.drop_table("study_intake_submissions")
