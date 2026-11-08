# Reviewed timeline clarification → versioned applicant history correction

This workflow creates a **traceable, deliberate consultant edit** from a
previously submitted client reply. It does not allow a client or staff assistant
to edit the master history through the clarification API.

The consultant must first open an active case and a clarification request
anchored to a prior timeline flag. The client submits a reply. The consultant
records `reviewed` (not `needs_more_information`). Only then can the
consultant submit a correction with a textual rationale and validated complete
history fields. The API checks the original audit SHA, the original flag hash
and the current case's history versions again before applying an edit.

For **uncovered periods**, a consultant can add a new dated record overlapping
the flagged gap. Existing records cannot be stretched under a gap request.
For **other flagged records**, an update must name a record ID explicitly
included in the original flag, with the current optimistic-lock version.
All history values use the same strict shared field validators as the existing
history editor, including date chronology.

A separate **immutable correction ledger** freezes the original details,
replacement details, old and new version, source clarification/reply/review
identifiers, the correction rationale, and the consultant identity. Original
client explanations and professional review decisions are not modified.
Repeat submission of a request fails closed. The restricted PostgreSQL role
has SELECT/INSERT but no UPDATE/DELETE on the ledger, with tenant/case RLS.
Audit events contain only identifiers, operation and version numbers, never
client responses, names, addresses or employer details.

The consultant Applicant workspace lists linked corrections and provides
a form for the reviewed clarification. Corrections never create or verify a
CaseFact, change official PDF fields, determine eligibility or certify timeline
completeness. They remain **unverified client/staff claims**, requiring original
documents and separate professional evidence review.

**Scope:** fictional data only. A historical correction does not guarantee that
every other prior document, review, or draft remains current. The existing
source-version and preflight checks must be re-run for any subsequent
application preparation.
