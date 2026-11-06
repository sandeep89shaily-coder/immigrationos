"""Real PostgreSQL tenant-RLS negative tests (run after local migrations)."""
import os
from uuid import uuid4

from sqlalchemy import create_engine, text

# Must use LIMITED APPLICATION ROLE, not the migration role or PostgreSQL superuser.
url = os.environ.get("RLS_APP_DATABASE_URL")
if not url:
    raise SystemExit("Set RLS_APP_DATABASE_URL to the immigrationos_app connection URL")
engine = create_engine(url)
t1, t2 = uuid4(), uuid4()
with engine.connect() as conn:
    # Without any context, tenant-scoped tables must expose no rows.
    result = conn.execute(text("SELECT count(*) FROM clients")).scalar_one()
    assert result == 0, "RLS FAILED: clients exposed without tenant context"
    # With an unrelated tenant context, rows are filtered by tenant_id.
    conn.execute(text("SELECT set_config('app.tenant_id', :tenant, true)"), {"tenant": str(t1)})
    result = conn.execute(text("SELECT count(*) FROM clients WHERE org_id = :id"), {"id": t2}).scalar_one()
    assert result == 0, "RLS FAILED: cross-tenant client rows exposed"
    # The evidence domain must enforce FORCE ROW LEVEL SECURITY on every table.
    tenant_tables = ['clients','cases','audit_events','case_documents','case_facts',
                     'case_issues','case_tasks','fact_suggestions']
    policies = conn.execute(text("""SELECT relname, relrowsecurity, relforcerowsecurity
       FROM pg_class WHERE relname = ANY(:tables)"""), {'tables': tenant_tables}).all()
    assert len(policies) == len(tenant_tables), 'RLS FAILED: missing evidence tables'
    assert all(enabled and force for _, enabled, force in policies), 'RLS FAILED: RLS not forced'
    for table in tenant_tables:
        assert conn.execute(text(f"SELECT count(*) FROM {table} WHERE org_id = :tid"),
                            {'tid': t2}).scalar_one() == 0, f'RLS FAILED: cross tenant rows in {table}'
    # No UPDATE or DELETE privileges on immutable audit history.
    privileges = conn.execute(text("""SELECT has_table_privilege(current_user, 'audit_events', 'UPDATE'),
        has_table_privilege(current_user, 'audit_events', 'DELETE')""")).one()
    assert privileges == (False, False), "RLS FAILED: audit history writable"
    conn.rollback()
print("PASS: database role and baseline RLS checks")
