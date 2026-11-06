# ImmigrationOS — RCIC CRM & Workflow Competitor Benchmark

**Research date:** 2026-11-06  
**Decision owner:** Product/engineering  
**Status:** Source-backed public-claims audit, **not** hands-on product verification.  
**Scope:** Canadian RCIC practice operations other than official form-generation engineering. Form factory remains the active commercial product milestone.

## Executive conclusion

Do not build a generic contact-management CRM. Build a **matter-centric RCIC operating system** with a linked prospect -> client -> engagement -> matter -> evidence -> form -> filing -> post-filing -> closure lifecycle. A common client/person/household record and event ledger underpin every stage. Keep immigration legal decisions and official submissions human-controlled.

**Competitive reality:** Officio's 400+ form claim is important, but established tools are also selling a complete operational suite: consultations, retainers, document collection, messages, workflows, invoicing/trust, dashboards and business continuity. The most defensible differentiator for ImmigrationOS is **traceable, versioned evidence-to-form quality control** plus RCIC-native lifecycle automation, rather than a larger pile of CRM screens.

## Evidence and interpretation rules

- "Advertised" = a vendor describes a feature on its own public website. This study does **not** confirm performance, legal compliance, availability for a specific plan, user satisfaction or production reliability.
- "Coming soon" or planned functionality is *not* counted as available.
- Vendor names are distinct: **Immicase** is at \`immicase.ca\`; **ImmCase** is at \`immcase.com\`.
- The CICC Code is a regulatory requirement for licensees, **not** a claim that any vendor or ImmigrationOS has regulator certification.
- References below are public pages inspected 2026-11-06. Recheck plans and feature status before a pricing or sales decision.

## Competing products — operational positioning

| Product | Advertised workflow strengths | Important nuance |
|---|---|---|
| **Officio** | Prospect assessments/scoring, multilingual web questionnaires, client conversion, automated tasks, integrated email/calendar, client portal, file numbering, time tracking, billing/trust accounting, multiple offices, staffing roles, unplanned absence planning, employer module and >400 common-field form mappings. | Vendor claims "400+" across federal, Quebec, PNP, Service Canada, citizenship and refugee forms. This is not a third-party validation of actual submission-ready form count. [Officio CRM](https://officio.ca/immigration-crm.html) · [10-step workflow](https://officio.ca/immigration-software.html) |
| **CaseEasy 360** | Intake questionnaires, client portal, PDF autofill, lead capture/conversion, retainers/e-signatures, email/chat templates, appointment scheduling, invoicing/card payments, trust reconciliation and reports, expiring documents, PDF merge/compress, optional employer management and integrations. | Public pricing page labels **IRCC Portal Autofill** coming soon and separately advertises a PDF autofill feature. Plan/seat/storage limits apply; $99 Starter, $199 Advanced as advertised on research date. [Pricing & features](https://caseeasy.ca/Home/Pricing) |
| **ImmiPractice** | Lead ingestion (Meta/WhatsApp/forms), calling queue, consultations, verified intake, retainers with e-signature, case filing workflow, document checklists, client portal, integrated WhatsApp inbox, invoices/installments, branch-based roles and analytics. | Says **trust accounting, online client card payments, and two-way calendar synchronization are not available**; an accountant/external system remains necessary. Claims $89/month Standard, unlimited users/branches, but verify contract. [Product](https://immipractice.com/product/) · [Feature inventory](https://immipractice.com/features/) |
| **Immicase** | Detailed 15-milestone case lifecycle, prospect pipeline, 11 stream options, case tracker, activity timeline, configurable checklists and task templates, unified messages, client portal, consultations/video, invoices/Stripe, double-entry trust ledger, reports, backups and firm-specific role overrides. | Vendor describes a **10-form**, edition-dated IRCC mapping catalog, not 400. "AI" is an optional add-on. Source also lists some Gmail/calendar/QuickBooks integrations as coming soon. [Detailed features](https://www.immicase.ca/features/) · [Pricing](https://www.immicase.ca/pricing/) |
| **ImmCase** | Unified firm operations including SMS, business phone, WhatsApp/video, forms, document management, sales quotes and invoicing, multi-tax/currency, case tasks, calendars, file synchronization, custom modules/roles and branding. | Public feature descriptions do not substantiate a verified form count or regulated trust-ledger implementation. [Features](https://www.immcase.com/features/) · [Overview](https://www.immcase.com/) |

**No assumption** is made about products whose features could not be substantiated from a first-party product page (e.g., uncertain/ambiguous vendor names).

## Workflow feature clusters customers will expect

| Area | Competitor evidence (representative, vendor-advertised) | ImmigrationOS current repository baseline | Product requirement |
|---|---|---|---|
| Lead and prospect CRM | Officio prospect scoring, CaseEasy lead forms, ImmiPractice channel-based pipeline, Immicase Kanban funnel | **Absent** | Contact/lead separation, lead source, duplicate matching, owner, stage, consent, follow-up, assessment-not-legal-advice, conversion with audit |
| Consultation scheduling | Officio/Calendly; CaseEasy booking and payment; ImmiPractice scheduling; Immicase booking/video | **Absent** | Calendar availability, consultation slots, written consultation agreement before a regulated initial consultation, payment and reminder linkage |
| Conflict checks, retainers and e-signatures | ImmiPractice retainers with e-sign; CaseEasy agreement builder; Immicase retainer templates | **Absent** | Engagement scope and conflicts review, consultant identity, fee/disbursement schedule, template versioning, client signature, amendments with immutable snapshots |
| Client/contact/household | All surveyed competitors organize client/case; ImmiPractice reuses a client record | **Basic** clients; **no family/household model** | Person vs client vs applicant vs employer vs family relation; structured addresses, travel, employment and education histories reusable across matters |
| Case lifecycle and routing | Immicase 15 milestones, case stages/stream-specific workflows; Officio tasks/reminders | **Basic** case status and tasks | Customizable, versioned program-specific milestones; roles, owner, deadline policies, case numbering, submission and outcome records |
| Task/deadline operation | Officio reminders; Immicase milestone-generated tasks and escalation | **Basic manual tasks** | Critical legal deadline vs soft task; timezone; recipient and escalation; acknowledgement; missed-deadline log; no fabricated deadlines |
| Client portal + questionnaires | CaseEasy, ImmiPractice, Immicase, Officio | **Development-only** portal invitation, scoped grants, one preliminary study-permit questionnaire | Client-facing multilingual status, client-upload request/expiry, review feedback, consent, secure threads, permissions for related applicants |
| Document workflow | Checklists, versions, expiries, merge/compress, client portal across surveyed firms | **Partial** encrypted test storage, requests, quarantine/scan, evidence extraction | Multiple versions, expiry/replacement, checklist applicability, secure download, malware scan, client feedback, controlled export and IRCC size constraints |
| Communications | Officio email filing; Immicase unified inbox/timeline; ImmiPractice WhatsApp; ImmCase SMS/phone/video | **Absent** unified inbound/outbound channel | One secure case timeline, reply threading, email/SMS/WhatsApp with consent, notification controls, confidential/internal visibility, delivery/error audit |
| Billing, invoices, trust | Officio + CaseEasy trust modules; Immicase double-entry; ImmiPractice fee ledger but **not** trust accounting | **Absent** | Fee agreements, stage invoices, taxes, disbursements, receipts, client trust liability subledgers, bank reconciliation and restricted financial roles |
| Team and office access | ImmiPractice seven roles/branch separation; Immicase five roles/custom grants | **Partial** firm membership roles + PostgreSQL RLS; no production staff invite/branch/case assignment | Staff invitations, office separation, assignment-scoped access, designated supervising RCIC, role change and offboarding, immutable access audit |
| Reporting/business operations | Officio advanced search; CaseEasy reports; Immicase overdue/deadline KPIs; ImmiPractice funnel analytics | **Basic** case/task counts | Cash vs trust, collections, lead conversion, days-to-filing, unanswered client requests, overdue critical deadlines, case throughput and export |
| Regulatory quality & closure | Officio unplanned-absence features; vendor compliance marketing | **Partial** evidence reviews and basic case close status | Complaint/error workflows, file return, final accounting/refunds, record retention/export, PUA continuity plan, privilege review, breach response |
| Integrations and migration | Officio Google Drive/Dropbox/Calendly; CaseEasy Zapier/QuickBooks/Stripe; Immicase Outlook/Stripe/Drive | **Absent** production connectors/migration | CSV import, evidence reconciliation, mail/calendar, accounting, payments, export/backup, scoped connectors with explicit consent and audit |

**Caveat:** repository status is based on currently checked-in models, routes and architecture docs, not a completed real-client end-to-end acceptance run. Feature presence does not mean production readiness.

## What a realistic RCIC practice workflow must do

### A. Enquiry → consultation → engagement

1. Capture lead with lawful collection purpose and source; deduplicate without merging unrelated people; assign staff.
2. Record call/email and follow-up date in one timeline. Booking flow creates a consultation record.
3. Generate a **written consultation agreement before the initial consultation**, with the information required by Code s.23, subject to applicable statutory exceptions.
4. Capture notes and any assessment as professional-authored. Keep marketing projections distinct from legal opinions.
5. Before additional consulting services: check prior representation and conflicts, identify responsible licensee, generate a versioned **written service agreement** satisfying Code s.24; collect signatures and supply client a copy.
6. Convert lead to client/case without losing consent, messages, agreement evidence or financial history.

### B. Active matter → prepare → submit → monitor

1. Assign RCIC and case team; set program and filing route.
2. Create versioned checklist and conditional questionnaire. Collect source documents with request status and expiry.
3. Quarantine/scan submissions, record document version, classify and extract **proposed** facts.
4. Reconcile contradictions and require human fact verification; stage official form fields with source provenance.
5. Track real deadlines (IRCC requests, biometrics, medicals, court/tribunal dates and form-expiry reviews) with owner/escalation. Never infer a deadline without a supported source.
6. Draft and professionally review submission package; explicit signoff on version, checklist, documents, signatures and forms.
7. Record submission receipt/portal evidence and timestamps **without implying an official submission integration exists**.
8. Record every external update, ADR, decision and client notice on an immutable case timeline.

### C. Billing → close → retain

1. Separate invoice receivables from client trust liabilities. For advance funds, Code s.32 requires regulated handling; do not treat a Stripe receipt as automatic authority to withdraw trust funds.
2. Confirm required invoice before transferring funds out of trust; keep per-client subledger and reconciliations.
3. At completion/termination, generate file closing checklist: outstanding client property, final invoice, account/refund, client notices, successor handoff and representative withdrawal as applicable.
4. Enforce governed retention/hold/destruction policy, secure export, audit evidence and PUA/continuity operations.

## Current regulatory source anchors

These are **product legal requirements to obtain professional/legal review**, not a certification claim.

- **Code s.22:** deadlines, efficient case handling, timely written status notifications and proper submission responsibility — [Justice Canada](https://laws-lois.justice.gc.ca/eng/regulations/SOR-2022-128/page-2.html).
- **Code s.23:** written consultation agreement before initial consultation; required terms and client copy — [Justice Canada full text](https://laws.justice.gc.ca/eng/regulations/SOR-2022-128/FullText.html).
- **Code s.24:** written service agreement before further consulting work; extensive terms, prior-representative check, written amendments — [Justice Canada s.24](https://laws-lois.justice.gc.ca/eng/regulations/SOR-2022-128/section-24.html).
- **Code s.28:** confidentiality in relation to present and former clients, with continuing obligations and disclosure limits — [Justice Canada](https://laws-lois.justice.gc.ca/eng/regulations/SOR-2022-128/page-2.html).
- **Code s.30:** specified procedures for material error/omission — [Justice Canada s.30](https://laws-lois.justice.gc.ca/eng/regulations/SOR-2022-128/section-30.html).
- **Code ss.31–33:** fee/disbursement requirements, advance funds in approved trust account and invoice-before-withdrawal — [Justice Canada full text](https://laws.justice.gc.ca/eng/regulations/SOR-2022-128/FullText.html).
- **Code s.36:** completion/termination, return of property, accounting, final invoice/refund within prescribed timelines — [Justice Canada](https://laws-lois.justice.gc.ca/eng/regulations/SOR-2022-128/section-36.html).
- **PIPEDA:** privacy safeguards, accountability, and breach notification/reporting where the statutory threshold applies — [Justice Canada](https://www.laws.justice.gc.ca/eng/acts/P-8.6/FullText.html).
- **CICC file-management and client-account rules:** confirm currently effective instruments and their retention/reconciliation periods with an RCIC and counsel before implementing automatic deletion or claiming compliance. Older documents may be superseded; retain linked revision and effective date in rules.

## Benchmark: what to beat, not what to copy

**Critical parity:** lead conversion, retainer workflow, firm-level inbox/timeline, real deadline management, client portal, invoicing, proper trust accounting, permissions, audit-ready file closure, document library and actual form generation.

**Defensible differentiation:**
1. **Evidence provenance:** every form datum links to a human-reviewed fact, source document, revision and extraction confidence; conflicts have explicit disposition.
2. **Change impact:** when source evidence or an official rule/form version changes, affected drafts, reviews, clients and tasks are marked stale with reason, not silently reused.
3. **RCIC signoff ledger:** distinguish staff preparation, consulting advice, applicant consent, professional approval and government submission receipt.
4. **Low-friction client experience:** reuse household data with consent and permissions, send precise missing-item requests, never overwhelm clients with irrelevant documents.
5. **Regulatory operations:** enforce consultation/retainer gates, accurate trust subledger, exports, grievance/error workflow and continuity plan.
6. **Measured outcomes:** benchmark time to first draft, average duplicate entry, documents requested twice, missed deadline rate, review rework rate and human corrections—never fabricated KPIs.

## Research gaps

1. Vendor websites are self-published; schedule real demos or trial accounts with dummy data to verify advertised functionality.
2. Separate product tiers/add-ons/seat costs/limits from headline features; these may change.
3. Get a qualified RCIC and accounting specialist to review regulated workflow requirements and local rules.
4. Do not assume ISO/SOC claims or "Canadian hosting" alone demonstrate actual compliance.
5. Test import/export of existing practice records from competing software before calling migration turnkey.
