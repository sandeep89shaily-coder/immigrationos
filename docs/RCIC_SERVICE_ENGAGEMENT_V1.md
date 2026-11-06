# ImmigrationOS — RCIC service engagement + supervised matter opening

**Status:** Development/synthetic records only. No certified client engagement, independent RCIC licence verification, cryptographically verified signatures, legal advice or IRCC submission integration.

## Regulatory baseline and constraints

Verified against official Department of Justice Canada pages on 2026-11-06:

- [Code s.15, conflicts of interest](https://laws-lois.justice.gc.ca/eng/regulations/SOR-2022-128/section-15.html): conflicts may be subject to strict disclosure, informed written consent and professional limitations. Some conflicts are prohibited under ss.16–18. This prototype **always blocks** potential, prohibited, concurrent or unresolved matters; it does not purport to adjudicate permissible informed-consent exceptions.
- [Code s.24, service agreement](https://laws-lois.justice.gc.ca/eng/regulations/SOR-2022-128/section-24.html): written agreement before consulting or, after an initial consultation, before further services; verify client's personal/business contact and previous representation; give a draft, cover specific clauses (a–z), keep signed copy and give client a copy; written amendments must be agreed to by both parties.
- [Code s.25, narrow non-application](https://laws-lois.justice.gc.ca/eng/regulations/SOR-2022-128/section-25.html): some institution-employed licensees may qualify for limited exceptions. This application **does not** implement exemption adjudication.

**Professional review is mandatory.** The a–z drafting editor is an **information-completeness checklist** to be completed by the RCIC. It does not insert unverified regulatory boilerplate, certify legal sufficiency, confirm licence status, verify conflict disclosures or create a valid e-signature.

## New workflow in consultant workspace

Open **Clients** and select a fictional client record:

1. **Conflict and previous-representative screen.** Staff with owner/admin/consultant roles record identity verification, prior representation arrangement, conflict status, rationale and independent review attestation. The record is immutable. Only a reviewed status with no identified conflict and no current concurrent representative can pass the conservative development gate.
2. **Written service agreement draft.** A fresh screen is required. All **26 headings** corresponding to Code s.24(3)(a)–(z) require explicit client-specific entries. Draft terms become immutable versions with a SHA-256 checksum, preserving old versions and amendments.
3. **Print draft and arrange signatures.** The printable escaped HTML has large warnings. Actual legal language, signature collection and delivery happen outside the application. Users record the time the client received the draft, the signature time, and the time a signed copy was provided.
4. **Upload a signed PDF (fictional data only).** Files are encrypted in the local development storage. The isolate-only ClamAV adapter clears or rejects bytes; otherwise they remain **quarantined**, never treated as clean. The full signing/delivery sequence is checked.
5. **Review signed evidence.** An authorized staff reviewer downloads only a scan-cleared file, inspects it independently, and records an accept/reject attestation with a substantive rationale. No server-side claim of signature authentication or licence verification is made.
6. **Open a supervised matter.** The active owner/admin/consultant reviewer selects an immigration program and an active firm owner/admin/consultant as assigned professional. The case is created in **draft** status with durable links to one client, the current screened record and the accepted latest agreement version.
7. **Change invalidation.** A newer conflicted/unresolved screen or newer unsigned service agreement blocks subsequent matter openings. Earlier accepted document versions remain historic. Written amendments still need real bilateral signatures and professional assessment.

> **Important scope:** Existing generic \`POST /api/v1/orgs/{org_id}/cases\` remains for legacy demo draft cases. It is **not** restricted by this new engagement gate, and generic case access is still firm-wide rather than case-assignment-limited. We must not claim all client work is now engagement-gated. The next architecture slice must enforce assignment and service authority consistently before any production trial.

## Core API

Within \`/api/v1/orgs/{org_id}/engagements\`:

| Method | Endpoint | Purpose |
|---|---|---|
| GET | \`/s24/clauses\` | Clause labels and official source |
| GET | \`/clients/{client_id}\` | Current screen, latest draft, signed review and readiness |
| POST | \`/clients/{client_id}/screens\` | Append immutable professional conflict screen |
| POST | \`/clients/{client_id}/drafts\` | Store all 26 client-specific sections with checksum |
| GET | \`/clients/{client_id}/drafts/{draft_id}/print\` | Escaped printable **unsigned** HTML |
| POST | \`/clients/{client_id}/drafts/{draft_id}/signed-copy\` | Scan/quarantine encrypted signed PDF and delivery timestamps |
| POST | \`/clients/{client_id}/drafts/{draft_id}/scan\` | Rescan pending quarantine only |
| GET | \`/clients/{client_id}/drafts/{draft_id}/signed-copy\` | Download cleared PDF for human review |
| POST | \`/clients/{client_id}/drafts/{draft_id}/review\` | Human review and rationale |
| POST | \`/clients/{client_id}/open-matter\` | Only when current signed agreement accepted and staff role active |
| GET | \`/clients/{client_id}/matters\` | Engagement-linked assigned cases |

## Security/quality invariants

- Four new tables, all with \`FORCE ROW LEVEL SECURITY\` and active tenant membership checks.
- Composite FKs prevent other firms' clients, another client's conflict screen or another client's agreement from being attached.
- Additional case \`(org_id, client_id, id)\` unique constraint prevents case-client mismatch even when the case ID is known.
- Conflict screens, agreement versions and matter assignments are append-only under the limited PostgreSQL runtime role.
- Signed PDF sha256, storage locator and client ID cannot be updated by runtime role; only scanner/reviewer disposition columns.
- Signed records cannot be accepted while quarantined or when prior representation/conflict evidence becomes stale.
- Draft-delivery, signing and client-copy timestamps are validated (timezones required, chronological order, not future-dated beyond a few minutes).
- SHA-256 is evidence of byte identity, **not proof of authenticity, signed consent or current legal validity**.
- No confidential agreement text or client contacts are copied into global metadata audit events.

## Acceptance

- Synthetic FastAPI end-to-end unit tests cover blocked conflicts, all 26 clauses, unsigned signoff, signed scan-review gates, immutable versions, stale screens, assigned matter creation, cross-tenant queries and composite FK violations.
- \`scripts/postgres_engagement_smoke.py\` tests the same main workflow with two fictional firms under the **limited PostgreSQL runtime role**. Its scanner is explicitly **simulated for dummy bytes**; a real ClamAV instance is not claimed to have scanned the fixture.
- \`scripts/verify_rls.py\` checks \`FORCE RLS\` on the four new tables and revoked UPDATE/DELETE permissions on immutable records and signed-copy hashes.
- \`.github/workflows/ci.yml\` executes Python/JavaScript checks and PostgreSQL migration, API and RLS smoke.
- Real browser tests in Windows/Keycloak and legal review of actual agreement language remain future acceptance gates.

## Next implementation slices

1. Enforce engagement-based **case authorization**, versioned assignments, supervised staff invitations/role verification and clear isolation for active-client records (not just new matter creation).
2. Legal deadline source and escalation policies, program-specific milestones, and a unified client communication timeline.
3. Proper s.24 amendment co-signing workflow, historical agreement exports, audit-ready file closure.
4. Fee invoicing and **real double-entry trust subledgers** reviewed by an RCIC and accountant before external payment integrations.
5. Official IRCC form factory remains a parallel core workstream. Validated form count is still **zero** until actual Adobe/IRCC workflow tests pass.


## Historical versions and case-level staleness (next increment)

The product now exposes **immutable professional decision history** and a
case-specific comparison to the latest service agreement and conflict screen:

- \`GET /api/v1/orgs/{org_id}/engagements/clients/{client_id}/history\` lists
  recent professional screens and service agreement versions, their checksums,
  signed-copy scan/review state, and which versions have been superseded.
  Detailed history access requires owner/admin/consultant roles.
- \`GET /api/v1/orgs/{org_id}/engagements/cases/{case_id}\` shows the signed
  agreement revision actually linked when the case was opened, assigned staff
  professional and whether the current latest screen/draft still matches.
  This status is visible to firm members, consistent with the current
  firm-wide case access scope.

A new unsigned draft or updated conflict review flags **professional
reconciliation required** on existing assigned matters rather than silently
treating the original agreement as current. It does **not** declare that the
old legal agreement ceased to exist or that any amendment is legally binding.

Older cases made through the legacy direct case-create route are labelled
**unlinked/legacy draft**: the software does not imply their engagement was
approved. The consultant's Clients engagement page has a revision-history
view; the case overview shows current/unlinked/stale engagement status.

This remains an **advisory signal, not an authorization engine**. Existing
non-engagement-gated routes and firm-wide case read permissions are still
supported for synthetic development; production work requires separate
case assignment-scoped authorization and s.24 professional legal review.
