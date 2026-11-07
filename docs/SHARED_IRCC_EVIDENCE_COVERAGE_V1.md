# Shared reviewed-evidence coverage — internal field subsets

This increment introduces a common, authenticated case-level evidence coverage
view for both registered study-permit contexts (IMM1294 outside Canada, IMM5709
inside Canada). It consumes reviewed `ObservedForm.preview_fields` definitions,
rather than hard-coded per-form PDF-generation code.

## Endpoint

`GET /api/v1/orgs/{org_id}/ircc/cases/{case_id}/forms/{form_code}/evidence-coverage?filing_context=outside_canada`

The response reports a field-by-field internal status, number of verified and
missing **preview** fields, provenance IDs and source hashes for verified values,
source revision freshness, blockers and a deterministic snapshot SHA-256.
Each read is tenant/case/assigned-staff controlled, with `no-store` headers.

## Security and incomplete-form safeguards

Only a human-reviewed CaseFact with same-case source-document linkage and
explicitly cleared malware scan may supply a displayed value. Unreviewed,
conflicting, invalid, missing-link, and unscanned values are not exposed. Date of
birth receives a syntax check. A change of evidence changes the snapshot digest.
Wrong application context is denied. All returned objects explicitly keep
`entire_official_form_complete=false`, `pdf_export_available=false`,
and `submission_supported=false`.

`verified_internal_subset` refers to only the six observed internal fields.
**It is not a form readiness, legal sufficiency, professional approval or
official validation indicator.** Conditional fields, all form controls,
declarations, signatures, dynamic XFA, and version-specific PDFs are outside
this increment. IMM5476 retains its separately pinned 21-field review flow.
No new form is counted as autofill-supported.

Next: move individually reviewed field definitions into a stable,
revision-pinned structured manifest with condition expressions and explicit
coverage denominator, then use that manifest to drive questionnaire and
PDF-output mapping *only after* complete per-form review.
