# Conditional study permit intake — identity and financing v2

This release extends the *preliminary client questionnaire* from 18 to **27
questions**, reusing the existing append-only client submission, staff accept/
dismiss and pending-fact verification workflow.

The added questions are based on the currently published official application
instruction pages:

- IMM1294 (outside Canada):
  https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm1294.html
- IMM5709 (inside Canada):
  https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm5709.html

| Parent question | New conditional fields | Official instruction location |
|---|---|---|
| Have you used other names? | Other family name and other given names | Personal details, question 2 |
| Do you have a national identity document? | Number, issuing country, issue date, expiry date | National identity document, questions 1–5 |
| Who pays your Canadian study expenses? | Other payer's description | Intended study, question 6 |

**Branch behavior:** A `yes` answer to the first two questions reveals the
corresponding fields. For the financing branch, `other` activates the
explanation. The server rejects nonempty answers to *inactive* branches even
if a client bypasses the browser interface. The active required subfields must
be supplied. If a controller is omitted or `unsure`, the consultant worklist
retains **unresolved applicability** instead of assuming a "no" answer.
National identity issue and expiry dates are checked for chronology. Monetary
answers reject nonfinite amounts and more than two fractional digits.

The schema response includes the instruction-section label for each added
question, a new template version, and no official submission capability.
The web portal continues to render from the versioned server-side schema.
A client submission is an immutable snapshot; consultant acceptance still
creates only a **pending**, unverified case fact. Previous questionnaire
revisions remain in case history.

Limitations: This is an *internal preparatory questionnaire*, not a validated
translation of each official form field or a complete conditional field
inventory. If several other names were used, current text fields need
subsequent repeatable-name support; they do not purport to capture every
possible historical alias. Country-specific requirements, official XFA field
mapping, PDF generation, signatures, filing, eligibility and professional
review all remain outstanding. Use synthetic development records only.
