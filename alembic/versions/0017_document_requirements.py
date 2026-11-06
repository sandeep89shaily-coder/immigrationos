"""Reviewed document requirements, case-scoped and append-only.

Revision ID: 0017_document_requirements
Revises: 0016_applicant_histories
"""
from alembic import op
import sqlalchemy as sa

revision = "0017_document_requirements"
down_revision = "0016_applicant_histories"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "requirement_decisions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("requirement_key", sa.String(80), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("decision", sa.String(24), nullable=False),
        sa.Column("reason", sa.String(900), nullable=False),
        sa.Column("source_url", sa.String(500), nullable=False),
        sa.Column("source_template_version", sa.String(100), nullable=False),
        sa.Column("source_observed_on", sa.Date(), nullable=False),
        sa.Column("reviewed_by_sub", sa.String(255), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_id", "case_id"], ["cases.org_id", "cases.id"],
                                name="fk_requirement_decision_case"),
        sa.UniqueConstraint("org_id", "case_id", "requirement_key", "revision",
                            name="uq_requirement_decision_revision"),
        sa.CheckConstraint("decision IN ('required','not_applicable')",
                           name="ck_requirement_decision"),
    )
    op.create_index("ix_requirement_decisions_case", "requirement_decisions",
                    ["org_id", "case_id", "requirement_key"])
    op.create_table(
        "requirement_document_reviews",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("requirement_key", sa.String(80), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("document_sha256", sa.String(64), nullable=False),
        sa.Column("decision", sa.String(16), nullable=False),
        sa.Column("reason", sa.String(900), nullable=False),
        sa.Column("source_template_version", sa.String(100), nullable=False),
        sa.Column("reviewed_by_sub", sa.String(255), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_id", "case_id"], ["cases.org_id", "cases.id"],
                                name="fk_requirement_doc_review_case"),
        sa.ForeignKeyConstraint(["org_id", "case_id", "document_id"],
                                ["case_documents.org_id", "case_documents.case_id", "case_documents.id"],
                                name="fk_requirement_doc_review_same_case"),
        sa.UniqueConstraint("org_id", "case_id", "requirement_key", "document_id",
                            name="uq_requirement_doc_once"),
        sa.CheckConstraint("decision IN ('accepted','rejected')",
                           name="ck_requirement_doc_decision"),
    )
    op.create_index("ix_requirement_doc_reviews_case", "requirement_document_reviews",
                    ["org_id", "case_id", "requirement_key"])
    if op.get_bind().dialect.name != "postgresql":
        return
    for table in ("requirement_decisions", "requirement_document_reviews"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        scope = f"""(org_id::text=current_setting('app.tenant_id',true)
            AND EXISTS (SELECT 1 FROM memberships m
                WHERE m.org_id={table}.org_id
                  AND m.subject=current_setting('app.principal_sub',true)
                  AND m.is_active))"""
        reviewers = f"""EXISTS (SELECT 1 FROM memberships m
            WHERE m.org_id={table}.org_id
              AND m.subject=current_setting('app.principal_sub',true)
              AND m.is_active AND m.role IN ('owner','admin','consultant'))"""
        op.execute(f"CREATE POLICY {table}_read ON {table} FOR SELECT USING ({scope})")
        op.execute(f"""CREATE POLICY {table}_insert ON {table} FOR INSERT
            WITH CHECK ({scope} AND {reviewers}
              AND reviewed_by_sub=current_setting('app.principal_sub',true))""")
    op.execute("""DO $grants$ BEGIN
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='immigrationos_app') THEN
            GRANT SELECT,INSERT ON requirement_decisions TO immigrationos_app;
            GRANT SELECT,INSERT ON requirement_document_reviews TO immigrationos_app;
        END IF;
    END $grants$""")


def downgrade():
    op.drop_index("ix_requirement_doc_reviews_case", table_name="requirement_document_reviews")
    op.drop_table("requirement_document_reviews")
    op.drop_index("ix_requirement_decisions_case", table_name="requirement_decisions")
    op.drop_table("requirement_decisions")
