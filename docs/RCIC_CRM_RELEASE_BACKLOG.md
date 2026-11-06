# ImmigrationOS — RCIC CRM Product Backlog and Release Gates

**Derived from:** [Competitor workflow benchmark, 2026-11-06](RCIC_COMPETITOR_WORKFLOW_BENCHMARK_2026-11-06.md)  
**Status:** Architecture/product backlog for implementation; not shipped functionality.

## Decision

Keep **form factory + evidence engine** as the core differentiator. Add the **minimum complete RCIC practice operating workflow** around them. Avoid breadth-first clones of competitors' dashboards. Ship vertical slices that let a fictional case move through the entire stage, with role, provenance, financial and regulatory controls and PostgreSQL negative tests.

**Meaning of priority**:
- **P0**: needed for a credible, legally reviewed RCIC practice trial or for platform trust/safety.
- **P1**: important competitive parity and time-saving features; release after critical flows.
- **P2**: growth, integrations and differentiation after operational foundations prove reliable.

All regulatory interpretations need RCIC/accountant/privacy counsel review before live deployment.

## P0 requirements — order and acceptance

### RCIC-CRM-001: Inquiry, consultation, and client conversion

**Entities:** Prospect, ContactIdentity, ProspectInteraction, ConsultationBooking, ConsultationAgreementVersion, ConversionLink.

**Acceptance**:
- Lead is distinct from client; source, collection purpose, outreach permission and assigned person recorded.
- Duplicate leads are suggested for review; merge is explicit, attributed and reversible within retention policy.
- Firm can book a consultation and generate a versioned written consultation agreement, signed/acknowledged before an initial regulated consultation as applicable under Code s.23.
- Signed PDF and timestamps retained; authorization checks keep prospect data from unrelated firms.
- Conversion to client/case preserves original lead events and agreements; immutable metadata audit.
- **Negative tests:** unsigned/expired agreements cannot silently satisfy gate; non-member cannot access prospects; role cannot merge without permission.

### RCIC-CRM-002: Case assignment, milestone templates and critical deadlines

**Entities:** MatterAssignment, ProgramWorkflowVersion, Milestone, TaskTemplate, Deadline, DeadlineEvidence, ReminderDelivery.

**Acceptance**:
- Study permit, work permit, visitor, PR, sponsorship and consultation-only routes support different **configurable versions**; no arbitrary count of 15 phases hardcoded into every program.
- Case manager can assign staff and supervising professional; case-level access requires membership **and** assignment/case authority.
- A legal/IRCC deadline records source document/event, timezone, actual date and editor. No unsupported date inference.
- Critical deadline notifications test retries, idempotency, acknowledgment and escalation to backup RCIC.
- Case timeline shows state changes, failed reminders and overdue counts. Deadline template changes do not silently rewrite existing due dates.
- **Negative tests:** across-office data leakage, overdue reminder skip, invalid role impersonation, closed-case modification.

### RCIC-CRM-003: Engagement, conflicts, service agreement and e-sign

**Entities:** ConflictCheck, EngagementScope, RetainerTemplateVersion, ServiceAgreement, AgreementSigner, SigningEvent, Amendment.

**Acceptance**:
- Before providing additional regulated consulting services, record Code s.24 preconditions: verified client contact, prior representative situation, assessed conflicts/scope, responsible licensee.
- Generate client- and program-specific agreement with provision checkboxes for required Code fields and an immutable template snapshot.
- Present draft, obtain signed copy, ensure applicant/RCIC acceptance and store version/signer audit.
- Material scope or fee changes use separately signed written amendment; old signed version never overwritten.
- Any form automation, client message or case work status is clearly separated from legal service authority; qualified reviewer controls exceptions.
- **Negative tests:** edited signed document checksum, retroactive event edits, unsigned agreement treated as completed.

### RCIC-CRM-004: Unified matter timeline and reliable communication

**Entities:** CaseEvent, Conversation, Message, MessageParticipant, AttachmentRef, DeliveryAttempt, ChannelConsent.

**Acceptance**:
- Email/portal correspondence and manual notes relate to correct client/case with certainty and review queue for ambiguous matches.
- Distinguish **internal-only notes** from client-visible messages; staff roles cannot accidentally send confidential internal content.
- Outbound case updates are written, timestamped, logged and deliver only after authorized reviewer release.
- Email retries are deduplicated, failures visible; no automatic lawyer/RCIC legal advice from AI.
- WhatsApp/SMS connectors are optional, require appropriate consent/business account and separately reviewed privacy safeguards.
- **Negative tests:** cross-client recipient leak, duplicate webhooks, attachment scope escape, sensitive content in notification previews.

### RCIC-CRM-005: Invoice + trust-subledger architecture

**Entities:** Invoice, InvoiceLine, TaxCode, Payment, Receipt, ClientTrustAccount, TrustJournal, TrustAllocation, BankReconciliation, Refund.

**Acceptance**:
- Ledger postings use immutable double-entry rules; firm operating money, client advances held in trust, earned fees and disbursements remain distinct.
- Each trust posting balances; client subledger and bank-account control totals reconcile; negative balances and unauthorized transfers fail closed.
- Invoice-before-withdrawal logic and required timing follow Code s.32 and related current rules after legal/accounting validation.
- Every refund, partial payment, disbursement and adjustment is auditable with approvals and supporting records; no direct table edits to financial history.
- Bank/payment gateway integration is **not** implemented before accurate offline reconciliation with synthetic transactions.
- **Negative tests:** cross-client spending, unbalanced journal, insufficient trust funds, duplicate payment webhook, assistant changing trust balances.

### RCIC-CRM-006: Closed-file governance, export and absence continuity

**Entities:** ClosureChecklist, ClientPropertyReturn, FinalAccountStatement, FileRetentionPolicy, LegalHold, ExportBundle, BackupRCICAppointment.

**Acceptance**:
- Closed-file transition enforces confirmation of client property return, fees/refunds accounting, client notification and representative status (Code s.36 subject to circumstances).
- Record final invoice, trust refund and handover materials with immutable evidence; block deletion when retention or legal hold applies.
- Client export includes agreement versions, correspondence, evidence hashes, received/submitted documents, invoices and review history.
- PUA/continuity feature tracks designated backup access policy, verified disclosure events and succession handoff without exposing all files by default.
- Retention clock and deletion policy require RCIC/legal verification and explicit opt-in; do not silently destroy client files.

### RCIC-SEC-001: Live-data safety gate (parallel, release-blocking)

**Acceptance**:
- Production MFA/identity, verified RCIC role/credentials process, privacy assessment and third-party pentest completed.
- Encryption/key lifecycle, malware scanning on every entry path, data residency contractual analysis, backups and restore drills, staff offboarding and breach plan reviewed.
- Row-level authorization covers staff, branches, case assignment, clients, attachments, communications, finances and exports.
- No real PII introduced until the explicit, recorded production acceptance decision.

## P1 parity priorities

| ID | Capability | Testable outcome |
|---|---|---|
| CRM-101 | Complete family/person/employer profile | Names, relationships, residence, education/work/travel timelines reusable across cases, versioned and consent-bound; no inappropriate co-applicant data sharing |
| CRM-102 | Conditional intake builder | Client sees only pertinent follow-ups; schema changes never corrupt answered historic questionnaires |
| CRM-103 | Document checklist/expiry control | Required/optional/conditional document statuses, version history, expiring passports/permits and source-specific request messages |
| CRM-104 | Firm-wide searches and case tracker | Filter by client, program, consultant, case number, deadline, status and UCI with tenant-safe result counts |
| CRM-105 | Portal status and secure updates | Client sees permitted milestones, statuses and messages with notification preferences and no sensitive email subjects |
| CRM-106 | Reusable letter/document templates | Per-firm branded versions, evidence-backed variables, RCIC pre-send review and downloadable audit export |
| CRM-107 | Management reporting | Lead conversion, consultations-to-engagement, days to first form draft, collection lag, overdue deadlines, outstanding accounts, case throughput |
| CRM-108 | Data migration and portability | Read-only import preview, deduplication, ID crosswalk, safe rollback, CSV/ZIP export under verified authorization |

## P2 growth and integrations

- Google/Microsoft calendar integration with conflict handling, no hidden overwrite.
- Outlook/Gmail authorized mailbox connection and safe inbound message association.
- Stripe/LawPay/Interac integration after financial posting/reconciliation is correct.
- WhatsApp Business Platform and SMS with consent, approved templates and deliverability audit.
- Employer module: corporate clients, HR cases, job offers, LMIA/economic programs.
- Multi-office franchise configuration, custom branding and localization EN/FR (with professional translations).
- Document PDF merge/compress under **current** IRCC portal-specific file limits; never hardcode one limit for all application types.
- Optional AI triage, grounded letter drafts, cited policy-impact queue and quality-assurance report—reviewed by accountable licensed professional.

## Three next vertical slices (recommendation)

1. **Prospect → consultation agreement → client conversion.** Unlocks actual CRM entry and regulatory record continuity.
2. **Client → versioned retainer → signed engagement → case assignment.** Enables a defensible start-of-work gate.
3. **Assigned matter → deadline/milestone/communication timeline → supervised draft-form task.** Connects current evidence engine with the daily working life of RCICs.

Build alongside the **IMM 5476 verified official form adapter** and wider approved form mapping work, not as a replacement for it.

## Benchmarks for pilot RCICs

Use the *same synthetic scenario* on competitor demo and ImmigrationOS:
- Time from lead to consultation agreement to signed retainer to case.
- Number of repeated data entries across applicant, spouse and dependent.
- Time to create an accurate document request and update evidence status.
- Time to prepare, review and validate the actual current form.
- Time to notify a client of an ADR and set the response deadline.
- Time to produce a client statement showing operating invoices vs trust.
- Time to export or close a file with proof of all required actions.
- Number and severity of incorrect data, missed steps and access-control failures.

**Winning criteria:** case-time savings must not be achieved by skipping professional review, legally required records, trust controls, document integrity or client confidentiality.

## Explicit non-goals for now

Do not create a generic AI chatbot, a large marketing website, a superficial dashboard-only redesign, fake "400 forms supported" counters, unvalidated eligibility engines, fake official portal automation, or direct banking transactions before accountants validate the ledger.
