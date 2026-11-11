# ImmigrationOS autonomous development rules

1. GitHub main + merged PRs are source of truth. Read this file, README, IMMIGRATIONOS_MASTER_PLAN.md, IMMIGRATIONOS_CURRENT_STATE.md, IMMIGRATIONOS_NEXT_ACTIONS.md and relevant docs before coding.
2. Preserve existing FastAPI/PostgreSQL/OIDC/evidence-first architecture; make incremental work on a branch with a narrowly scoped PR.
3. Never use real clients or credentials. Public repo must never contain client PII, secrets, private licensed PDFs or commercial assets.
4. Fail closed on tenant/case authorization, unknown conditions, missing repeat counts, dirty/missing scans, conflicting facts, stale form revisions, PDF validation and missing professional approvals.
5. Official IRCC coverage is zero until independently verified. Internal subsets, synthetic PDFs, copied forms and experimental XFA are not accepted government outputs.
6. Require test evidence and review for every security/semantic change; unit tests are not PostgreSQL RLS or browser E2E certification.
7. Verify commercial license permits intended hosted SaaS usage before deployment. Adobe compatibility and IRCC validation remain independent gates.
8. After meaningful work, document exact SHA, tests that actually ran, unresolved blockers, and next executable task. Don't mark a PR merged or CI green without checking.
