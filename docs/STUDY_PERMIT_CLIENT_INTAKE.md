# Preliminary study-permit client questionnaire

**Development only. Fictional data. Not an official IRCC application, legal decision, or consent for external AI processing.**

## Official-source basis (reviewed November 6, 2026)

- [IMM 1294 official instructions](https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm1294.html): identity, passport, school, DLI, intended study, finances and related questions. IRCC lists June 2026 as the form's revision. This questionnaire is not a complete or validated IMM 1294 mapping.
- [Guide 5269 — applying for a study permit outside Canada](https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/guide-5269-applying-study-permit-outside-canada.html): LOA, PAL/TAL as applicable, checklist IMM 5483, region-specific instructions, additional forms and exceptions. Review the current official guidance for each applicant.
- [IMM 5483 document checklist](https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm5483.html): online applicants get a personalized checklist; the static PDF is not necessarily an upload requirement.

No automated determination is made about PAL/TAL exemptions, financial sufficiency, prior refusals, study permit eligibility or which government submission channel applies.

## Workflow

1. Staff creates a **study permit** matter with a fictional client email.
2. Staff issues a single-use portal invitation from the **Portal** tab.
3. Client signs in with a verified OIDC identity, accepts the invitation, and sees a **Preliminary study-permit intake** form.
4. Submission requires the stored development notice acknowledgement, a current template version and required identity fields.
5. Every submission creates an **immutable case-scoped revision**; prior submissions remain available to staff.
6. In the consultant workspace, the **Intake** tab shows the latest answers with per-answer **Accept to pending facts** or **Dismiss**.
7. An accepted answer creates a PENDING canonical CaseFact linked back to the questionnaire submission. A separate consultant-role verification remains necessary, and the IRCC preflight still requires source documents.
8. A new client revision blocks staff decisions on older submissions. Previously accepted facts are retained rather than overwritten; conflicts must be resolved explicitly.

## API

- `GET /api/v1/client/cases/{case_id}/study-intake`: active-grant client only.
- `POST /api/v1/client/cases/{case_id}/study-intake/submissions`: current template + notice acknowledgement + strictly validated answers.
- `GET /api/v1/orgs/{org_id}/cases/{case_id}/study-intake`: member staff with intake access.
- `POST /api/v1/orgs/{org_id}/cases/{case_id}/study-intake/{submission_id}/answers/{field_path}/decide`: consultant-role decision only.

Answers are never written to audit event details, which contain only submission identifiers, template metadata and counts.

## Security decisions

- Composite tenant/case foreign keys protect the submission and review tables.
- PostgreSQL FORCE RLS, a limited runtime role, verified-email OIDC grants and per-case authorization are all required.
- The runtime database role receives SELECT and INSERT only; submissions and decisions have no UPDATE or DELETE permission.
- A client's RLS read/insert policies additionally require their own active case grant and verified email context.
- Staff decisions require the latest submission for the case and an active staff review role.
- Input validation restricts field keys, data types, dates, choices, numeric bounds and answer size.
- Fictitious data only until consent workflows, retention, key management, hosting and independent security testing are completed.

## Outstanding to compete with Officio / CaseEasy

This module **does not** generate official IRCC PDF forms, capture all conditional form questions, provide multilingual intake, handle household interviews or support signed government submission packages. A production form adapter requires version-specific mapping and Adobe validation, and the practice needs legal/privacy review before collecting real personal data.

GitHub Actions runs unit tests, JavaScript syntax checks, PostgreSQL migrations/RLS verification and a synthetic client-to-consultant intake smoke test.
