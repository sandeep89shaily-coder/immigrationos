# RCIC evidence planning — development preview

This is a **non-exhaustive operational checklist**, not a legal eligibility
determination, authoritative document checklist, immigration form or permission
to submit an application. Use synthetic data only.

## Why this feature exists

Current practice workflows often mix up:
1. documents requested;
2. documents received but quarantined;
3. documents cleared for technical handling;
4. facts extracted from documents;
5. facts independently verified by a professional; and
6. legal applicability and sufficiency of evidence.

These are different states. ImmigrationOS never equates receipt with evidence
sufficiency or a professional decision.

## Supported scope

- Study permit **planning** only, with an explicit inside/outside-Canada context.
- Covers a small number of common *planning categories*: identity facts,
  passport/travel document, letter of acceptance or exception evidence,
  financial support evidence, and PAL/TAL/CAQ or exception evidence.
- The IRCC pages are observed source references, not a complete legal ruleset.
- A requirement's applicability, sufficiency, exemptions, regional instructions
  and current regulatory position must be checked by an authorized
  representative with the current IRCC instructions.

Sources, reviewed November 6, 2026:
- [IRCC study permit supporting documents](https://www.canada.ca/en/immigration-refugees-citizenship/services/study-canada/study-permit/get-documents.html)
- [IRCC PAL/TAL guidance and exceptions](https://www.canada.ca/en/immigration-refugees-citizenship/services/study-canada/study-permit/get-documents/provincial-attestation-letter.html)
- [IRCC proof of financial support](https://www.canada.ca/en/immigration-refugees-citizenship/services/study-canada/study-permit/get-documents/financial-support.html)

**No conditional requirement is automatically waived.** In particular,
evidence of a possible exemption is not an exemption decision.

## API

For a logged-in member of the correct firm:

- GET \`/api/v1/orgs/{org_id}/cases/{case_id}/evidence/matrix?filing_context=outside_canada\`
- POST \`/api/v1/orgs/{org_id}/cases/{case_id}/evidence/request-missing\`
  with JSON \`{"filing_context":"outside_canada"}\` (or
  \`{"filing_context":"inside_canada","requirement_keys":["passport"]}\`).

The POST creates **draft portal document requests only**; no message, email,
submission, or legal advice is sent. It is safe to retry sequentially:
existing open/received requests and existing matching documents prevent
duplicate requests. PostgreSQL case row locking serializes concurrent calls.

The matrix reports:

- \`unverified\`, \`facts_verified\`, \`conflict\` for canonical identity facts;
- \`missing\`, \`requested\`, \`quarantined\`, \`rejected_upload\`,
  \`received_for_review\` for supporting-document categories;
- source links, relevant document and fact IDs, open-issue counts, and whether
  professional applicability review is always necessary.

A cleared antivirus scan is **not** human verification, document authenticity,
or legal sufficiency. Staff-uploaded documents are displayed for human review,
not labelled approved.

## Security controls and tests

- All queries filter by \`org_id\` and \`case_id\`; no client portal endpoint
  can browse the firm's matrix.
- Existing organization authentication, role permissions and PostgreSQL RLS
  remain in force.
- Only firm staff (owner, admin, consultant or assistant) can create requests.
  Viewers can read but cannot create.
- Closed cases are read-only; non-study-permit matters fail closed.
- The system does not reveal sensitive fact values in audit entries.
- Quarantined or rejected portal documents never satisfy a received-evidence
  status.
- Identity conflicts remain visible even if values are marked verified.

## Deliberately not yet implemented

- A complete context-driven legal requirement engine for all study permit
  subclasses, dependents, countries, ages, provinces, exemptions and local
  visa office instructions.
- CICC licence verification or professional attestation.
- Evidence sufficiency, authenticity, fraud detection, funds calculations or
  legal eligibility determinations.
- Automatic email delivery of document requests.
- Actual IRCC form generation and automated submission.
- Version-reviewed rule publication, regulatory-impact analysis, export packs,
  production storage certification and third-party penetration testing.

## Proposed acceptance expansion

Next: professionally reviewed condition trees, source-effective dating, client
questionnaire branching, explicit exemption decisions with RCIC review trail,
evidence-linked form-field mapping, and review-signoff snapshots invalidated
when the underlying evidence changes.
