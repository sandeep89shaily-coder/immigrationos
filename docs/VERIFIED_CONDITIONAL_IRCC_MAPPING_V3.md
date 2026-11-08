# Verified-only conditional IMM1294 / IMM5709 internal mapping v3

Official source pages checked November 8, 2026:
- IMM1294: https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm1294.html
- IMM5709: https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm5709.html

Both official instruction pages cover Personal details question 2 (other
names), National identity document questions 1–5, previous marriage/common-law
history (IMM1294 question 11; IMM5709 question 10), and countries of prior
residence (question 8). These were independently checked as overlapping
preparation questions, not validated as PDF/XFA control names.

This update extends each incomplete internal form manifest from 14 to **24
fields**, 18 with source links and question-level instruction labels. The
new ten are:
- Other name/alias declaration, other family name, other given names (3)
- National identity document declaration, number, issuing country,
  issue date and expiration date (5)
- Previous marriage/common-law declaration and qualifying foreign-residence
  declaration (2)

**Conditional semantics:** The two alias details are active only when the
other-name declaration is `yes`; the four document details are active only
when the national-ID declaration is `yes`. Their parent value must be
independently reviewed, document-linked and scan-cleared. Missing, conflicted,
unreviewed, scan-blocked or `unsure` parent values keep the branch
**unresolved**, not inactive. A verified `no` makes the detail fields
inactive and suppresses their values/evidence identifiers in the output.
This conservative software rule does not assert that documentary proof of a
negative answer is legally required: an RCIC must establish whether and how
the official form question is appropriately answered.

The newly mapped national-ID dates are syntax validated, while declaration
values must be `yes` or `no` to become a valid verified internal condition.
The form coverage snapshot and the unified evidence-to-form trace reflect the
new manifest fingerprint and explicitly list the remaining **16** preliminary
questionnaire paths absent from the reviewed manifest.

**No legal or filing claims:** The mapping remains a partial internal
question-level model. It is not a complete official IRCC form inventory and
does not expose validated PDF control IDs, government-ready outputs or an
eligibility determination. A client statement or a historical record does not
become independent documentary evidence by appearing in the trace. Use only
synthetic test cases until the system is independently approved for real data.
