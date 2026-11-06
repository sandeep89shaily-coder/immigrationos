# RCIC CRM v1 — Prospect → Consultation → Client

**Release stage:** Synthetic/development only. Not a certified CICC practice tool, electronic-signature platform, or production document store.

## What actually works

A firm's consultant uses the **Prospects** section of the development workspace at \`/app\`:

1. Create a prospect, with source and optional documented outreach-consent source. An existing open prospect with the same email is **flagged** rather than silently merged.
2. Record calls, emails and internal notes in an append-only prospect activity list. Recording an email **does not send it**.
3. Schedule a timezone-aware consultation assigned to the currently authenticated consulting professional. Appointments are not advertised as sent calendar invites.
4. Create an **immutable consultation agreement terms version** for the scheduled consultation. The draft records the proposed licensee name, licence number, full contact details, client contact details, consultation fee or pro bono status, description of CICC's regulatory role, purpose and scope. The 64-character content digest changes when terms change. This is **NOT** an approved legal template.
5. Download a printable, safely escaped HTML **draft** with signature lines and warnings. Arrange signing/delivery separately.
6. Upload a synthetic signed PDF and record signing and client-copy delivery timestamps. The encrypted development blob is always treated as untrusted; ClamAV scanning clears or rejects it when available, otherwise it stays **quarantined**. The PDF is NOT automatically considered authentic.
7. Authorized staff download a **scan-cleared** signed PDF and manually record acceptance/rejection with a written rationale. A pending/quarantined copy cannot be accepted. Repeated review is blocked.
8. Mark the consultation complete **only** if the latest version has a cleared and accepted signed PDF.
9. Convert the prospect to a client, preserving the immutable prospect events and agreement link. Retrying conversion returns the same client identifier. Potential duplicate clients are blocked for manual reconciliation.
10. The client now appears in the existing case-management directory. **A separately signed service agreement and conflict checks are still required before further consulting services.** This conversion does not create a retainer, charge funds, confer RCIC authorization or submit an IRCC application.

## Regulatory rationale and important caveats

Official source: [SOR/2022-128 Code, s.23](https://laws-lois.justice.gc.ca/eng/regulations/SOR-2022-128/section-23.html).

For initial immigration/citizenship consulting consultations, Code s.23 generally requires a **written consultation agreement before the consultation**, with licensee name/registration/address/telephone/email, prospective client's details, fee or pro bono statement, CICC regulator description and scope. Keep signed copy and provide copy to client.

Code [s.24](https://laws-lois.justice.gc.ca/eng/regulations/SOR-2022-128/section-24.html) separately governs written service agreements before subsequent consulting work. Exemptions can apply under [s.25](https://laws-lois.justice.gc.ca/eng/regulations/SOR-2022-128/section-25.html) in limited scenarios. This module does not adjudicate exemptions.

**No automatic legal claim:** The product cannot independently confirm that the entered consultant is an actively licensed RCIC, that a client actually received or signed an agreement, that the contract is legally valid, that the scheduled meeting occurred, or that the uploaded document is genuine. Review is staff attestation. This milestone does not create a signing integration or an email/scheduling integration.

The "completed" operation records a staff-controlled CRM state, NOT a government or regulator verification. Do not use real client information.

## API overview

All endpoints are within a firm:
\`/api/v1/orgs/{org_id}/crm\`

| Operation | Endpoint |
|---|---|
| List/create prospects | GET/POST \`/prospects\` |
| Prospect details | GET \`/prospects/{prospect_id}\` |
| Append/read interactions | POST/GET \`/prospects/{prospect_id}/activities\` |
| Schedule/list consultations | POST/GET \`/prospects/{prospect_id}/consultations\` |
| Cancel appointment | POST \`/prospects/{prospect_id}/consultations/{consultation_id}/cancel\` |
| Prepare/list versioned agreement terms | POST/GET \`/.../agreements\` |
| Download printable draft terms | GET \`/.../agreements/{agreement_id}/draft\` |
| Upload signed PDF | POST \`/.../agreements/{agreement_id}/signed-copy\` |
| Scan a quarantined signed PDF | POST \`/.../agreements/{agreement_id}/scan\` |
| Download a cleared signed PDF | GET \`/.../agreements/{agreement_id}/signed-copy\` |
| Review signed evidence | POST \`/.../agreements/{agreement_id}/review\` |
| Complete consultation | POST \`/.../consultations/{consultation_id}/complete\` |
| Convert client | POST \`/prospects/{prospect_id}/convert\` |

\`...\` in the agreement endpoints represents
\`/prospects/{prospect_id}/consultations/{consultation_id}\`.

**Access control:** Tenant membership is checked by the API and PostgreSQL FORCE RLS on all five new tables. Firm viewers may read but cannot write. Staff can add prospects and activities. Owner/admin/consultant roles alone can schedule consultations, create terms, review signed evidence, complete appointments or convert clients. The DB application role has no UPDATE/DELETE grant on immutable agreement terms or activity events and no DELETE on CRM business records.

**No unsigned bypass:** The complete endpoint requires the current consultation's latest written terms AND its reviewed, scan-cleared signed PDF. Any actual services performed before those steps are a human compliance issue: the software cannot retroactively prevent a meeting taking place outside the app.

## Deliberately not in v1

- Production signature authentication, identity proofing and trusted e-sign service.
- Direct delivery of consultation agreements to clients and proof of receipt.
- Automatic booking/calendar sync, appointment reminders and no-show handling.
- Prior-representation/conflict checks, s.24 service retainer creation and approval.
- Payment collection, fee invoices, client trust accounting and bank reconciliation.
- Multi-office assignments, delegated case-level permissions and production export/retention.
- Robust duplicates across phone/name transliteration and household/family linkage.
- Validating actual RCIC licence numbers against CICC's current register.
- Regulatory exceptions, immigration eligibility decisions, legal advice, IRCC submission.

## Acceptance checks

- New \`tests/test_crm.py\`: prospect fields, deduplication, activity, appointment validation, versioned draft, PDF scanning, quarantine, role isolation, signed-copy reviewer attestation, idempotent conversion and database composite foreign keys.
- \`scripts/postgres_crm_smoke.py\`: actual limited PostgreSQL role, RLS isolation between two fictional practices, agreement creation and unsigned consultation gate.
- \`scripts/verify_rls.py\`: all CRM tables must have FORCE RLS.
- \`.github/workflows/ci.yml\`: includes new script and syntax checks for \`crm.js\`.
- Local browser/manual acceptance (still required): create two firms, add fictional prospects, schedule a consultation, download printable agreement, simulate safe signed PDF scanning with isolated ClamAV, review, complete and convert. Validate browser rendering on Windows, Keycloak end-to-end, print layout and failure handling.

## Next bounded vertical slice

**Signed service retainer + conflict/scope checks → case assignment and program-specific milestones.** Connect existing evidence/form factory only after an explicit, governed engagement gate. Later: deadlines, communication timeline, financial ledger and full file closure.

This sequence preserves the existing form-factory/evidence architecture and makes the product genuinely more useful to practising RCICs without pretending to support regulatory requirements it has not implemented.
