# Applicant and family master data — core workflow increment

This increment connects the existing **Client → Case → Application package** path with reusable data and immutable answer drafts. It is intended for synthetic development records only.

## Functionality added

- Tenant-bound identity fields: names, birth date/country, citizenship, passport number and expiry. Shared across future cases for the same client.
- Tenant-bound family members with relationship and version-checked edits.
- Optimistic version enforcement for master data: stale browser edits return HTTP 409.
- A case-specific **internal answer draft** generated only after a study-permit package and applicant profile exist. IMM1294 or IMM5709 is selected from the pinned filing context. Drafts freeze the profile version and recorded answers and are append-only, rather than silently updating earlier case documents.
- A visible **Applicant** tab in the consultant case workspace, with identity and family editing and answer draft history.
- Relational organization/client/case integrity plus PostgreSQL FORCE ROW LEVEL SECURITY and limited production app-role grants.
- Audit metadata records changes without duplicating applicant PII into the audit table.

## Important non-capabilities

These drafts are **not official IRCC PDFs**, do **not** resolve evidence discrepancies, and do **not** convert self-reported data into verified case facts. No Adobe validation, official field mapping, barcodes, government submission, or eligibility adjudication is supported. Current internal field mapping is explicitly incomplete.

## Developer acceptance

Run `pytest -q tests/test_applicant_profiles.py tests/test_application_package.py` and `pytest -q`, plus the existing PostgreSQL smoke tests. Apply `alembic upgrade head` in a disposable development database. Test firm isolation and authorized consultant case/client access. Do not put real applicant data in the development system.

## Remaining major core work

1. Link master-profile values with provenance-backed case facts and resolve contradictions through a professional review queue before any form-value promotion.
2. Add travel, address, education and employment history models and reusable person-to-case roles; integrate client portal submissions.
3. Complete the program/country document requirement and exception-decision workflow, with source revision tracking.
4. Validate an actual, current IRCC PDF's technical fields/Adobe requirements per revision before enabling form generation. No blanket 400-form coverage claim.
5. Application-level approval/re-export, deadline monitoring and complete production-security verification.
