# ImmigrationOS — Evidence-led product research and release gates

**Reviewed:** November 5, 2026. **Scope:** v0.4 portal, uploaded documents, professional oversight, and future IRCC handoff. The legal and privacy questions below require qualified review; this is engineering research, not legal advice.

## Official-source findings

1. **Multiple official IRCC channels:** The Authorized Paid Representative (APR) portal supports many application categories, but IRCC also provides a separate representative portal and permanent-residence route. The right pathway depends on application type; we must not assume universal third-party automation or a universal submission API. [IRCC APR sign-in](https://www.canada.ca/en/immigration-refugees-citizenship/corporate/partners-service-providers/authorized-paid-representatives-portal/sign-in-authorized-paid-representative-portal.html) · [APR portal guide](https://www.canada.ca/en/immigration-refugees-citizenship/corporate/partners-service-providers/authorized-paid-representatives-portal/user-guide.html).
2. **Applicant-only actions:** Some government pathways require applicants to create accounts or sign for themselves. For in-Canada refugee applications IRCC explicitly restricts paid representatives from opening a client's account, signing for the applicant, or using the applicant's credentials. Product routing must retain an applicant-action flag, and no model may impersonate an applicant. [IRCC guide](https://www.canada.ca/en/immigration-refugees-citizenship/services/refugees/asylum/start/in-canada.html).
3. **Representative authority and forms:** The IMM 5476 Use of a Representative form governs authorization, changes and withdrawal; the supported signature method can vary by submission route. Case representation status and consent must not be inferred from a user portal invitation alone. [IRCC IMM 5476](https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm5476.html).
4. **Professional obligations:** The federal CICC Code addresses confidentiality (s.28), client communication and deadline management (s.22), recordkeeping (s.37), and supervision (s.38). The software must retain immutable provenance and review decisions with restricted permissions. [Federal Code](https://laws-lois.justice.gc.ca/eng/regulations/SOR-2022-128/FullText.html).
5. **File-upload attack surface:** OWASP recommends allowlisted files, validating signatures, size and authorization checks, non-web-root storage, scanning and optionally content-disarm-and-reconstruct. A valid PDF signature does **not** prove the file is benign. [OWASP upload guidance](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html).
6. **Third-party AI processing:** The OPC's generative AI principles emphasize lawful use, meaningful consent where applicable, transparency, safeguards and documented processing relationships. Uploaded client documents should not be sent to a model provider based solely on accepting an invitation. [OPC AI principles](https://www.priv.gc.ca/en/privacy-topics/technology/artificial-intelligence/gd_principles_ai/).

## Architecture decisions for v0.4

- **Staff access and client access are separate:** a client identity is not a firm membership. Access is a revocable `portal_grants` record for one case only. Client principals never receive the firm CRM endpoints.
- **Invitations do not serve as authentication:** an opaque one-time secret is SHA-256 hashed at rest, expires after 48 hours, and is usable only by an authenticated identity with a provider-verified matching email. Tokens are not written to audit logs or embedded in query parameters.
- **PostgreSQL RLS complements API authorization:** tenant membership policies remain intact for staff; narrow client policies allow only the granted case, its requests and the client's own uploads. End-to-end PostgreSQL smoke tests are required on the limited app DB role.
- **Quarantine is default:** client uploads are encrypted in development, stored with a `quarantined` state, and blocked from download and extraction until scanning is independently integrated. Their existence blocks case readiness instead of satisfying document requirements.
- **No implicit legal authority:** inviting a client into the portal does not authorize an RCIC to represent that client to IRCC; form/signature/retainer approvals are separate workflow entities planned for later phases.
- **No government submission endpoint:** the preview contains only internal case preparation. Submission automation is a separate architecture and legal review.

## Acceptance matrix — v0.4

| Scenario | Automated check | Release acceptance |
|---|---|---|
| Valid, email-matched, one-time invite | SQLite API and PostgreSQL smoke | Pass |
| Wrong or unverified email | SQLite API and PostgreSQL smoke | Denied |
| Expired/revoked/replayed invitation | SQLite API | Denied |
| Access to unrelated firm or case | SQLite API and PostgreSQL smoke | Denied |
| Direct staff API from client identity | SQLite API and PostgreSQL smoke | Denied |
| Valid, synthetic client upload | SQLite API | Encrypted; quarantined |
| Invalid/mismatched file signature | SQLite API | Denied |
| Quarantined file staff download/extraction | SQLite API | Denied |
| Readiness if quarantine remains | SQLite API | Review required |
| Revoked portal grant | SQLite API | Access denied |

## Production blockers and future milestones

**P0 — production security (required before real client data):** independently reviewed authentication and verified email claim mapping; MFA policy; abuse/rate limiting; secure invitation delivery; consent and privacy records; malware scanner/CDR and isolated PDF parsing; a dedicated encrypted object store; backup/restore; retention and disposal; independent penetration and privacy reviews; adversarial RLS tests and case-specific audit controls.

**P1 — end-to-end consultant workflow:** document disposition after scanning; intake schema and consents; evidence graph provenance; required-document templates by application and rule version; secure messaging; client notification and case changes requiring professional sign-off.

**P2 — IRCC forms and regulatory change intelligence:** independently verified form mappings, revision hashes, supported government portal routing, source-grounded policy snapshots, versioned deterministic rules, and human approvals. Government credentials and client signing responsibilities must never be bypassed.

**P3 — measured competitive validation:** blinded synthetic/consented case trials comparing preparation time, manual corrections, form validation success, evidence traceability, failure rates, onboarding effort and pricing against competitor trials. Public feature checklists alone cannot prove superiority.

## Deliberately not claimed

The v0.4 preview does not provide a production client portal, automated compliance, actual malware scanning, legal assessments, IRCC submissions or complete form filling. All pilot data must be fictional until P0 controls pass independent validation.