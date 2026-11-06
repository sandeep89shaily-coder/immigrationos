# ImmigrationOS — Threat Model (first pass)

**Scope:** Firm-boundary API, PostgreSQL tenancy, Keycloak development JWTs and audit metadata. Refresh this before handling real client information and before each new data integration.

| Threat | Impact | Controls in v0.2 | Further mitigation required |
| --- | --- | --- | --- |
| Horizontal access across firms | Severe data breach | Membership checks, tenant-scoped queries, FORCE RLS, composite case-client FK, negative tests | Postgres adversarial testing, independent pentest, authorization coverage for all new endpoints |
| Stolen login/bearer token | Unauthorized access | JWT signature, expiry, audience/issuer checks | Production MFA, session binding, short token TTL, identity hardening, logout/revocation strategy |
| Incorrect firm membership | Role privilege escalation | Explicit roles; only creator receives initial owner membership | Verified invitation flow, approval, periodic role recertification |
| Injection into API/database | Data breach | ORM parameters and type validation | SAST, dependency scans, input threat modeling, external tests |
| Malicious client document | Malware / prompt injection | Document processing not yet enabled | Malware isolation, file-type verification, content-security pipeline, prompt injection tests |
| Audit log manipulation | Lost forensic evidence | Append-only trigger, no runtime UPDATE/DELETE grants | Central immutable log sink, secure timestamps, incident retention policy |
| Configuration/secret disclosure | Environment takeover | Separate roles, local-only development ports, `.env` excluded from git | Managed secrets, short-lived workload identity, rotation, no demo credentials outside development |
| Unsupported legal determination | Harmful advice or submission | No AI legal decision engine or submission | Approved rules, human verification, cited policy snapshots, release gating |
| Loss of data | Business interruption | Transactions, migrations | Automated encrypted backups, disaster-recovery drills, restore RTO/RPO testing |
| Abuse of public organization creation | Spam / account exhaustion | Auth required | Invitation/purchase gate, quotas, anomaly detection, rate limiting, onboarding verification |

## Release blockers

- Never connect real client data to the development Keycloak setup or public API over HTTP.
- No deployment with `ENVIRONMENT=development` or the example fixed passwords in a shared environment.
- Tenant isolation must pass PostgreSQL-level integration tests, not merely SQLite API tests.
- A privacy impact assessment, data retention schedule, breach response plan, DPA review, and RCIC review workflow must be documented and verified.
- OIDC/JWKS unavailability and signing-key rotation handling must be tested under failure conditions.
- Do not open internet-facing routes until rate limits, abuse controls, real monitoring and hardened production identity are implemented.

## v0.4 client portal changes

- Invitations are 48-hour bearer capabilities, SHA-256 hashed at rest, single-use, bound to an OIDC-verified email, and revokeable before acceptance. A secure out-of-band delivery channel is **not** yet implemented.
- Client identity has case-scoped grants only, no organization membership. PostgreSQL RLS has separate narrow portal policies; testing must include the actual limited PostgreSQL runtime role.
- Portal uploads are in quarantine and cannot be read, parsed, downloaded or approved by consultants until malware scanning is integrated. **Do not deploy this feature for real client files.**
- Open risks: no invitation delivery integration, MFA policy, malware scanner/CDR, rate limiting, independent penetration test, consent records, case-grant review, production object storage or identity lifecycle management.
