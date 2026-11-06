# First real form target: IMM 5476 (11-2025)

**Status: official version researched; template not technically validated; autofill not enabled.**

This form is high priority for an RCIC firm because a representative may
need it across temporary-resident, permanent-resident and citizenship cases.
However, an authorized person is not created simply because a form exists.

## Verified source baseline (2026-11-06)

- [IRCC official instructions for IMM 5476](https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm5476.html)
- [Official IRCC IMM 5476 PDF (11-2025)](https://www.canada.ca/content/dam/ircc/documents/pdf/english/kits/forms/imm5476/01-11-2025/imm5476e.pdf)
- IRCC identifies version **11-2025**; acceptance of older versions
  ended **March 12, 2026** (verify current guidance before use).
- Form is four pages, with conditional sections **A–E**.
- Some signature approaches differ between portal/secure-account
  submissions and submissions outside those channels.
- Separate representation forms can be required for adult dependents,
  spouses or partners depending on circumstances and application type.
- Paid representatives must be authorized and in good standing.

## Branching workflow already coded

| Action | Sections the official instructions identify |
|---|---|
| Appoint representative | A, B, E |
| Update appointed representative contact information | A, B, E |
| Cancel representative | A, C, E |
| Cancel and appoint new representative | A, B, C, E |
| Withdraw as representative | A, D, E |

API for a firm member:

\`GET /api/v1/orgs/{org_id}/ircc/forms/IMM5476/workflow?operation=appoint&submission_channel=portal_or_secure_account\`

Or substitute \`submission_channel=outside_portal\`.
The output is review guidance, not a filled form or legal approval.

## Template inspection (development only)

The official PDF should be downloaded from the IRCC source, opened in Adobe
Reader and verified as the most recent relevant version. Do **not** use a real
completed applicant PDF during development.

From the repository (Python dependencies installed):

\`python -m scripts.inspect_ircc_form --input "C:/Forms/imm5476e.pdf" --form-code IMM5476 --output "reports/IMM5476-inspection.json"\`

The inspector outputs a checksum, field count, field names/types, and indicators
for XFA, active content, populated inputs, signatures and unsafe features.

The authenticated development API alternative is:

\`POST /api/v1/orgs/{org_id}/ircc/inspect-template\`

using multipart \`form_code=IMM5476\` and blank \`file=<local PDF>\`.
Only owner/admin/consultant members have this access. The API does not persist
the bytes and is disabled in production. Do not upload personal data.

## Strict release gates before counting IMM 5476 as supported

1. Obtain the actual current official blank template from IRCC; confirm source.
2. Record its SHA-256, PDF structure, field names, conditions, checkboxes,
   signatures and potential XFA/JavaScript dependencies.
3. Review the field-level canonical mapping with practising authorized RCICs.
4. Verify the PDF adapter's compatibility on Windows/Adobe; pypdf field
   readback on a synthetic fixture is **not** official form validation.
5. Test all five action paths, signatory combinations and submission channels.
6. Add current version monitoring, fixtures, review attestations and release
   rollback. Do not publish an approved adapter while steps are incomplete.

## Product contract

**One official form is supported only when:**
a pinned/current PDF revision is mapped; every conditional section is
covered; real fill-and-readback tests pass; required Adobe/portal validation
passes; and an RCIC reviewer approves the release. A template upload alone
does not satisfy this contract.

Current official form-autofill count remains **0**, even after this milestone.


## Official blank-template observation pipeline

The form-factory research job downloads the **public blank PDF only** from
the exact reviewed IRCC HTTPS URL. It performs transient, read-only PDF
structure inspection and writes a JSON observation (SHA-256, field structure,
XFA/action indicators and compatibility category). It does not save PDF
bytes, process client documents, publish mappings or approve releases.

Run the same one-shot observation locally if the hosted government connection
is unavailable:

\`python -m scripts.observe_imm5476_template --output reports/imm5476-observation.json\`

After a current official template SHA-256 has been independently reviewed
and approved, use \`--expected-sha256 <64-character lowercase sha256>\`
to flag a changed download as \`changed_bytes\`. A matching checksum is only
evidence of byte identity; it does not verify legal, Adobe, barcode, signature,
or application-context requirements.

The separate \`IMM 5476 official blank-template observation\` GitHub workflow
supports manual dispatch and a weekly schedule. It stores technical
observations as short-retention Actions artifacts. Network failures produce
an explicit \`unavailable_or_not_inspectable\` observation and a failed
monitoring run; they do not alter \`main\`, claim a current form, or block
the unrelated application release tests.

**Current status:** no approved baseline hash and no validated official
form generation. Continue to report zero supported IRCC official PDF outputs.
