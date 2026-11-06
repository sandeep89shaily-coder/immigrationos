# Case-specific document requirements and review (study permits)

**Status:** Development-only implementation. This is an operational, non-exhaustive preparation workflow, not legal advice, an IRCC checklist certification, government submission or official eligibility decision.

## In consultant workspace

Open a fictional study-permit matter and initialize its Application package. The **Supporting evidence worklist** now shows requirement statuses from a new case-scoped API. For conditional requirements (LOA or exemption evidence, PAL/TAL/CAQ or exemption evidence), an owner, administrator or assigned consultant can record one of two professional applicability decisions: `required` or `not_applicable`. A substantive note, confirmation of current official-source review, source URL, observed source date, timestamp, reviewer, and revision are recorded. Re-deciding appends a new revision; earlier attestations are preserved. Mandatory identity, passport and financial-support requirements cannot be marked exempt using this endpoint.

After personally reviewing a matching, scan-eligible, same-case document, a reviewer can attach an **accepted** or **rejected** immutable decision to that document and requirement slot. A previously reviewed file cannot be silently overwritten or re-approved in place; replacement files get new identities. The worklist distinguishes upload receipt from staff acceptance. Client-supplied documents in malware quarantine cannot be accepted. Rejected documents do not clear requirements.

A reviewed exemption suppresses *new* draft document requests from the existing evidence request workflow. It does not delete already created requests and does not settle changing legal requirements. No messages are automatically sent.

## Technical delivery

- `app/requirement_models.py`: append-only source-pinned applicability decisions and same-case immutable document reviews.
- `alembic/versions/0017_document_requirements.py`: foreign keys, unique decision revisions, role-limited inserts, PostgreSQL FORCE RLS and restricted grants.
- `app/document_requirements.py`: version-guarded decisions, case/type/malware checks and a read-only aggregate worklist.
- `app/static/application_package.js`: consultant applicability and document review controls.
- `app/evidence_matrix.py`: avoids requesting requirements professionally marked not applicable.
- `tests/test_document_requirements.py`: applicability transitions, review gating, same-case checks and scoped access.

## Guardrails and outstanding work

Sources were observed on 2026-11-06 and must be checked against current official guidance. Requirements can vary by nationality, study program, province, application location and exemptions; this catalogue does not claim all variants. A staff-reviewed document is not accepted by IRCC. Current IRCC PDF autofill, validation and submission are **not** implemented.

Next work: richer country/program-specific requirements, applicant-specific exemption evaluation with detailed evidence, document review supersession workflow, application-level approval and audited final handoff; one official form must be technically and operationally validated before production.
