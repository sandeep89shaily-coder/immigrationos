"""Adversarial, transaction-rollback tests against a real PostgreSQL app role.

Run after Alembic migrations with RLS_APP_DATABASE_URL set to the LIMITED
immigrationos_app role. This script deliberately uses synthetic records only.
"""
import os
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

url = os.environ.get("RLS_APP_DATABASE_URL")
if not url or not url.startswith(("postgresql+psycopg://", "postgresql://")):
    raise SystemExit("Set RLS_APP_DATABASE_URL to a PostgreSQL immigrationos_app URL")

engine = create_engine(url)

def context(conn, principal, tenant):
    conn.execute(text("SELECT set_config('app.principal_sub', :p, true)"), {"p": principal})
    conn.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant)})

def count(conn, table):
    return conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one()

with engine.connect() as conn:
    transaction = conn.begin()
    try:
        role = conn.execute(text("SELECT current_user, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")).one()
        assert role[0] == "immigrationos_app", "RLS test must use the limited application role"
        assert not role[1] and not role[2], "Application role bypasses RLS"
        context(conn, "", "")
        assert count(conn, "clients") == 0, "RLS exposed clients without identity context"

        tenant_a, tenant_b = uuid4(), uuid4()
        client_a, client_b = uuid4(), uuid4()
        case_a, case_b = uuid4(), uuid4()
        principal_a, principal_b = f"rls-a-{uuid4()}", f"rls-b-{uuid4()}"
        now = "2026-01-01T00:00:00Z"

        for org, client, case, principal, label in [
            (tenant_a, client_a, case_a, principal_a, "A"),
            (tenant_b, client_b, case_b, principal_b, "B"),
        ]:
            context(conn, principal, org)
            conn.execute(text("""INSERT INTO organizations (id, slug, name, created_by_sub, created_at)
                VALUES (:id, :slug, :name, :principal, :now)"""),
                {"id": org, "slug": f"rls-{str(org)}", "name": f"Synthetic {label}", "principal": principal, "now": now})
            conn.execute(text("""INSERT INTO memberships (id, org_id, subject, role, is_active, created_at)
                VALUES (:id, :org, :principal, 'owner', true, :now)"""),
                {"id": uuid4(), "org": org, "principal": principal, "now": now})
            conn.execute(text("""INSERT INTO clients (id, org_id, first_name, last_name, created_at, updated_at)
                VALUES (:id, :org, :name, 'Test', :now, :now)"""),
                {"id": client, "org": org, "name": f"Synthetic {label}", "now": now})
            conn.execute(text("""INSERT INTO cases (id, org_id, client_id, application_type, title, status, created_at, updated_at)
                VALUES (:id, :org, :client, 'study_permit', 'Synthetic application', 'draft', :now, :now)"""),
                {"id": case, "org": org, "client": client, "now": now})

        context(conn, principal_a, tenant_a)
        assert count(conn, "clients") == 1 and count(conn, "cases") == 1
        assert conn.execute(text("SELECT id FROM clients")).scalar_one() == client_a
        context(conn, principal_b, tenant_b)
        assert count(conn, "clients") == 1 and count(conn, "cases") == 1
        assert conn.execute(text("SELECT id FROM clients")).scalar_one() == client_b

        # Switching tenant_id alone must not grant access if the principal is not a member.
        context(conn, principal_a, tenant_b)
        assert count(conn, "clients") == 0 and count(conn, "cases") == 0, \
            "RLS FAILED: changing tenant context exposed another firm's data"
        with conn.begin_nested() as savepoint:
            try:
                conn.execute(text("""INSERT INTO clients (id, org_id, first_name, last_name, created_at, updated_at)
                    VALUES (:id, :org, 'Injected', 'Client', :now, :now)"""),
                    {"id": uuid4(), "org": tenant_b, "now": now})
            except SQLAlchemyError:
                savepoint.rollback()
            else:
                savepoint.rollback()
                raise AssertionError("RLS FAILED: non-member could insert client into another firm")

        tenant_tables = ["clients", "cases", "audit_events", "case_documents", "case_facts",
                         "case_issues", "case_tasks", "fact_suggestions", "evidence_review_snapshots",
                         "crm_prospects", "crm_prospect_activities", "crm_consultations",
                         "crm_consultation_agreements", "crm_consultation_signed_copies", "crm_followups",
                         "engagement_screens", "service_agreement_drafts",
                         "service_signed_copies", "matter_assignments"]
        policies = conn.execute(text("""SELECT relname, relrowsecurity, relforcerowsecurity
            FROM pg_class WHERE relname = ANY(:tables)"""), {"tables": tenant_tables}).all()
        assert len(policies) == len(tenant_tables), "RLS FAILED: missing tables"
        assert all(enabled and force for _, enabled, force in policies), "RLS FAILED: FORCE RLS missing"
        privileges = conn.execute(text("""SELECT has_table_privilege(current_user, 'audit_events', 'UPDATE'),
            has_table_privilege(current_user, 'audit_events', 'DELETE')""")).one()
        assert privileges == (False, False), "RLS FAILED: audit history is mutable"

        snapshot_privileges = conn.execute(text("""SELECT
            has_table_privilege(current_user, 'evidence_review_snapshots', 'SELECT'),
            has_table_privilege(current_user, 'evidence_review_snapshots', 'INSERT'),
            has_table_privilege(current_user, 'evidence_review_snapshots', 'UPDATE'),
            has_table_privilege(current_user, 'evidence_review_snapshots', 'DELETE')""")).one()
        assert snapshot_privileges == (True, True, False, False), \
            "RLS FAILED: review history must be append-only"

        crm_privileges = conn.execute(text("""SELECT
            has_table_privilege(current_user, 'crm_consultation_agreements', 'UPDATE'),
            has_table_privilege(current_user, 'crm_consultation_agreements', 'DELETE'),
            has_table_privilege(current_user, 'crm_prospect_activities', 'UPDATE'),
            has_table_privilege(current_user, 'crm_prospect_activities', 'DELETE'),
            has_column_privilege(current_user, 'crm_consultation_signed_copies', 'review_status', 'UPDATE'),
            has_column_privilege(current_user, 'crm_consultation_signed_copies', 'sha256', 'UPDATE')
        """)).one()
        assert crm_privileges == (False, False, False, False, True, False), \
            "RLS FAILED: CRM immutable terms/activity or signed-copy hash is mutable"

        crm_followup_privileges = conn.execute(text("""SELECT
            has_table_privilege(current_user, 'crm_followups', 'DELETE'),
            has_column_privilege(current_user, 'crm_followups', 'due_at', 'UPDATE'),
            has_column_privilege(current_user, 'crm_followups', 'assigned_to_sub', 'UPDATE'),
            has_column_privilege(current_user, 'crm_followups', 'status', 'UPDATE')""")).one()
        assert crm_followup_privileges == (False, False, False, True), \
            "RLS FAILED: follow-up due dates or assignees can be altered"

        engagement_privileges = conn.execute(text("""SELECT
            has_table_privilege(current_user, 'engagement_screens', 'UPDATE'),
            has_table_privilege(current_user, 'engagement_screens', 'DELETE'),
            has_table_privilege(current_user, 'service_agreement_drafts', 'UPDATE'),
            has_table_privilege(current_user, 'service_agreement_drafts', 'DELETE'),
            has_table_privilege(current_user, 'matter_assignments', 'UPDATE'),
            has_table_privilege(current_user, 'matter_assignments', 'DELETE'),
            has_column_privilege(current_user, 'service_signed_copies', 'sha256', 'UPDATE'),
            has_column_privilege(current_user, 'service_signed_copies', 'draft_id', 'UPDATE'),
            has_column_privilege(current_user, 'service_signed_copies', 'review_status', 'UPDATE')
        """)).one()
        assert engagement_privileges == (
            False, False, False, False, False, False, False, False, True
        ), "RLS FAILED: signed agreement or immutable professional record could be overwritten"




        # Positive control: a member can record a review for their own firm's case.
        context(conn, principal_a, tenant_a)
        conn.execute(text("""INSERT INTO evidence_review_snapshots (
            id, org_id, case_id, filing_context, template_version, case_sha256,
            reviewer_sub, review_note, open_issues_at_review, created_at)
            VALUES (:id, :org, :case, 'outside_canada', 'synthetic-test', :hash,
                    :reviewer, 'Synthetic reviewer note only', 0, :now)"""),
            {'id': uuid4(), 'org': tenant_a, 'case': case_a, 'hash': '0'*64,
             'reviewer': principal_a, 'now': now})
        assert count(conn, 'evidence_review_snapshots') == 1
        context(conn, principal_a, tenant_b)
        assert count(conn, 'evidence_review_snapshots') == 0, \
            "RLS FAILED: review history leaked across firms"

    finally:
        transaction.rollback()
engine.dispose()
print("PASS: PostgreSQL limited-role, active-membership RLS and write-isolation checks")
