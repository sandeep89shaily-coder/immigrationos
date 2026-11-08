# Repeatable former relationships and foreign-country residences — v2

Official instructions consulted 2026-11-08:
- IMM 1294: https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm1294.html
  - Personal details, question 11: previous marriages/common-law relationships
  - Personal details, question 8: other countries of residence for more than six months in the previous five years
- IMM 5709: https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm5709.html
  - Personal details, question 10: previous marriages/common-law relationships
  - Personal details, question 8: other countries of residence for more than six months in the previous five years

## Current implementation

The prior repeatable workflow already supports multiple address, employment, education and travel records. This release adds two **distinct** repeatable proposal categories:

1. `previous_relationship` requires relationship type (married or common-law), former partner family and given names, and relationship start and end dates. Former partner birth date can be provided. Date order is validated.
2. `foreign_residence` requires country, immigration status held there, start/end dates, and an explanation only when immigration status is `other`. A missing end date or reversed interval is rejected.

The client submits as many distinct records as needed using the existing verified-email, case-granted portal. Duplicate submissions with the same canonical fields remain blocked. Each proposal is **immutable**, with a fingerprint and a client submission audit event. A consultant can individually accept or dismiss a proposal; dismissals do not create master records. Acceptance creates a **separately versioned but unverified** supplemental applicant record, which is visible in the Applicant workspace through the case-bound staff read endpoint `/repeatables/master-records`.

Records and portal proposal categories are enforced by the PostgreSQL database. The new master table requires **FORCE ROW LEVEL SECURITY**, with staff-only INSERT/SELECT policies and no UPDATE/DELETE privileges for the restricted application role. No client has direct master-table write privileges. The complete portal-to-consultant path is covered by synthetic unit and PostgreSQL integration tests.

## Not claimed

- A supplied foreign stay is not automatically classified as relevant to the five-year/six-month IRCC question. Any exclusions, dates, and status implications require professional assessment.
- Multiple previous relationships and residence records are preserved, but the form's full conditional questionnaire, government PDF field mapping, annex rules and filing mechanism remain incomplete.
- Acceptance is **not evidence verification**, immigration eligibility determination, document completeness or authorization to submit.
- Data should remain **fictional** until the application is approved for real client use.
