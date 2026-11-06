# ImmigrationOS form factory — commercial pivot

**Objective:** Compete against established Canadian immigration software by producing
*correct, reproducible, version-specific* form outputs—not by displaying a large
number of unsupported PDF links.

## Four separately reported coverage metrics

1. **Official index discovered:** entries (including checklists and guides)
   parsed from the official [IRCC form index](https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides.html).
2. **Reviewed catalog and mapping:** official revision, route, PDF/digital type,
   field-level mapping and evidence provenance professionally reviewed.
3. **Autofill working:** repeatable generation on the reviewed form revision.
4. **Official validation verified:** current form opened in the appropriate
   official software/portal and validated end-to-end, including any required
   barcode and signature/consent steps.

Only stages 3–4 should count toward a genuine "400 forms supported" claim.
A static form catalog, an internal preflight, or a synthetic PDF fixture does
**not** count as a working official form.

## Why a single PDF adapter cannot fill all IRCC forms

IRCC forms include dynamic/barcoded PDFs and digital portal screens. IRCC
requires certain forms to be opened in Adobe Reader and validated to generate
2D barcodes. A pypdf merge is **not** a substitute for IRCC validation.

Official guidance:
- [IRCC form and checklist index](https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides.html)
- [How to open IRCC PDF forms](https://ircc.canada.ca/english/helpcentre/answer.asp?qnum=138)
- [2D barcode validation](https://www.ircc.canada.ca/english/helpcentre/answer.asp?qnum=1523)
- [IMM 5406: digital and PDF variants](https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm5406.html)

**No IRCC form currently has an approved official PDF generation adapter in
this project.** The existing two study permit templates are internal previews.

## This increment: concrete tools

- \`app/catalog_import.py\`: strict parser for IRCC's actual form-index table,
  including variant identifiers, linked official source, and modified month.
  It rejects broken/missing layouts, duplicate identifiers, non-government
  links, invalid dates, or truncated downloads. No user-supplied URLs.
- \`scripts/observe_ircc_catalog.py\`: one-shot, review-only research
  observation. Produces a JSON catalog with checksum and a Markdown summary.
  This process cannot mark any form as usable.
- \`.github/workflows/ircc-form-observation.yml\`: weekly/manual GitHub job
  exporting that observation as a retention-limited artifact, without
  automatically publishing forms or modifying the software.
- \`app/pdf_form_adapter.py\`: tested, pinned static AcroForm text adapter
  using an explicit allowlist and template SHA-256. It refuses XFA, PDF
  JavaScript, barcode-required forms, unapproved field lists, encrypted
  templates and unexpected form revisions.
- \`GET /api/v1/orgs/{org_id}/ircc/coverage\`: reports the true number of
  reviewed previews and the number of actually supported official form
  generators (zero at this stage). Tenant authenticated.

## Mandatory per-form release gate

1. RCIC-approved form version and application context (inside/outside,
   portal versus paper, principal versus spouse/dependants).
2. Official source URI, revision label, template checksum, source-observation
   and applicability/routing evidence.
3. Complete field inventory (including conditional sections, repeats,
   declarations and signatures), with named canonical data paths.
4. Evidence-linked, consent-appropriate client data; conflicts never silently
   resolved. All critical fields independently verified.
5. Independent PDF/portal golden sample tests for every supported revision.
6. Required official Adobe/barcode validation and professional sign-off.
7. Version monitor alerts and blocks obsolete/unreviewed revision use.
8. Audit log, migration/rollback, security and regression checks.

## Next development order

- Catalogue the official index to full research coverage, then triage the
  most-used forms; do not imply every index item is an application form.
- Deliver complete applicant/person/family canonical records and conditional
  questionnaires with repeatable work/education/travel timelines.
- Validate the first actual static PDF form that is technically compatible
  with the adapter, using official versioned examples and human QC.
- Implement Windows Adobe-assisted verification for dynamic/XFA forms,
  without claiming to regenerate IRCC barcodes independently.
- Expand by measured RCIC usage frequency and shared field families
  (representative, temporary residents, permanent residence, sponsorship,
  citizenship, Quebec/PNP); maintain a reproducible pass/fail coverage ledger.

**Production posture:** Development with synthetic data only. Neither the
index-importer nor the synthetic adapter handles actual client submissions.
