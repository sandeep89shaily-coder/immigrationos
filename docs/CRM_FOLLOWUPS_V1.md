# ImmigrationOS — Prospect follow-ups and overdue queue

**Stage:** RCIC CRM development prototype using synthetic data only.
**Automation:** Internal queue only. There are **no outbound email, SMS, WhatsApp, calendar push, scheduled escalation or notification delivery workers**.

## What RCIC staff can do

1. Open **Prospects** in the consultant workspace. Firm-wide open overdue follow-ups appear above the pipeline.
2. Open a fictional prospect and select **+ Follow-up**.
3. Enter a short next action, due date/time in the browser's local timezone, and normal or urgent priority. The server normalizes the timestamp to UTC.
4. The task is assigned to the authenticated staff member who created it. In the initial workflow, tasks cannot be reassigned by entering an arbitrary identity subject.
5. See due times and overdue status for that prospect. Staff may mark the task complete or cancel it; those actions record an immutable metadata audit event.
6. A completed/cancelled task cannot be reopened, rescheduled or modified. To create a new follow-up, create a separate record and retain the original history.
7. Closing or converting the prospect does not secretly delete or mark its open follow-ups complete. Staff can still explicitly reconcile the tasks.

## REST API

All endpoints require authenticated membership in the correct firm under
\`/api/v1/orgs/{org_id}/crm\`.

- \`GET /follow-ups?status=open&overdue_only=true\` — firm work queue, sorted by due date; 200-record cap.
- \`GET /prospects/{prospect_id}/follow-ups\` — current and historical prospect actions.
- \`POST /prospects/{prospect_id}/follow-ups\` — \`{"title":"Follow up with prospect","due_at":"2026-11-12T15:00:00-05:00","priority":"normal"}\`.
- \`POST /prospects/{prospect_id}/follow-ups/{id}/complete\` — complete once.
- \`POST /prospects/{prospect_id}/follow-ups/{id}/cancel\` — cancel once.

The server rejects duplicate open tasks with the same title on the same prospect, invalid or naive timezones, dates in the past, deadlines more than three years away, malformed priorities, and new tasks for inactive prospects.

The response contains \`delivery_mode: "internal_queue_only"\` and \`message_sent: false\` deliberately: the presence of a task is not proof of any reminder being delivered.

## Security and integrity

- Five existing CRM tenant relationships remain intact; new \`crm_followups\` has a same-prospect composite foreign key.
- PostgreSQL \`FORCE ROW LEVEL SECURITY\` checks active firm membership and tenant context on every read and write.
- Insert rows must be assigned to/created by the current authenticated subject.
- The limited PostgreSQL runtime role may update **only** terminal status and the attributed completion/cancellation columns—not the due date, assignee, original title or creator. A terminal-state check requires the correct attribution.
- Append-only audit metadata records task creation, completion and cancellation without copying client/prospect names or note contents into audit events.
- All program/legal deadlines must use a **separate source-anchored legal deadline feature**. This prospect follow-up tool is NOT a legal/IRCC deadline calculator and should never infer statutory due dates.

## Acceptance

- \`tests/test_crm_followups.py\`: create, duplicate detection, overdue list and filtering, complete/cancel once, viewer permissions, cross-firm isolation, validation, closed-lead behavior and composite-FK rejection.
- \`scripts/postgres_crm_smoke.py\`: real PostgreSQL limited-role create/complete plus cross-tenant checks.
- \`scripts/verify_rls.py\`: FORCE RLS on table, no due-date or assignee mutation grants.
- \`.github/workflows/ci.yml\`: Python + JS syntax and all database migration/integration checks.

**Future:** firm staff invitations/verified assignments, retry-safe notification delivery with client consent, calendar sync, escalation to backup RCIC, business hours and multi-timezone reminders. These are not present in this increment.
