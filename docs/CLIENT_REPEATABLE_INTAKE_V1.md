# Client repeatable family and history intake — initial implementation

This extends the *existing* OIDC case-granted client portal and the existing
consultant intake workspace. A client may propose one family member, address,
education period, employment period, or trip at a time. These are validated using
the same strict family and history schemas used by the staff editors.

Each submitted entry is an immutable, case/tenant-bound proposal with a template
version and content digest. The server refuses exact duplicate proposals from the
same portal user and rejects malformed dates, invalid enumerations and extra
fields. Only the submitting client can list their own proposal metadata.

Consultants can inspect submitted proposals, then **accept** or **dismiss**
each once. Acceptance creates a new reusable family or history record for the
case's client, marked as **unverified**. It never creates verified CaseFacts,
verifies historical continuity, updates existing records, or generates an
official PDF. Dismissal never mutates the applicant profile. The original
proposal and its decision remain as separate records; no edits or deletions
are granted to the runtime PostgreSQL role. Exact duplicate master imports
are blocked.

PostgreSQL RLS enforces portal grant, verified identity and case/tenant context
for client submission and access; consultant insert policy requires an active
owner, admin or consultant membership, and normal API case assignment rules
continue to apply. Audit events include only metadata, not names or values.

## Current limitations

- The browser forms collect one item at a time; they do not yet support editing
  an earlier submitted proposal. Clients submit corrections as a new record,
  which a consultant must compare and review.
- More complex family relationships, previous names, multi-status timelines,
  duration/continuity analysis, and all IRCC-specific conditional questions
  require individually reviewed field definitions and additional workflow.
- No proof of completeness of any family/travel/employment history is implied.
- No record is an official IRCC form field, signed representation agreement,
  verified source document or submission-ready application.
- Development remains restricted to fictional test clients.
