# Core RCIC application package — first study-permit vertical slice

**State:** Implemented in the consultant workspace and API for *fictional development records*. No form is officially autofilled, Adobe-validated or submitted. This is a core case-preparation building block, not a marketing coverage claim.

## Why this matters

ImmigrationOS already had clients, matters, document storage, client questionnaires, verified facts and an incomplete IRCC form registry. Those were separate experiences. A working RCIC case needs **one file** that identifies the selected filing route, expected forms, required source evidence, missing items and reviewed draft copies.

This increment creates that object without claiming support for unsupported government technologies.

## End-to-end consultant path

1. Create a fictional client and a **study-permit matter**. If the practice uses the governed flow, link its written service agreement first.
2. In the case workspace select **Application package**.
3. Confirm the actual route **inside Canada** or **outside Canada** and decide whether the representative form is included. The route is pinned; it cannot silently switch later.
4. The package automatically lists **IMM 5709** (inside Canada) or **IMM 1294** (outside Canada). It also lists **IMM 5476** when the consultant selected it. The existing source-anchored identity/passport, letter of acceptance, financial evidence and PAL/TAL worklist is shown beside the forms. This is deliberately a **non-exhaustive document checklist**, not legal eligibility logic.
5. Download the applicable official blank form from the IRCC source outside this application and prepare it in the appropriate official software. This system cannot yet fill the actual form fields.
6. Upload a fictional PDF form copy via the case **Documents** tab.
7. From **Application package**, attach that *same-case* PDF to its form slot. The server checks the immutable document hash and sends the bytes to the isolated development malware scanner. If the scanner is unavailable, the copy remains **quarantined**.
8. An owner/admin/consultant reviews the **scan-cleared** copy against current official instructions. The resulting attestation, timestamp and document hash are preserved; a replacement PDF creates another copy and makes the old acceptance historical.
9. The worklist shows pending/received/reviewed form copies and existing supporting document states. It never reports the file as government-ready or actually submitted.

There is intentionally **no** manual "Mark IRCC validated" or "Submit" action. Staff review is not proof of genuine IRCC/Adobe validation.

## Concrete implementation

- \`app/package_models.py\`: \`CaseApplicationPackage\` plus append-only-linked \`PackageFormCopy\` records, immutable filing route, source revision, checksum, case/document foreign keys, scan and staff review.
- \`alembic/versions/0014_application_package.py\`: same-case FK joining \`CaseDocument\`, unique form-copy document linking, restricted field edits and PostgreSQL **FORCE ROW LEVEL SECURITY**.
- \`app/application_package.py\`: case-scoped worklist, route creation, manual PDF linking, quarantine/re-scan and staff review API. Reuses existing IRCC registry and study-permit evidence matrix rather than duplicating source requirements.
- \`app/static/application_package.js\`: new **Application package** tab in the consultant workspace.
- \`tests/test_application_package.py\`: form route selection, idempotency, unsupported programs, same-case proof, copy history, scan failure, staff review requirements, role isolation and database FK rejection.
- \`scripts/postgres_package_smoke.py\`: limited PostgreSQL runtime role checks for two firms, form-copy review and cross-firm denial. Its scanner and PDF bytes are explicitly fictional test doubles.
- CI checks the new JavaScript, Python unit tests, migration, PostgreSQL RLS permissions and application-package smoke.

## Source and coverage policy

Official sources used for the initial form selections:

- [IMM 1294 — study permit outside Canada](https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm1294.html)
- [IMM 5709 — study permit inside Canada](https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm5709.html)
- [IMM 5476 — Use of a Representative](https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm5476.html)
- [IRCC study-permit documents](https://www.canada.ca/en/immigration-refugees-citizenship/services/study-canada/study-permit/get-documents.html)

Source records are observations, **not** legal instructions frozen forever. More country-specific lists, special cases, client/dependent variations, document exception decisions, official portal steps and up-to-date form releases require RCIC review.

**Official IRCC PDF autofill: 0 verified. Official IRCC PDF validation: 0 verified. Government submission integration: 0.**

## Next genuine core features

1. **Applicant and family relationships** (one master profile reusable across cases), with passports, spouse, dependants, travel and education histories.
2. **Structured IRCC form-answer drafts** linked to canonical applicant fields, evidence provenance and the *actual* observed PDF revision. Target one validated official form before scaling to more codes.
3. **Country/program-specific document requirement profiles** and professional applicability decisions, persisted with a source/version snapshot.
4. Real version-specific PDF field mapping and Adobe/portal acceptance testing, beginning with **IMM 5476** where technically appropriate. Dynamic XFA/JavaScript/barcoded forms must take a different, independently validated route.
5. Application-level reviewer approval, final export/handoff and a genuine deadline ledger.

Everything else—marketing feature count, automatic customer outreach, elaborate dashboards and advanced AI—stays out of the critical path until the first complete, verified application preparation workflow works.
