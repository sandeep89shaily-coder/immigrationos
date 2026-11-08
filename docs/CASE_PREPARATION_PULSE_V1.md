# Case preparation pulse — preliminary unified consultant worklist

A read-only consultant endpoint combines existing case preparation signals, without inventing a new professional readiness threshold:

`GET /api/v1/orgs/{org_id}/cases/{case_id}/preparation-pulse`

Included independently scoped domains:

- Conditional client questionnaire answers and their human/evidence review states.
- Awaiting consultant decisions on repeatable family/history proposals.
- Outstanding timeline explanations, consultant reviews, requests for more information, and reviewed but uncorrected findings.
- The existing non-exhaustive document requirement matrix and source refresh requirements.
- Existing open case tasks and evidence issues.
- Existing registry-limited IRCC form preflight blockers and current/stale staff acknowledgement.
- Explicit missing-package and unsupported-workflow blockers.

This makes **one filtered list of work items**, grouped by domain; it neither writes database records nor changes domain-level acceptance criteria. The existing worklist, evidence and preflight helpers remain the source of truth. When a package has not been initialized or is unsupported, this returns explicit missing-domain blockers instead of falsely reporting no gaps.

The staff Intake tab displays each outstanding item, its area, status and source reference ID. No questionnaire answers, full applicant address history, client responses or raw fact values are reproduced in the combined pulse. Worklist freshness is evaluated on each request; response is `Cache-Control: no-store`.

**Not a readiness certificate:** `operational_worklist_clear` covers only the listed operational tasks; even when true, the response always reports official form completeness, eligibility validation, PDF generation and filing support as **false**. No automatic publication, submission, form-fill or legal advice is enabled. Study permit questionnaire and IRCC forms are partial, and document requirements vary with jurisdiction, conditions and current government instructions.

Development remains synthetic/fictional data only.
