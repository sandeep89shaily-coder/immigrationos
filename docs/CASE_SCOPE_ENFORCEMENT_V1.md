# ImmigrationOS — Assignment and engagement enforcement v1

**Stage:** Synthetic-data development only. Not certified for real RCIC client records or regulated production operations.

## Security result

Firm membership is no longer sufficient to browse a colleague's case. The shared
\`get_org_access\` dependency now checks the resolved \`case_id\` across the
case workspaces, evidence planning, documents, tasks, reviews, portal-staff
operations, questionnaires and internal form-preflight routes.

### Case permissions

| User in firm | Case read/list | Case write | Notes |
|---|---|---|---|
| Owner/admin | Firm-wide | Role permitting; production requires a current staff-accepted signed engagement | Management/audit access, not independent licence verification |
| Primary assigned consultant | Own assigned matters only | Role permitting; production requires current staff-accepted engagement | Linked through \`matter_assignments\` |
| Assistant with \`read\` grant | Specifically granted matters | Denied | Does not gain professional approval or advice privileges |
| Assistant with \`intake\` grant | Specifically granted matters | Intake-only operations permitted by original route roles; production engagement gate applies | No reviewer signoff |
| Unassigned consultant or assistant | No access | No access | HTTP 404 for an out-of-scope case |
| Firm viewer | No case contents by membership alone | Denied | No implicit confidentiality waiver |

The \`GET /cases\` directory, firm-wide task and issue queues and dashboard case
counts use the same case scope (instead of revealing hidden records). Previously
created unlinked **legacy draft cases** remain visible to managers for
reconciliation, but are not represented as authorized active legal engagements.

In \`ENVIRONMENT=production\`, the former generic
\`POST /api/v1/orgs/{org_id}/cases\` API refuses direct case creation. The
engagement-gated \`POST /engagements/clients/{client_id}/open-matter\` is the
intended path. Updates to an existing case are rejected if its latest
conflict-screen revision or latest service agreement is missing, unreviewed,
superseded, quarantined, or not linked to that case. This is a **conservative
technical gate**, not a legal finding that prior agreements are invalid.

In \`development\` and \`test\`, the legacy draft API remains available for
**fictional demo records only**, preserving reproducible technical tests and
legacy imports. Role-based case scope checks still apply.

### Assistant grants

The new \`case_access_grants\` table is tenant- and case-FK-linked and has
PostgreSQL **FORCE ROW LEVEL SECURITY**.

- \`GET /cases/{case_id}/staff/grants\` — managers/primary consultant see case grants.
- \`POST /cases/{case_id}/staff/grants\` with a known active assistant member
  subject and \`scope=read|intake\` — creates one scoped grant, after checking
  a current reviewed engagement and an open case.
- \`POST /cases/{case_id}/staff/grants/{id}/revoke\` — irrevocably marks a
  grant revoked; a new grant row is required to reinstate access.

Only an active owner/admin or the *primary assigned consultant* can manage
case grants. The database permits UPDATE of **revocation fields only**;
subject, case, scope and original grant metadata cannot be rewritten. A
partial unique index prevents concurrent duplicate live grants.
Offboarding the assistant (deactivating firm membership) removes case
access even if the grant row has not been revoked.

The case overview includes a small assistant-access management dialog,
intended for fictional development identities while staff onboarding is
still being built.

### Client and contract privacy

New \`clients.created_by_sub\` metadata identifies the initiating staff member.
Client list/detail access is limited to:
- firm owner/admin;
- the consultant who created/converted the client, the originating assigned
  prospect consultant, or the professional assigned to a client matter;
- assistants specifically assigned to a case for that client, for
  client-contact access only.

Assistant case grants do **not** expose confidential Code s.24 engagement
terms or full conflict-screen details through \`/engagements/clients/{id}\`.
Unassigned consultants cannot open another client's engagement dossier
merely by knowing the client's UUID. Historic clients with no attributable
creator or case assignment are manager-visible for safe reconciliation.

**Remaining gap:** Firm-level prospect CRM records are not yet individually
assignment-scoped; communication/inbox and client portal grant policies need
a separate full production privacy audit. This release is not an assurance
that every business record has per-client PostgreSQL RLS.

### Membership bootstrap hardening

The old application-role membership policy accepted a self-asserted
\`app.tenant_id\` when inserting a membership. Migration 0012 replaces it with
a narrow, migration-owned SECURITY DEFINER check: the **initial owner**
membership can only be created for the organization created by that
authenticated principal, while it has no prior members.

A separate controlled **staff invitation** workflow will be required to
onboard additional members. For PostgreSQL integration tests, fictional
teammates are provisioned using the isolated, privileged migration connection
and then exercised under the restricted API role.

The **migration role** is marked \`BYPASSRLS\` in the isolated development
PostgreSQL provisioning so the narrowly granted helper functions can
see authorized staff rows despite FORCE RLS. Its credentials must **never**
be present in application/API processes. The runtime \`immigrationos_app\`
role remains non-superuser and has \`rolbypassrls=false\`. This separation
requires an independent database-privilege audit for any real deployment.

### Verification

- Unit tests exercise cross-client agreement denial, case list/task/issue
  isolation, firm viewers, assistant read vs intake, revocation, offboarding,
  primary consultant restrictions, stale engagement gating and legacy drafts.
- A route-inventory test requires \`get_org_access\` on all firm-scoped
  \`{case_id}\` API routes; future endpoints cannot silently omit the shared
  access check without failing CI.
- PostgreSQL integration tests open synthetic reviewed matters with a separate
  professional, provision assistant identities via a migration-only connection,
  grant/revoke under the limited app role, and assert loss of access.
- RLS tests verify FORCE RLS, immutable grants, no app-role bypass and
  rejection of uninvited cross-firm self-enrollment.
- GitHub Actions additionally runs all existing client-portal, form-preflight,
  study-intake, evidence and CRM suites.

## Explicit non-claims and next release gates

This is **API-level assignment scope and organization-level database RLS**.
It does **not** implement per-case RLS on every evidence/task/document table.
It does not verify current CICC registration, electronic signatures, trust
accounting, client data-retention compliance or actual IRCC form submission.
Client portal principals continue to use separate verified-identity
\`PortalGrant\` authorization. They are not staff case grants.

Before any real-client pilot, a dedicated security review must test *every*
record channel (including SQL-access paths, prospect CRM, client portal,
download endpoints, exports and background jobs), establish a controlled
staff-invitation process, document production migrations/secrets, and
verify professional and Canadian privacy compliance.
