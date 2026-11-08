# Timeline clarification workflow v1 (development-only)

The existing read-only timeline audit is now connected to a complete
**consultant request → client reply → consultant decision** flow.

An authorized consultant runs a current, date-window-specific audit and selects
a concrete finding. The server re-evaluates the full case/tenant-scoped history,
validates the submitted audit SHA-256 and finding fingerprint, and refuses
unmatched or stale requests. The clarification question is visible only to a
case-granted client. A verified OIDC client submits one immutable response;
a consultant then records either `reviewed` or
`needs_more_information`.

Every request, reply and review is preserved in separate append-only,
RLS-enforced tables. Portal principals cannot edit the master applicant
history and cannot write professional review decisions. Staff review does not
automatically edit a history item, certify residence or employment continuity,
generate a form, or verify underlying documentary evidence. Where a correction
is justified, consultants must explicitly update the existing version-controlled
Applicant history record. Re-run the timeline audit afterwards.

The client portal and Applicant workspace now show these steps. Migration
`0021_timeline_clarifications` adds case-linked tables, restricted-role RLS,
append-only database privileges and a narrowly extended metadata-only audit
allowlist. Dedicated PostgreSQL smoke and unit tests cover separation of duties,
stale findings, immutable replies and tenancy boundaries.

**Release boundary:** synthetic fictional data only. The date window is chosen
by the user, not inferred from IRCC. A resolved clarification is not proof that
official application requirements have been met.
