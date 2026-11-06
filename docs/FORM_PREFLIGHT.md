# Form preflight: snapshot acknowledgement (development only)

## Purpose
Adds a **conservative internal preflight** to IMM1294 and IMM5709 preparation.
It is *not* a complete field mapping, official IRCC PDF, eligibility assessment,
professional credential verification, or government submission approval.

Current sources were checked on 2026-11-06:
- IMM1294: https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm1294.html
- IMM5709: https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm5709.html
Both were shown as updated June 2026 on their IRCC pages. These observations
are not a claim that the source will remain current.

## Workflow
1. Create a synthetic study-permit case.
2. Upload supporting documents and scan any client-portal submissions.
3. Record facts and have permitted consultant-role staff explicitly verify them.
4. Resolve open issues and tasks.
5. `GET /api/v1/orgs/{org_id}/ircc/cases/{case_id}/forms/IMM1294/preflight?filing_context=outside_canada`
   to see blockers, mapped evidence and the case-specific snapshot digest.
6. A consultant-role staff member may acknowledge only the exact digest shown
   by that GET using `POST` to the same path with `/acknowledge` before the
   query string and JSON `{"snapshot_sha256":"..."}`.
7. Adding, changing or reviewing evidence invalidates the earlier acknowledgement.
   The acknowledgement is recorded as a metadata-only audit event.

## Security and accuracy boundaries
- Tenant and reviewer-role checks are enforced by the API and PostgreSQL RLS.
- Evidence linked to a quarantined or rejected client document is never copied
  into the preflight fields. Legacy form previews also exclude such facts.
- No raw client values enter the acknowledgement audit entry.
- Audit events are append-only in PostgreSQL; SQLite is for isolated tests only.
- No scanned-document verification is assumed for staff-origin uploads.
- Source observations older than 30 days block internal acknowledgement.
- No submission, PDF auto-generation, legal assessment, or AI decision is performed.
- The internal subset of field mappings is intentionally not a complete IRCC form.

## Remaining engineering validation
- Independently reviewed official PDF revision and mapping tests in Acrobat.
- Real RCIC workflow testing and professional role credential verification.
- Concurrency and case snapshot transaction design for actual production sign-off:
  the current case-row lock is a preview safeguard, not a substitute for a
  hardened immutable submission package workflow.
- Run full GitHub Actions CI and PostgreSQL isolation before merging.
