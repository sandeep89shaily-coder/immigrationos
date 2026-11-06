"""Require active firm membership for tenant-scoped records.

Revision ID: 0004_member_guard
Revises: 0003_extraction

This makes accidentally switching a database tenant context insufficient to see
another firm's records. It is defense in depth, not a replacement for safe SQL,
verified authentication, or per-request authorization.
"""
from alembic import op

revision = "0004_member_guard"
down_revision = "0003_extraction"
branch_labels = None
depends_on = None

POLICIES = {
    "clients": "clients_tenant_all",
    "cases": "cases_tenant_all",
    "case_documents": "case_documents_tenant_policy",
    "case_facts": "case_facts_tenant_policy",
    "case_issues": "case_issues_tenant_policy",
    "case_tasks": "case_tasks_tenant_policy",
    "fact_suggestions": "fact_suggestions_tenant_policy",
}


def _predicate(table: str) -> str:
    # Qualification is intentional: org_id must belong to the protected row,
    # not the membership subquery.
    return f"""(
        {table}.org_id::text = current_setting('app.tenant_id', true)
        AND EXISTS (
            SELECT 1 FROM memberships AS member
            WHERE member.org_id = {table}.org_id
              AND member.subject = current_setting('app.principal_sub', true)
              AND member.is_active = true
        )
    )"""


def upgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    for table, policy in POLICIES.items():
        op.execute(f"DROP POLICY {policy} ON {table}")
        predicate = _predicate(table)
        op.execute(f"CREATE POLICY {policy} ON {table} FOR ALL USING ({predicate}) WITH CHECK ({predicate})")

    op.execute("DROP POLICY audit_select ON audit_events")
    op.execute("DROP POLICY audit_insert ON audit_events")
    audit_condition = _predicate("audit_events")
    op.execute(f"CREATE POLICY audit_select ON audit_events FOR SELECT USING ({audit_condition})")
    op.execute(f"CREATE POLICY audit_insert ON audit_events FOR INSERT WITH CHECK ({audit_condition})")


def downgrade():
    if op.get_bind().dialect.name != "postgresql":
        return
    for table, policy in POLICIES.items():
        op.execute(f"DROP POLICY {policy} ON {table}")
        predicate = f"{table}.org_id::text = current_setting('app.tenant_id', true)"
        op.execute(f"CREATE POLICY {policy} ON {table} FOR ALL USING ({predicate}) WITH CHECK ({predicate})")
    op.execute("DROP POLICY audit_select ON audit_events")
    op.execute("DROP POLICY audit_insert ON audit_events")
    predicate = "audit_events.org_id::text = current_setting('app.tenant_id', true)"
    op.execute(f"CREATE POLICY audit_select ON audit_events FOR SELECT USING ({predicate})")
    op.execute(f"CREATE POLICY audit_insert ON audit_events FOR INSERT WITH CHECK ({predicate})")
