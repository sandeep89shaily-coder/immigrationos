# ImmigrationOS Workspace v0.4 — Client portal development preview

**Status: functional development preview, not a commercial or production-ready immigration platform. Fictional data only.**

A real FastAPI/PostgreSQL case-and-evidence workspace with OIDC sign-in, tenant-isolated records, a consultant dashboard, encrypted local development uploads, traceable fact suggestions, discrepancy detection, human review, internal form worksheets and task tracking. The code evolves the previously delivered v0.2 foundation; it does **not** reuse the v0.1 single-file Flask demo.

## New in v0.4: verified-identity client intake

- Consultant case → **Portal** tab: create document requests and single-use (48h) email-bound invitations. Tokens are displayed once and **not sent automatically**.
- Client opens **http://localhost:8000/client**, signs in with OIDC + PKCE, enters the invitation token and sees only their explicitly granted case.
- Development identity: `client.demo` / `DemoOnly-Client2026!` uses the fictional verified email `sample.person@example.test`; add a fictional client with that same email in the consultant workspace to create an invite.
- Client document uploads are encrypted in the development store and **quarantined**; no access to extraction/download until a real malware scanning system is designed and integrated.
- Staff can revoke portal access; a client cannot access staff CRM APIs or another client's cases. Client access requires an identity-provider-verified email, not a self-typed email.
- This is not yet production-ready, and **no real client information should be used**. No emails are automatically sent.

## Try the complete Windows development preview

1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) with WSL2 and start it.
2. Extract **all** ZIP files to a folder (do not run inside the ZIP).
3. Double-click `RUN_WINDOWS.bat`; Docker will build and launch PostgreSQL, Keycloak, the migration process and API/UI.
4. Open **http://localhost:8000/app** in your browser. The launcher opens this automatically.
5. Select **Sign in** and use the **development-only** account `rcic.demo` / `DemoOnly-ChangeMe2026!`.
6. Select **Create practice**, supply e.g. `Fictional Immigration Partners`, slug `fictional-partners`.
7. From the Overview page, click **Load synthetic sample**. This generates 3 *fictional* cases, 3 clients, tasks and an evidence conflict. Explore matters, the review queue and the internal worksheet.
8. Within a matter, select **Documents → Upload** and choose a fictional `.txt`/PDF/PNG/JPEG (≤ 8 MB). For text, test with the bundled `sample_data/synthetic_employment_letter.txt`. Select **Extract** to generate source-grounded *unverified* suggestions; **Suggestions → Accept** records a pending fact; **Evidence → Verify** requires a separate professional-role decision.
9. Check `/docs` for the REST API and `/health/live` for basic process health.

First build requires internet access to obtain container images and Python packages. The browser access token is intentionally held in memory, so reloading may require a fresh sign-in. Docker/Keycloak end-to-end testing was not possible in the authoring environment and requires local verification.

**Critical:** do not enter real names, passports, immigration records, bank documents, client messages, or other personal data. This is a synthetic-data development environment.

### Troubleshooting

```powershell
docker compose ps
docker compose logs -f api
docker compose logs -f keycloak
docker compose logs -f migrate
```

If sign-in fails, verify the Keycloak container is healthy and retry the local development login. Port 8000 is the web workspace/API, 8080 is Keycloak, and 5432 is PostgreSQL. All are bound to localhost. Avoid `docker compose down -v` unless you intend to **delete both the local database and the development document volume**.

### Run automated tests without Docker

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[test]"
pytest -q
```

The 18 test cases cover access rules, tenant isolation, case state changes, review gates, task handling, encrypted synthetic upload/download, extraction, source matching, suggestion approval, internal worksheet mapping and synthetic sample creation. Tests use SQLite for speed; SQLite cannot prove PostgreSQL row-level security.

### PostgreSQL row-level security validation

With Docker running:

```powershell
$env:RLS_APP_DATABASE_URL = 'postgresql+psycopg://immigrationos_app:dev_only_app@localhost:5432/immigrationos_dev'
python scripts/verify_rls.py
python scripts/smoke.py
```

These scripts verify baseline RLS policies and exercise the local stack with synthetic data. Additional real PostgreSQL and browser integration testing is **required** before any pilot.

## Implemented capabilities

| Domain | Functionality |
|---|---|
| Authentication | Keycloak development realm; OIDC authorization-code PKCE browser client; RS256 JWT verifier |
| Firm isolation | Org membership RBAC, composite tenant FKs, PostgreSQL FORCE RLS, limited application DB role |
| Practice management | Clients, matters, application categories, case stages, overview metrics |
| Workflow | Firm/case tasks, deadlines, explicit completion, review queue |
| Evidence | Case documents, source-linked facts, review status and immutable audit metadata |
| Document handling | Development-only encrypted file storage (Fernet), content hashing, MIME signature checks, 8 MB limit |
| Extraction | Conservative deterministic labelled-field text/PDF parser; page/excerpt provenance; human acceptance required |
| Optional experimental AI | OpenAI Responses API structured-output adapter, **disabled by default**; source-anchored candidates only; *never approved for real data* |
| Conflict detection | Distinct values for same canonical field cause review issues; a human must document resolution |
| Form mapping | Demo study/work permit **internal worksheets**, using only verified facts; these are **NOT official IRCC forms** |
| Operations | Dashboard, client list, matter workspace, evidence and document views, task list, review queue, audit view |
| Test fixtures | One-click synthetic seed; bundled fictional sample documents |

### Experimental external AI (optional; NOT for real documents)

The model integration is implemented as a disabled, opt-in adapter using the OpenAI Responses API with structured JSON output. Configure a development `.env` consumed by Docker Compose:

```dotenv
EXPERIMENTAL_AI_ENABLED=true
AI_MODEL=<a model enabled for your API account>
AI_API_KEY=<your API key>
```

After Docker restart, the Documents tab shows an **AI review** action. It asks for explicit confirmation before a sample document is sent to the configured provider. Model output is validated against the original document, and ungrounded results are discarded. Fact acceptance and verification remain human-controlled. API use may incur charges. **Do not enable this on real client data** until contractual, security, privacy and residency reviews are completed.

No API credentials are included in the project. The bundled Docker Fernet key is a **public development-only test key**, not suitable for storing sensitive or real information.

## Architecture

```text
Browser OIDC PKCE login --> Keycloak developer realm
       |
Consultant workspace (bundled static UI; future production UI: Next.js/TypeScript)
       |
FastAPI, JWT verification, member role/tenant context
       |
PostgreSQL (organizations, clients, cases, documents, facts, proposals, issues, tasks, audit)
       |
Encrypted local dev document store --> deterministic parser / optional isolated AI gateway
       |                                          |
       +------------------- human review & audit <-+
```

This release intentionally uses a dependency-light web UI for a working preview rather than an untested Next.js bundle. Before production we would move to the approved Next.js architecture, finalize a case-specific permission model, production OIDC deployment, secure object storage and private asynchronous document workers.

## Major NOT-yet-built capabilities

- Actual official IRCC form mappings/generation, barcode validation and compliant handoff to government portals.
- Real client self-service portal, invitation and consent flow, messaging, client-upload security.
- Financial ledgers, trust accounting, e-signatures, invoicing and payment processing.
- Official IRCC regulatory monitoring, legal rule versioning and validated eligibility logic.
- Production-ready malware/OCR scanning, object storage, key management, retention/deletion, backups, incident response, tenant and case permission policy, MFA enforcement, compliance and security audits.
- RCIC professional licence verification and the legal/professional rules required before reviewer roles can be treated as licensed-appropriate.
- Full browser/Keycloak/PostgreSQL integration validation, independent penetration test, real-world benchmark against Officio/CaseEasy/immiBoard/ImmiPractice.

**This is a meaningful product build, not a claim that ImmigrationOS already beats established commercial products.** No production client case should be processed with v0.3.

## Project layout

- `app/` API, database, evidence intelligence, internal worksheets, development document encryption and frontend assets
- `alembic/versions/` three schema migrations, including PostgreSQL tenant policies
- `infra/keycloak/` local dev realm with browser PKCE and CLI clients
- `infra/postgres/` limited database roles
- `sample_data/` explicitly fictional test files
- `tests/` API, isolation, parsing, review and mapping tests
- `scripts/` smoke tests and PostgreSQL security checks
- `docs/` architecture, risk and acceptance references carried forward from v0.2
- `RUN_WINDOWS.bat` and `CHECK_WINDOWS.bat` for Windows users

## v0.5 — Optional development malware-scanning pipeline

ClamAV is **opt-in** because its signature engine may need roughly 4 GB RAM. The official `clamav/clamav:stable` image runs only on an internal Docker network and does not publish its unauthenticated port to the host. The adapter uses ClamAV `zINSTREAM` framing with a strict 8 MB input bound and fail-closed handling. It does not send a filename, path or identifying client metadata to the scanner.

To enable **fictional-data scanning only** on Windows PowerShell:

```powershell
$env:CLAMAV_ENABLED='true'
docker compose --profile scanner up -d --build
```

ClamAV may take time to initialize and update signatures. If unavailable, the scan API returns HTTP 503 and keeps the document quarantined. In the consultant matter's **Portal** tab, use **Scan** on a quarantined synthetic client upload. A clean verdict releases it from quarantine for normal **development-only** evidence extraction; a malware-detection verdict rejects it, and unclear errors never release it. Virus scanning alone is not equivalent to safe PDF parsing/CDR. Production uploads remain disabled and require independent privacy/security review, durable scan workers, retention rules and monitoring.

References: [ClamAV INSTREAM protocol](https://docs.clamav.net/manual/Usage/ClamdProtocol.html), [official ClamAV Docker guidance](https://docs.clamav.net/manual/Installing/Docker.html), [OWASP file upload safety](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html).
