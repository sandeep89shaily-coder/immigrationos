# ImmigrationOS — prioritized development actions

## P0 — complete conditional-manifest correctness
- Review `fix/conditional-repeat-fail-closed-and-handoff` against latest main; run `pytest -q tests/test_form_manifest.py` and full suite in CI.
- Acceptance: parent false/inactive needs no repeat count; unknown/unsure does not become empty; active needs explicit bounded integer; invalid hidden counts rejected; no regressions.
- Then inspect all callers of `expand_manifest` for status expectations and evaluate conditions from verified, scan-cleared case facts only.

## P0 — finish one official form safely
- Pick an official revision, inventory every real field, conditional branch and signature requirement; pin source checksum/observation.
- Complete an independently licensed, permitted SaaS autofill engine evaluation and independent PDF/Adobe/IRCC readback with synthetic golden samples.
- Acceptance: every field, revision and conditional has traced acceptance, no claims of official form support until an RCIC signs off.

## P0 — package integrity and approval
- Bind every generated document to case, evidence and immutable source revision; fail closed on stale/replaced/unscanned documents.
- Require scoped RCIC approval, signed package checklist and append-only audit.

## P1 — security
- Independently verify PostgreSQL RLS including row/case-level leakage, portal authorization, revocation and privilege escalation; test with separate restricted runtime role.
- Security review of secrets, encryption, malware quarantine, retention, backups, privacy jurisdiction and vendor agreements before live data.

## P2 — essential CRM only
Communications, deadlines, tasks, invoices/trust accounting after end-to-end case package/approval passes.

## Session discipline
Inspect main and PRs before changes; branch → tests → PR → inspect CI → update these four handoff files. No background development claim.

## Current checkpoint: versioned evidence-to-manifest resolver
Review `feature/versioned-manifest-evidence-resolver`; check CI and ensure independently reviewed, scan-cleared, tenant/case scoped condition parent facts; verify unknown parents and absent counts fail closed. Next build authoritative repeat-cardinality evidence, cross-field validation and version-pinned preparation packet integration. Do not expose these internal field keys as official IRCC XFA identifiers.

## Current P0: case preparation integration
Review `feature/preparation-manifest-resolver-gate`; run unit, PostgreSQL-isolation and read-only probe CI. Check that a completed 18-applicable-field conditional subset stores a version/provenance hash; six-field-only packets cannot bypass the new gate; a resolver/coverage disagreement cannot capture. Follow with cross-field date constraints, authoritative repeat-cardinality and source-refresh handling. Do not claim official PDF compatibility.

## Next unfinished P0 following merged PR #63
1. Add authoritative independently reviewed repeat-record cardinality and prevent inconsistent count assertions before exposing repeatable manifest integration in live case workflows.
2. Cross-field validation for chronology (passport validity, education dates), unresolved conditional assertions and source revision freshness; retain fail-closed capture semantics.
3. Complete one revision-pinned official IRCC form field inventory and independent PDF engine SaaS-license and Adobe/IRCC validation gates. Until then zero official validated outputs.
4. Broaden case-document package + RCIC sign-off with case-bound immutable provenance and restricted-role PostgreSQL tests.
