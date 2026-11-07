# IMM5476 (11-2025) — reviewed case preparation

**Scope:** Read-only preparation for the 21 observed text fields in the *appoint paid-CICC* representative scenario. This is **not** a completed official PDF, all-fields mapping or a legal completeness decision.

## What's built

The existing Application package consultant screen now shows the IMM5476 observed-field progress count and an expandable list of 21 fields, each with human-reviewed evidence status and permitted canonical values. The panel appears only when IMM5476 belongs to the case package.

GET /api/v1/orgs/{org_id}/cases/{case_id}/ircc/IMM5476/preparation

This case-scoped, permission-checked GET route accepts only operation=appoint and representative_type=paid_cicc. It does not write PDFs or XDP. It returns Cache-Control: no-store.

Only human-verified CaseFact records attached to that firm's exact case, to a document belonging to that case, and to an explicitly malware-cleared PortalSubmission can show values. Rejected, pending, contradictory, unlinked and uncleared sources cannot leak their values in the response. Eligible fields expose source fact IDs, document IDs and document SHA hashes for review. Any change to a verified value changes the reported snapshot hash.

Statuses: missing_evidence, conflicting_evidence, unreviewed_evidence, invalid_evidence_value, missing_case_document, source_scan_not_cleared, verified_source_value.

For a complete 21/21 observed-field subset, the existing strict resolve_verified_form_fields kernel independently checks tenant scope, human review, cleared document status and provenance. This still does **not** mean a government form is ready.

## Remains blocked even at 21/21

- Full conditional IMM5476 mapping and all operation branches
- Commercial Qoppa/Apryse licence and production suitability
- Applicant and representative signature/declaration workflows
- Official PDF generation, IRCC validation, barcode generation or submission
- Privacy and security acceptance for real client data

All production and official-support flags remain false. Neither the Qoppa evaluation library nor its binaries are distributed with the project.

## Tests

Synthetic API tests cover no evidence, full fictional reviewed evidence, scan statuses, conflicting values, missing documents, unreviewed facts, invalidation on changed evidence, unassigned case access, closed matters and open evidence issues.
