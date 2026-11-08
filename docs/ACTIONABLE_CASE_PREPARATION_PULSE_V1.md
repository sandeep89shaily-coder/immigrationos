# Actionable case preparation pulse (internal development)

The existing consultant Intake tab now links each outstanding preparation work item directly to its **existing** destination, rather than requiring consultants to locate the workflow manually.

The server supplies an explicit allowlisted `target_tab` for each item:

| Worklist source | Existing consultant tab |
| --- | --- |
| Application package not initialized | Package |
| Preliminary questionnaire gap | Intake |
| Pending family or history proposal | Intake |
| Timeline explanation / correction | Applicant |
| Missing or unreviewed requirements | Planning |
| Case evidence issue | Issues |
| Open case task | Tasks |
| Form source/preflight blocker | Preflight |

The UI uses the current, already-authorized case context and never interprets server data as executable URLs or arbitrary frontend actions. A pending client proposal, timeline request, task, or evidence issue includes its **case-scoped record ID**, which the relevant view uses to focus the exact row. Items lacking an individual record open the relevant module at its top. The interface provides a link back to the combined worklist.

This is navigation only: opening an item **does not** create or mark a review, acknowledge a form, accept client evidence, import a profile claim or change case state. The existing module authorization and professional review controls remain authoritative.

The backend navigation targets are covered by unit tests, and the client and consultant JavaScript is checked by CI. No new personally identifiable data is stored or transmitted to external providers.

**Not a release gate:** This is a preliminary internal workflow over partial questionnaires, non-exhaustive documentary requirements and limited form manifests. It is not an IRCC form completeness or submission-readiness assertion. Use fictional test data only.
