# Conditional preliminary intake and consultant review (November 2026)

This extends the **existing** study-permit client questionnaire rather than making a second questionnaire database.

- The client-facing preliminary questionnaire now includes a conditional details field when a client reports an earlier visa/permit refusal. The condition is expressed as a constrained parent path/value in the returned schema, rendered as a hidden/disabled control when inactive.
- The server, not only the browser, requires a nonempty refusal description when the parent is `yes`. It rejects a stale hidden answer when the parent becomes `no` or `unsure`. All questionnaire submissions remain immutable, versioned and explicitly unverified.
- A consultant accepting a refusal-details answer creates a **PENDING** CaseFact; no applicant answer is promoted into independent source-verified evidence.
- The existing consultant Intake workspace now displays the evidence gap worklist for all preliminary questions, condition applicability, counts of source-verified questions, and summary counts of reusable family, address, education, employment and travel records. It links to the existing Applicant tab for editing repeatable records rather than duplicating their storage.

**Limits:** This is a preliminary 18-question study-permit questionnaire, not a complete IMM1294/IMM5709 inventory, eligibility opinion, verified legal rule, or permission to generate/sign/submit an official PDF. The client form exposes only the new explicit prior-refusal condition. Family/history editing remains in the existing practice workspace; a separate client-side repeatable editor is not implemented here. The answer schema version was advanced from 2026-11-06 to 2026-11-08, and old submissions remain readable but not eligible for new staff accept decisions.
