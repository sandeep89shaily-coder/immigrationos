"""Case application packages and immutable per-upload form evidence.

Revision ID: 0014_application_package
Revises: 0013_verified_staff_invites
"""
from alembic import op
import sqlalchemy as sa

revision = "0014_application_package"
down_revision = "0013_verified_staff_invites"
branch_labels = None
depends_on = None


def upgrade():
    # A triple FK ensures a PDF from a different case in the same firm cannot
    # be falsely presented as an application form for this matter.
    op.create_unique_constraint("uq_doc_org_case_id", "case_documents",
                                ["org_id", "case_id", "id"])
    op.create_table(
        "case_application_packages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("application_type", sa.String(80), nullable=False),
        sa.Column("filing_context", sa.String(32), nullable=False),
        sa.Column("include_representative_form", sa.Boolean(), nullable=False),
        sa.Column("profile_version", sa.String(80), nullable=False),
        sa.Column("created_by_sub", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("org_id", "case_id", name="uq_application_package_case"),
        sa.UniqueConstraint("org_id", "case_id", "id", name="uq_application_package_case_id"),
        sa.ForeignKeyConstraint(["org_id", "case_id"], ["cases.org_id", "cases.id"],
                                name="fk_application_package_case"),
        sa.CheckConstraint("filing_context IN ('inside_canada','outside_canada')",
                           name="ck_application_package_context"),
        sa.CheckConstraint("application_type = 'study_permit'",
                           name="ck_application_package_type_v1"),
    )
    op.create_table(
        "package_form_copies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("package_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("form_code", sa.String(20), nullable=False),
        sa.Column("source_revision", sa.String(120), nullable=False),
        sa.Column("source_observed_on", sa.Date(), nullable=False),
        sa.Column("linked_document_sha256", sa.String(64), nullable=False),
        sa.Column("scan_status", sa.String(16), nullable=False),
        sa.Column("review_status", sa.String(16), nullable=False),
        sa.Column("review_note", sa.String(900)),
        sa.Column("reviewed_by_sub", sa.String(255)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("created_by_sub", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_id", "case_id", "package_id"],
                                ["case_application_packages.org_id",
                                 "case_application_packages.case_id",
                                 "case_application_packages.id"],
                                name="fk_package_form_package_case"),
        sa.ForeignKeyConstraint(["org_id", "case_id", "document_id"],
                                ["case_documents.org_id", "case_documents.case_id",
                                 "case_documents.id"], name="fk_package_form_doc_same_case"),
        sa.UniqueConstraint("org_id", "case_id", "document_id",
                            name="uq_package_form_document_once"),
        sa.CheckConstraint("scan_status IN ('cleared','quarantined','rejected')",
                           name="ck_package_form_scan"),
        sa.CheckConstraint("review_status IN ('pending','accepted','rejected')",
                           name="ck_package_form_review"),
    )
    op.create_index("ix_package_form_copies_latest", "package_form_copies",
                    ["org_id", "case_id", "form_code", "created_at"])
    if op.get_bind().dialect.name != "postgresql":
        return

    for table in ("case_application_packages", "package_form_copies"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        base = f"""({table}.org_id::text = current_setting('app.tenant_id',true)
             AND EXISTS (SELECT 1 FROM memberships m
             WHERE m.org_id={table}.org_id
               AND m.subject=current_setting('app.principal_sub',true)
               AND m.is_active))"""
        op.execute(f"CREATE POLICY {table}_read ON {table} FOR SELECT USING ({base})")
        write_roles = ("owner","admin","consultant") if table == "case_application_packages" else (
            "owner","admin","consultant","assistant")
        role_sql = ", ".join("'" + x + "'" for x in write_roles)
        op.execute(f"""CREATE POLICY {table}_insert ON {table} FOR INSERT WITH CHECK (
            {base}
            AND created_by_sub=current_setting('app.principal_sub',true)
            AND EXISTS(SELECT 1 FROM memberships m
                WHERE m.org_id={table}.org_id
                  AND m.subject=current_setting('app.principal_sub',true)
                  AND m.is_active AND m.role IN ({role_sql}))
        )""")
    op.execute("""CREATE POLICY package_form_review ON package_form_copies
        FOR UPDATE USING (
            org_id::text=current_setting('app.tenant_id',true)
            AND review_status='pending'
            AND EXISTS(SELECT 1 FROM memberships m
                WHERE m.org_id=package_form_copies.org_id
                  AND m.subject=current_setting('app.principal_sub',true)
                  AND m.is_active AND m.role IN ('owner','admin','consultant')))
        WITH CHECK (
            org_id::text=current_setting('app.tenant_id',true)
            AND EXISTS(SELECT 1 FROM memberships m
                WHERE m.org_id=package_form_copies.org_id
                  AND m.subject=current_setting('app.principal_sub',true)
                  AND m.is_active AND m.role IN ('owner','admin','consultant')))
    """)
    op.execute("""DO $grants$ BEGIN
       IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='immigrationos_app') THEN
          GRANT SELECT,INSERT ON case_application_packages TO immigrationos_app;
          GRANT SELECT,INSERT ON package_form_copies TO immigrationos_app;
          GRANT UPDATE(scan_status,review_status,review_note,reviewed_by_sub,reviewed_at)
            ON package_form_copies TO immigrationos_app;
       END IF;
    END $grants$""")


def downgrade():
    op.drop_index("ix_package_form_copies_latest", table_name="package_form_copies")
    op.drop_table("package_form_copies")
    op.drop_table("case_application_packages")
    op.drop_constraint("uq_doc_org_case_id", "case_documents", type_="unique")
