# Previous relationships and foreign residences — disclosure/evidence cross-check

This read-only change ties versioned screening answers to existing immutable
client proposals, consultant decisions and accepted supplemental applicant
history records. It does **not** add another master table or mutate an existing
case.

The preliminary study-permit intake now contains **39 questions**, including:
- `history.has_previous_relationships`: a yes/no/unsure screen for former
  marriages and common-law relationships.
- `history.has_foreign_residences`: a yes/no/unsure screen for residence in
  another country or territory for more than six months in the last five years.

Both are anchored to the Personal details sections of the official IRCC
IMM 1294 and IMM 5709 instruction pages:
- https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm1294.html
- https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm5709.html

**Worklist behavior**
- Missing or unsure answers remain unresolved, whether or not there are
  stored historic records.
- A “No” declaration with historical client proposals or consultant-accepted
  records is flagged as a discrepancy requiring consultant investigation.
- “Yes” without an accepted historical record is flagged as missing. A
  submitted but unreviewed proposal routes to the existing consultant review.
- Accepted histories are never automatically verified. Each essential field
  is compared with an *exact-value matching*, independently verified case fact
  linked to a case-owned, malware-scan-cleared document. Differences, pending
  facts, document gaps and unscanned sources remain blockers.
- Even when every essential field has matching evidence, the output explicitly
  requires **professional relevance review** before treating the form's
  question as adequately addressed. The system does not automatically decide
  whether a residence qualifies under IRCC's lookback, duration or exemptions.

The consultant study-intake worklist exposes two non-sensitive status records
and field-count metadata. The consolidated case preparation pulse routes
discrepancies and absent supporting evidence to the Applicant screen. A
pending client proposal is shown in its existing Intake review instead of
generating a duplicate navigation item. The UI never includes applicant names,
residence countries, exact dates or client text in status summaries.

**Evidence paths** use the internal, record-specific canonical shape
`supplemental.<kind>.r_<UUID hex>.<field>`. These are **not** PDF/XFA field
identifiers. Case-scoped facts and scanned documents are compared; facts from
other cases never count. Reusable master records are client-scoped within a
single firm, and must be re-reviewed with evidence for each matter.

This remains a development-only preparatory workflow using fictional data.
It does not certify an official form, legal eligibility, complete relationship
history or valid IRCC PDF, and does not support IRCC submission.
