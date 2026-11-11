# ImmigrationOS — verified development state

Last inspected: 2026-11-11. Base `main` commit: `b35181c76b5918dc069fa2bcb9c5ea09a34b177c` (PR #60 merged 2026-11-10). Work in this review branch is **not** considered merged.

## Existing, repository-backed capabilities
- FastAPI/PostgreSQL, OIDC dev auth, multi-tenant case/evidence architecture and FORCE RLS with documented case-scope gaps.
- Client/family and study-permit intake, reviewed document/fact provenance, case worklists and service engagements.
- IMM1294/IMM5709 *internal* manifest expanded to 24 fields; immutable preparation packets now require current manifest evidence coverage (PRs #56/#57).
- IMM5476 experimental PDF tooling and independently specified XFA readback checks (PRs #58/#59); scheduled observation diagnostics repaired in PR #60.
- One open experimental native Aspose PR #30 at inspection. No officially approved IRCC PDF autofill or submission workflow.

## Current review branch change
`fix/conditional-repeat-fail-closed-and-handoff`: fix repeatable conditional section logic in `app/form_manifest.py` and add regression cases in `tests/test_form_manifest.py`. An inactive section should not require an instance count; an unresolved parent must not be silently treated as zero; malformed counts fail even when hidden.

## Verification boundaries
- Code changes and tests committed for CI; full local test suite, Docker/Keycloak, real PostgreSQL RLS and Adobe/IRCC verification have **not** been run in this session.
- No approval of commercial PDF licensing, cloud deployment, official output, real-client usage or production security.
- Use the PR checks and their logs as verification evidence; do not infer test results merely from committed tests.

## Technical blockers
Official version-specific field coverage, vendor SaaS rights, Adobe save/reopen/validate and barcode/signature acceptance; complete table-level case RLS, threat assessment and production secrets/key management; realistic end-to-end RCIC practitioner workflow and competitor acceptance benchmarks.
