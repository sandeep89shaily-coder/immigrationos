# ImmigrationOS — Foundation Architecture Decision Record

**ADR-001 | Status: accepted for development | Version: 0.2**

## Goal

Build a Canadian immigration-practice operating system using a single canonical immigration case/evidence domain, AI services with verifiable provenance, and deterministic rules/form generation. The current foundation is deliberately narrower: firm isolation, identity integration, cases and immutable event metadata.

## Architectural choices

1. **Modular monolith** (FastAPI + PostgreSQL): shared transaction boundaries simplify correctness. Extract specialized workers only for document processing, policy monitoring and ML inference after contracts stabilize.
2. **Managed identity/OIDC**: JWT signature, audience, issuer and expiration verified. Keycloak is a local, disposable identity emulator, not the recommended production credential store.
3. **Defense-in-depth tenancy**: organization id in all tenant records; membership checks in API; PostgreSQL FORCE RLS policies; composite foreign key to prevent a case linking to an unrelated firm's client; separate restricted runtime DB role.
4. **Immutable case history**: auditable state-transition events, no document payloads in audit. Production will add cryptographic event-chain integrity, secure retention and export controls.
5. **Human approval boundary**: planned AI workers produce evidence candidates and findings, not automatic legal decisions, form submission or financial transactions.
6. **Explicit migrations**: Alembic is the only production path for schema changes. `Base.metadata.create_all()` is restricted to fast SQLite tests.

## Authorization matrix (v0.2)

| Role | Read own-firm clients/cases | Create clients/cases | Change case status | View audit |
| --- | --- | --- | --- | --- |
| owner | Yes | Yes | Yes | Yes |
| admin | Yes | Yes | Yes | Yes |
| consultant | Yes | Yes | Yes | No |
| assistant | Yes | No | No | No |
| viewer | Yes | No | No | No |

These roles are intentionally conservative until supervised workflows, invitations, access requests and delegated case permissions exist.

## Essential invariants

- No organization endpoint returns data for an unaffiliated principal. The response does not reveal whether the target organization exists.
- `cases.(org_id, client_id)` is a composite foreign key to `clients.(org_id, id)`, preventing cross-firm case-client associations at the database level.
- All tenant API sessions set `app.tenant_id` and `app.principal_sub` **inside the active database transaction** before protected queries.
- A committed transaction discards RLS context; every new transaction must reinitialize it. Code must not refresh ORM entities after commit without an explicit new context.
- Business data cannot be deleted by the runtime role. Audit events cannot be updated or deleted even by normal table owners; the migration role is separated from the app role.
- Database migrations must be run as the migration role. Do not use PostgreSQL `postgres`/superuser as the runtime API identity.
- No AI assistant is allowed to issue SQL or perform access control decisions autonomously.

## Roadmap data model additions

Next: UserInvitations, FirmBranches, MatterAssignments, ClientHouseholds, CaseParticipant, Document, DocumentVersion, DocumentFact, FactSource, EvidenceConflict, SourceCatalog, ReviewedRuleVersion, FormVersion, FormFieldMapping, FormGeneration, Approval, and AIJob. Each tenant-scoped entity must receive an authorization/RLS review and negative isolation tests before merge.

## Future API contracts

- `POST /api/v1/orgs/{org_id}/invitations` — admin-verified invite to staff, accepted through IdP authorization flow, never by arbitrary subject assignment.
- `POST /api/v1/orgs/{org_id}/cases/{case_id}/document-requests` — checklist requirements based on reviewed program-specific templates.
- `POST /api/v1/orgs/{org_id}/documents/initiate` — short-lived, malware-scanned upload workflow; files never pass directly to an LLM.
- `POST /api/v1/orgs/{org_id}/ai/extract` — explicit, audited, queued candidate extraction; no verified fact mutation.
- `POST /api/v1/orgs/{org_id}/facts/{id}/approve` — licensed representative or appropriately delegated reviewer; preserves source and approval signature.
- `POST /api/v1/orgs/{org_id}/forms/generate` — reviewed verified facts, correct published IRCC form version, deterministic mapping and validity checks.

## Non-goals of v0.2

- Production compliance certification; production MFA/SSO configuration; full document security; legal advice; real IRCC integration; trust accounting; automatic eligibility assessments; scraping private government portals; actual AI. These are NOT implemented or claimed.
