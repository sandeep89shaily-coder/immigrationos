# v0.2 release acceptance checklist

## Executable automated checks

- [x] API organization creation with owner membership (SQLite test)
- [x] One user cannot list another firm's client records (SQLite test)
- [x] Forged client ID cannot create cross-firm case (SQLite test)
- [x] Viewer cannot write, and cannot read audit (SQLite test)
- [x] Status transition guard rejects illegal transition (SQLite test)
- [x] Audit metadata excludes provided client name (SQLite test)
- [x] Duplicate organization slug and invalid slug rejected (SQLite test)
- [x] JWT bad signature, wrong audience, issuer and expired tokens rejected (unit test)
- [x] Production settings reject HTTP issuer and development DB (unit test)
- [x] Alembic migration executes in a SQLite migration smoke test

## Requires Windows Docker validation (NOT verified here)

- [ ] `docker compose up --build -d` starts Postgres, Keycloak and API.
- [ ] `python scripts/smoke.py` returns PASS against actual PostgreSQL and Keycloak.
- [ ] `python scripts/verify_rls.py` returns PASS against non-owner application role.
- [ ] Cross-firm access tested over live OIDC-token endpoints using distinct real test subjects.
- [ ] Confirm DB migrations are applied by migration role and application role has no dangerous privileges.
- [ ] Verify Keycloak realm import and JWT audience mapper in pinned Keycloak version.
- [ ] Verify restart, migration idempotence, and rollback procedure.

## Not yet suitable for production

- [ ] Production identity with MFA and verified staff onboarding
- [ ] Security review and external penetration test
- [ ] Privacy and data residency assessment
- [ ] Backup/restore and incident response drills
- [ ] Rate limiting and abuse prevention
- [ ] Data retention/deletion/export governance
- [ ] Document storage and evidence-based immigration case workflows
