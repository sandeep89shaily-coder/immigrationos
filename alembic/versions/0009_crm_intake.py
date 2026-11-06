"""RCIC prospect/consultation CRM with case-safe prospect conversion and RLS.

Revision ID: 0009_crm_intake
Revises: 0008_study_intake

Development-only; no email delivery, external payment or electronic signing.
"""
from alembic import op
import sqlalchemy as sa

revision = "0009_crm_intake"
down_revision = "0008_study_intake"
branch_labels = None
depends_on = None


def uuid_col(name, *, pk=False, nullable=False):
    return sa.Column(name, sa.Uuid(), primary_key=pk, nullable=nullable)


def upgrade():
    op.create_table(
        "crm_prospects",
        uuid_col("id", pk=True), uuid_col("org_id"),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("email", sa.String(254)),
        sa.Column("phone", sa.String(40)),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("stage", sa.String(32), nullable=False),
        sa.Column("assigned_to_sub", sa.String(255)),
        sa.Column("outreach_consent", sa.Boolean(), nullable=False),
        sa.Column("consent_source", sa.String(200)),
        uuid_col("converted_client_id", nullable=True),
        sa.Column("created_by_sub", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.UniqueConstraint("org_id", "id", name="uq_crm_prospect_org_id"),
        sa.ForeignKeyConstraint(["org_id", "converted_client_id"], ["clients.org_id", "clients.id"],
                                name="fk_crm_converted_client_tenant"),
        sa.CheckConstraint("stage IN ('new','contacted','consultation_scheduled','consulted','converted','closed')",
                           name="ck_crm_prospect_stage"),
    )
    op.create_index("ix_crm_prospects_org_stage", "crm_prospects", ["org_id", "stage", "created_at"])

    op.create_table(
        "crm_prospect_activities",
        uuid_col("id", pk=True), uuid_col("org_id"), uuid_col("prospect_id"),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("content", sa.String(1200), nullable=False),
        sa.Column("created_by_sub", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["org_id", "prospect_id"], ["crm_prospects.org_id", "crm_prospects.id"],
                                name="fk_crm_activity_prospect"),
        sa.CheckConstraint("kind IN ('call','email','meeting','note')", name="ck_crm_activity_kind"),
    )
    op.create_index("ix_crm_activity_prospect", "crm_prospect_activities",
                    ["org_id", "prospect_id", "created_at"])

    op.create_table(
        "crm_consultations",
        uuid_col("id", pk=True), uuid_col("org_id"), uuid_col("prospect_id"),
        sa.Column("professional_sub", sa.String(255), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_by_sub", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.UniqueConstraint("org_id", "id", name="uq_crm_consultation_org_id"),
        sa.UniqueConstraint("org_id", "prospect_id", "id", name="uq_crm_consultation_prospect_id"),
        sa.ForeignKeyConstraint(["org_id", "prospect_id"], ["crm_prospects.org_id", "crm_prospects.id"],
                                name="fk_crm_consultation_prospect"),
        sa.CheckConstraint("status IN ('scheduled','completed','cancelled')", name="ck_crm_consultation_status"),
    )
    op.create_index("ix_crm_consultations_org_date", "crm_consultations", ["org_id", "starts_at"])

    op.create_table(
        "crm_consultation_agreements",
        uuid_col("id", pk=True), uuid_col("org_id"), uuid_col("prospect_id"),
        uuid_col("consultation_id"),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("terms", sa.JSON(), nullable=False),
        sa.Column("terms_sha256", sa.String(64), nullable=False),
        sa.Column("created_by_sub", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.UniqueConstraint("org_id", "id", name="uq_crm_agreement_org_id"),
        sa.UniqueConstraint("org_id", "prospect_id", "id", name="uq_crm_agreement_prospect_id"),
        sa.ForeignKeyConstraint(["org_id", "prospect_id"], ["crm_prospects.org_id", "crm_prospects.id"],
                                name="fk_crm_agreement_prospect"),
        sa.ForeignKeyConstraint(["org_id", "prospect_id", "consultation_id"],
                                ["crm_consultations.org_id", "crm_consultations.prospect_id",
                                 "crm_consultations.id"], name="fk_crm_agreement_consultation"),
    )
    op.create_index("ix_crm_agreement_consultation", "crm_consultation_agreements",
                    ["org_id", "consultation_id", "created_at"])

    op.create_table(
        "crm_consultation_signed_copies",
        uuid_col("id", pk=True), uuid_col("org_id"), uuid_col("prospect_id"),
        uuid_col("agreement_id"),
        sa.Column("storage_key", sa.String(128), nullable=False, unique=True),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("client_copy_provided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scan_status", sa.String(16), nullable=False),
        sa.Column("review_status", sa.String(16), nullable=False),
        sa.Column("review_note", sa.String(800)),
        sa.Column("reviewed_by_sub", sa.String(255)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("created_by_sub", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.UniqueConstraint("org_id", "agreement_id", name="uq_crm_signed_copy_agreement"),
        sa.ForeignKeyConstraint(["org_id", "prospect_id"], ["crm_prospects.org_id", "crm_prospects.id"],
                                name="fk_crm_signed_copy_prospect"),
        sa.ForeignKeyConstraint(["org_id", "prospect_id", "agreement_id"],
                                ["crm_consultation_agreements.org_id", "crm_consultation_agreements.prospect_id",
                                 "crm_consultation_agreements.id"], name="fk_crm_signed_copy_agreement"),
        sa.CheckConstraint("scan_status IN ('quarantined','cleared','rejected')", name="ck_crm_copy_scan"),
        sa.CheckConstraint("review_status IN ('pending','accepted','rejected')", name="ck_crm_copy_review"),
    )

    if op.get_bind().dialect.name != "postgresql":
        return
    tables = ("crm_prospects", "crm_prospect_activities", "crm_consultations",
              "crm_consultation_agreements", "crm_consultation_signed_copies")
    for table in tables:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

    def predicate(table, roles=None):
        role_filter = "" if roles is None else (" AND m.role IN (" +
                     ",".join("'" + role + "'" for role in roles) + ")")
        return f"""({table}.org_id::text = current_setting('app.tenant_id', true)
            AND EXISTS (SELECT 1 FROM memberships m WHERE m.org_id = {table}.org_id
            AND m.subject = current_setting('app.principal_sub', true)
            AND m.is_active{role_filter}))"""

    staff = ("owner", "admin", "consultant", "assistant")
    reviewer = ("owner", "admin", "consultant")
    for table in tables:
        op.execute(f"CREATE POLICY {table}_read ON {table} FOR SELECT USING ({predicate(table)})")
        insert_roles = reviewer if table == "crm_consultation_agreements" else staff
        op.execute(f"CREATE POLICY {table}_insert ON {table} FOR INSERT WITH CHECK "
                   f"({predicate(table, insert_roles)})")
    for table in ("crm_prospects", "crm_consultations"):
        op.execute(f"CREATE POLICY {table}_update ON {table} FOR UPDATE "
                   f"USING ({predicate(table, staff)}) WITH CHECK ({predicate(table, staff)})")
    table = "crm_consultation_signed_copies"
    op.execute(f"CREATE POLICY {table}_review ON {table} FOR UPDATE "
               f"USING ({predicate(table, reviewer)}) WITH CHECK ({predicate(table, reviewer)})")

    op.execute("""DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles
        WHERE rolname = 'immigrationos_app') THEN
        GRANT SELECT, INSERT, UPDATE ON crm_prospects TO immigrationos_app;
        GRANT SELECT, INSERT ON crm_prospect_activities TO immigrationos_app;
        GRANT SELECT, INSERT, UPDATE ON crm_consultations TO immigrationos_app;
        GRANT SELECT, INSERT ON crm_consultation_agreements TO immigrationos_app;
        GRANT SELECT, INSERT ON crm_consultation_signed_copies TO immigrationos_app;
        GRANT UPDATE (scan_status, review_status, reviewed_by_sub, reviewed_at, review_note)
            ON crm_consultation_signed_copies TO immigrationos_app;
        END IF; END $$""")


def downgrade():
    for table in ("crm_consultation_signed_copies", "crm_consultation_agreements",
                  "crm_consultations", "crm_prospect_activities", "crm_prospects"):
        op.drop_table(table)
