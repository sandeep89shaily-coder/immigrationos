# IMM5476 internal evidence checkpoints (development only)

The paid-CICC appointment's 21 observed official PDF field identifiers are mapped to reviewed case evidence. This release adds **immutable checkpoints**, not government PDFs.

## What a consultant can do

On a study-permit package with IMM5476 selected, the workspace shows all observed fields and their evidence status, plus a count of saved checkpoints. Once there is at least one verified value and no disputed/unsafe fields, the consultant can record an internal checkpoint.

The saved checkpoint contains the exact historical field statuses, verified values, source IDs, document hashes, mapping version, original template SHA-256, and remaining blockers. It is immutable. Later changes to case evidence cause the historical checkpoint to show **stale** when compared to the current preview.

This enables a real form-preparation review history without the vendor PDF SDK, without copying answers from unverified applicant profiles, and without falsely claiming completed form coverage.

## API

GET /api/v1/orgs/{org_id}/cases/{case_id}/ircc/IMM5476/packets

Returns up to 30 most recent snapshots, with is_current indicating whether each saved snapshot still matches current case data. Only authorized and assigned-case staff can access them.

POST /api/v1/orgs/{org_id}/cases/{case_id}/ircc/IMM5476/packets

Requires the selected representative form in an initialized study-permit package and a JSON body containing an expected_sha256 equal to the freshly computed preview hash and acknowledge_internal_only=true. The consultant must have write permission to the case.

Capture rejects cases with zero verified fields, closed cases, open evidence issues, stale official source review, invalid/conflicting/unreviewed data, missing case-document links, or uncleared malware scans. It accepts genuinely missing fields as explicit missing status for a PARTIAL checkpoint. It rejects duplicate snapshots and stale submitted hashes.

Stored values can ONLY come from reviewed CaseFact records with a same-case document that has an explicitly cleared PortalSubmission scan. Raw or unreviewed values never enter the packet. Audit metadata contains IDs and hashes only, not applicant names or raw evidence.

## Security and limits

Migration 0019_imm5476_packets creates a separate append-only table with organization/case/package composite foreign keys, PostgreSQL RLS, and SELECT/INSERT-only app grants. No update/delete endpoint or PDF generation API exists. The results always report that IRCC form validation, official autofill and submission are unsupported.

The test suite covers partial creation, current/stale status, duplicate/stale input rejection, unsafe/unreviewed sources, access permissions, and closed/open-issue case blockers. This is a development-stage feature for fictional test clients only pending privacy/security review, licensing, full IMM5476 mapping and RCIC professional validation.
