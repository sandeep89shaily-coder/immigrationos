# ImmigrationOS RCIC practice staff onboarding — verified invitations v1

**State:** Synthetic-data development prototype. The UI is not approved for real RCIC client data.

## Workflow

A firm **owner** can invite an administrator, consultant, assistant or viewer.
An **administrator** may invite consultants, assistants and viewers, but cannot
invite or promote another administrator. Neither role can invite an owner.
Ownership transfers and last-owner succession are intentionally out of scope.

1. Open **Practice team** in the consultant workspace (visible to owner/admin).
2. Enter a staff member's **identity-provider verified email** and the intended
   firm role. The server creates a cryptographically random 48-byte-entropy
   token, stores its **SHA-256 digest**, and shows the raw token **once**.
3. Deliver the token through a separately approved private channel.
   **No email, SMS or WhatsApp is sent** by ImmigrationOS.
4. The recipient authenticates through OIDC with the **matching verified email**
   (the web login asks for the \`email\` scope), then selects
   **Join an invited practice** and pastes the token.
5. A single transaction checks token digest, email, 72-hour expiry, revocation,
   no previous acceptance, no conflicting firm identity, and creates the
   **active firm membership** at the exact invited role.
6. The recipient becomes visible in the firm's roster, **without receiving
   access to any individual case**. A supervising professional must separately
   grant appropriate case access using the existing case permission workflow.
7. Owners/admins can change permitted roles or deactivate staff members.
   Staff cannot change their own role, and nobody can deactivate the owner
   through this API. Deactivation immediately removes firm membership access,
   including previously granted case access.

These operations record metadata-only audit entries; the token and the invited
email are not copied into general audit-event details.

## API

- \`GET /api/v1/orgs/{org_id}/staff/members\`
- \`GET /api/v1/orgs/{org_id}/staff/invitations\`
- \`POST /api/v1/orgs/{org_id}/staff/invitations\`
  with \`{"email":"fictional@example.test","role":"assistant"}\`
- \`POST /api/v1/orgs/{org_id}/staff/invitations/{id}/revoke\`
- \`POST /api/v1/staff/invitations/accept\`
  with \`{"token":"one-time-secret"}\`
- \`POST /api/v1/orgs/{org_id}/staff/members/{subject}/role\`
  with \`{"role":"consultant"}\`
- \`POST /api/v1/orgs/{org_id}/staff/members/{subject}/revoke\`

An unrelated firm principal cannot list another practice's roster.
Only owners may create or revoke admin invitations, promote an admin, change an
admin member's role, or deactivate an admin. There is no reactivation endpoint
for revoked memberships; re-enrolment requires separately reviewed recovery.

## PostgreSQL security boundary

Migration \`0013_verified_staff_invites\` establishes:

- A \`staff_invitations\` table with tenant FK, **FORCE RLS**,
  immutable target role/email/token fields and app-role permission to
  update *revocation columns only*.
- Membership \`verified_email\` and a unique
  \`(org_id, lower(verified_email))\` index for email-bound identities.
- Owner/admin-only membership roster reading, via a narrowly scoped
  migration-owned \`SECURITY DEFINER\` membership helper.
- A \`SECURITY DEFINER\` acceptance function that locks the invitation,
  checks the verified email claim, expiry and token hash, prevents token
  replay, and creates the membership **atomically**. The application runtime
  has no unrestricted membership UPDATE and retains the initial-owner-only
  INSERT policy added in migration 0012.
- Restricted migration-owned role-change and member-deactivation functions.
  They reject owner modification, self-modification and non-owner admin
  promotions/demotions.
- Audit entries only after successful acceptance, role update or revocation.

**Trust assumption:** OIDC signature/issuer/audience/expiry verification is
performed by the web API before it sets transaction-local DB session identity
and verified-email variables. DB functions do not independently validate
OIDC cryptographic signatures. Therefore there must be no untrusted direct
SQL access to the runtime database credentials or identity session variables.

The migration-only PostgreSQL role has \`BYPASSRLS\` in the isolated developer
topology so these constrained functions can check the staff directory. It must
be completely isolated from the runtime API role and protected by dedicated
credentials in a production architecture. This is still not a completed
security/privacy review.

## Acceptance tests

- Unit tests: one-use tokens, mismatch between invite email and OIDC email,
  missing verified-email flag, expiry, revocation, replay, admin/owner limits,
  role changes, deactivation, identity binding, cross-firm isolation and
  token-free audit metadata.
- PostgreSQL limited-role smoke: staff acceptance, direct self-enrolment
  denial, role restrictions, read controls, duplicate email and immediate
  membership revocation.
- Adversarial PostgreSQL verification: \`FORCE RLS\`, invitation immutability,
  absence of direct runtime role membership UPDATE, restricted function
  privileges and controlled migration owner.
- CI JavaScript syntax check includes \`app/static/staff.js\`.

## Outstanding before a real-client RCIC pilot

- No independent CICC licence verification or delegated-authority validation.
  A "consultant" membership role **does not confirm RCIC status**.
- No invite email delivery, second-channel confirmation, configurable SSO
  policy, optional MFA enforcement, enterprise SCIM onboarding or
  secure self-service account recovery.
- No production legal/privacy review, access-log monitoring, support
  impersonation safeguards or full **per-case PostgreSQL RLS** for every
  document/fact/task table.
- No controlled owner succession flow, no permission to change the last
  owner, no staff reinstate/transfer workflow.
- OIDC \`email_verified\` must be correctly mapped by the actual identity
  provider; merely entering an email string in the browser is insufficient.
- Staff email address/role details are visible to firm owners/admins and
  require normal privacy protections.
- The verified token is shown once in the current browser session. It must
  not be placed in analytics, URL query parameters, mail tracking links,
  debug logs or unapproved shared documents.

Next release gates: browser tests with actual Keycloak verified identities,
case-table-level SQL isolation, and source-backed RCIC legal deadline recording.
