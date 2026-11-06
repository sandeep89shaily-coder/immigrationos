"""RCIC service engagement gates: tenant-bound, append-only evidence.

Revision ID: 0011_service_engagement
Revises: 0010_crm_followups
"""
from alembic import op
import sqlalchemy as sa

revision = "0011_service_engagement"
down_revision = "0010_crm_followups"
branch_labels = None
depends_on = None


def uid(name, nullable=False, primary_key=False):
    return sa.Column(name, sa.Uuid(), primary_key=primary_key, nullable=nullable)


def upgrade():
    # Prevent a case from being associated with a different client through
    # its firm-scoped matter assignment.
    op.create_unique_constraint("uq_case_org_client_id", "cases", ["org_id", "client_id", "id"])

    op.create_table(
        "engagement_screens",
        uid("id", primary_key=True), uid("org_id"), uid("client_id"),
        sa.Column("prior_rep", sa.String(32), nullable=False),
        sa.Column("conflict_status", sa.String(32), nullable=False),
        sa.Column("client_identity_verified", sa.Boolean(), nullable=False),
        sa.Column("previous_rep_checked", sa.Boolean(), nullable=False),
        sa.Column("details", sa.String(1200), nullable=False),
        sa.Column("reviewer_sub", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.UniqueConstraint("org_id", "client_id", "id", name="uq_engagement_screen_client"),
        sa.ForeignKeyConstraint(["org_id", "client_id"], ["clients.org_id", "clients.id"],
                                name="fk_engagement_screen_client"),
        sa.CheckConstraint("prior_rep IN ('none','ended_in_writing','concurrent','unknown')",
                           name="ck_engagement_prior_rep"),
        sa.CheckConstraint("conflict_status IN ('none_identified','potential','prohibited','unresolved')",
                           name="ck_engagement_conflict"),
    )
    op.create_index("ix_engagement_screen_client_date", "engagement_screens",
                    ["org_id", "client_id", "created_at"])
    op.create_table(
        "service_agreement_drafts",
        uid("id", primary_key=True), uid("org_id"), uid("client_id"), uid("screen_id"),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("clauses", sa.JSON(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("created_by_sub", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.UniqueConstraint("org_id", "client_id", "id", name="uq_service_draft_client"),
        sa.UniqueConstraint("org_id", "client_id", "version", name="uq_service_draft_version"),
        sa.ForeignKeyConstraint(["org_id", "client_id"], ["clients.org_id", "clients.id"],
                                name="fk_service_draft_client"),
        sa.ForeignKeyConstraint(["org_id", "client_id", "screen_id"],
                                ["engagement_screens.org_id", "engagement_screens.client_id",
                                 "engagement_screens.id"], name="fk_service_draft_screen"),
    )
    op.create_index("ix_service_draft_client_version", "service_agreement_drafts",
                    ["org_id", "client_id", "version"])
    op.create_table(
        "service_signed_copies",
        uid("id", primary_key=True), uid("org_id"), uid("client_id"), uid("draft_id"),
        sa.Column("storage_key", sa.String(128), nullable=False, unique=True),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("draft_provided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("client_copy_provided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scan_status", sa.String(16), nullable=False),
        sa.Column("review_status", sa.String(16), nullable=False),
        sa.Column("review_note", sa.String(1000)),
        sa.Column("reviewed_by_sub", sa.String(255)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("created_by_sub", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.UniqueConstraint("org_id", "draft_id", name="uq_service_signed_draft"),
        sa.ForeignKeyConstraint(["org_id", "client_id"], ["clients.org_id", "clients.id"],
                                name="fk_service_signed_client"),
        sa.ForeignKeyConstraint(["org_id", "client_id", "draft_id"],
                                ["service_agreement_drafts.org_id", "service_agreement_drafts.client_id",
                                 "service_agreement_drafts.id"], name="fk_service_signed_draft"),
        sa.CheckConstraint("scan_status IN ('quarantined','cleared','rejected')",
                           name="ck_service_signed_scan"),
        sa.CheckConstraint("review_status IN ('pending','accepted','rejected')",
                           name="ck_service_signed_review"),
    )
    op.create_table(
        "matter_assignments",
        uid("id", primary_key=True), uid("org_id"), uid("client_id"), uid("case_id"), uid("draft_id"),
        sa.Column("professional_sub", sa.String(255), nullable=False),
        sa.Column("assigned_by_sub", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.UniqueConstraint("org_id", "case_id", name="uq_matter_assignment_case"),
        sa.ForeignKeyConstraint(["org_id", "client_id"], ["clients.org_id", "clients.id"],
                                name="fk_matter_assignment_client"),
        sa.ForeignKeyConstraint(["org_id", "client_id", "case_id"],
                                ["cases.org_id", "cases.client_id", "cases.id"],
                                name="fk_matter_assignment_matching_case_client"),
        sa.ForeignKeyConstraint(["org_id", "client_id", "draft_id"],
                                ["service_agreement_drafts.org_id", "service_agreement_drafts.client_id",
                                 "service_agreement_drafts.id"], name="fk_matter_assignment_draft"),
    )
    op.create_index("ix_matter_assignment_professional", "matter_assignments",
                    ["org_id", "professional_sub"])
    if op.get_bind().dialect.name != "postgresql":
        return

    tables = ("engagement_screens", "service_agreement_drafts",
              "service_signed_copies", "matter_assignments")
    for name in tables:
        op.execute(f"ALTER TABLE {name} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {name} FORCE ROW LEVEL SECURITY")

    def predicate(table, roles=None):
        filter_roles = "" if roles is None else (" AND m.role IN (" +
            ",".join("'" + role + "'" for role in roles) + ")")
        return f"""({table}.org_id::text = current_setting('app.tenant_id', true)
            AND EXISTS (SELECT 1 FROM memberships m WHERE m.org_id = {table}.org_id
              AND m.subject = current_setting('app.principal_sub', true)
              AND m.is_active{filter_roles}))"""

    reviewers = ("owner", "admin", "consultant")
    intake = (*reviewers, "assistant")
    for table in tables:
        op.execute(f"CREATE POLICY {table}_read ON {table} FOR SELECT USING ({predicate(table)})")
        authorized = intake if table == "service_signed_copies" else reviewers
        op.execute(f"CREATE POLICY {table}_insert ON {table} FOR INSERT WITH CHECK "
                   f"({predicate(table, authorized)})")

    name = "service_signed_copies"
    op.execute(f"""CREATE POLICY service_copy_review ON {name} FOR UPDATE
        USING ({predicate(name, reviewers)})
        WITH CHECK ({predicate(name, reviewers)})""")

    op.execute("""DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles
        WHERE rolname = 'immigrationos_app') THEN
        GRANT SELECT, INSERT ON engagement_screens TO immigrationos_app;
        GRANT SELECT, INSERT ON service_agreement_drafts TO immigrationos_app;
        GRANT SELECT, INSERT ON service_signed_copies TO immigrationos_app;
        GRANT UPDATE (scan_status, review_status, review_note, reviewed_by_sub, reviewed_at)
            ON service_signed_copies TO immigrationos_app;
        GRANT SELECT, INSERT ON matter_assignments TO immigrationos_app;
        REVOKE UPDATE, DELETE ON engagement_screens, service_agreement_drafts,
            matter_assignments FROM immigrationos_app;
        END IF; END $$""")


def downgrade():
    for table in ("matter_assignments", "service_signed_copies",
                  "service_agreement_drafts", "engagement_screens"):
        op.drop_table(table)
    op.drop_constraint("uq_case_org_client_id", "cases", type_="unique")
