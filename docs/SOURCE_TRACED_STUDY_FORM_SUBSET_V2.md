# Source-traced IMM1294 / IMM5709 preparation subset v2

On November 8, 2026, the **official public instruction pages** for IMM1294
and IMM5709 were checked for overlapping questions. Both pages indicated a
June 2026 update at the time of this review. The existing six-field internal
source registry was preserved, while **eight more** directly documented
questions were added to the case-scoped internal guidance manifest.

Official guidance sources:

- IMM1294: https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm1294.html
- IMM5709: https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm5709.html

| Internal canonical path | Source section on both pages |
|---|---|
| `identity.passport_issuing_country` | Passport, question 2 |
| `identity.passport_issue_date` | Passport, question 3 |
| `identity.passport_expiry_date` | Passport, question 4 |
| `education.dli_number` | Details of intended study in Canada, question 2 |
| `education.program_start_date` | Details of intended study in Canada, question 3 |
| `education.program_end_date` | Details of intended study in Canada, question 3 |
| `finance.tuition_cad` | Details of intended study in Canada, question 4 |
| `finance.available_funds_cad` | Details of intended study in Canada, question 5 |

The **14 fields now mapped** (six previously reviewed, eight newly
source-traced) are an incomplete, internal question-level inventory, **not**
the actual interactive PDF's XFA control names or positions. Individual IRCC
form questions and conditional branches differ between contexts; this
increment deliberately adds only fields verified in both instruction pages.
Their internal `required` flag is false until applicability and conditional
requirements have been separately researched. This is *not* a declaration
that IRCC considers them optional.

The guidance fields carry their official source URL and source-question label
in the manifest, evidence coverage output, and manifest fingerprint. Revisions
invalidate previous internal answer-draft manifest fingerprints. Existing
client-side questionnaire answers remain preliminary, with human acceptance
creating only pending facts. Independently reviewed case-document evidence
must be cleared by the malware scanner before a source value can be displayed
as verified. Basic date validity, nonnegative two-decimal money amounts and
conservative DLI reference syntax are additionally enforced. A DLI number's
format passing does **not** prove the school is currently designated by IRCC.

Limitations remain non-negotiable:

- No complete official field inventory or mappings to PDF widgets/XFA nodes.
- No certification of every conditional question, country-specific checklist,
  legal eligibility, fees, or required supporting documents.
- No official PDF autofill, signing, submission, or production use.
- Case information and test documents must remain **synthetic**.
