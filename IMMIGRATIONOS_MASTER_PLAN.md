# ImmigrationOS — permanent product charter

Status: synthetic-data development, not production approved. GitHub main and merged PRs are authoritative; historical conversation context is not.

## Product
Secure multi-tenant evidence-centered Canadian RCIC practice-management SaaS. Benchmark observed, repeatable RCIC workflows against Officio, CaseEasy, ImmiPractice and immiBoard using documented evidence; do not claim superiority without trials.

## Required core path
Client onboarding → family/personal details → case and authorized engagement → documents → quarantined upload and independent malware clearance → human evidence verification → versioned, conditional form mapping → official form output and external validation → package/checklist → licensed RCIC approval.

## Non-negotiable gates
Tenant and case scoping; minimum privilege; provenance, immutable approvals and audit; identity/engagement authorization; source/revision pinning; conditional and repeatable field completeness; independent PDF readback and applicable Adobe/IRCC barcode checks; approved commercial vendor licensing; privacy, security, key management, backups and disaster recovery. Never use real client data until acceptance is documented.

## Verified coverage disclosure
Report separately: discovered official catalog entries, reviewed internal mappings, working official autofill, and independently validated official IRCC outputs. The current official autofill and accepted-validation counts are **zero**. A 24-field internal IMM1294/IMM5709 subset is not a completed application.

## Sequencing
1. Canonical records/evidence and safe conditional-repeatable form preparation.
2. Complete per-revision official field inventories and independent format/readback acceptance.
3. Secure case document/package assembly and RCIC approval.
4. Tasks, deadlines, communications, billing and trust accounting after core processing.
5. Production-hardening, legal and RCIC validation, and measured competitor benchmarks.

## Architectural decisions
FastAPI/PostgreSQL with FORCE RLS, OIDC, append-only evidence decisions, quarantined uploads and human approvals. Preserve existing working code and migrate with tests; do not replace established architecture for appearance or dashboard features.
