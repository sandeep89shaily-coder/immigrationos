"""Timeline clarification append-only tables with portal and staff RLS.

Revision ID: 0021_timeline_clarifications
Revises: 0020_repeatable_intake
"""
from alembic import op
import sqlalchemy as sa

revision="0021_timeline_clarifications"
down_revision="0020_repeatable_intake"
branch_labels=None
depends_on=None


def upgrade():
    op.create_table("timeline_clarifications",
        sa.Column("id",sa.Uuid(),primary_key=True),
        sa.Column("org_id",sa.Uuid(),sa.ForeignKey("organizations.id"),nullable=False),
        sa.Column("case_id",sa.Uuid(),nullable=False),
        sa.Column("kind",sa.String(20),nullable=False),
        sa.Column("flag_type",sa.String(50),nullable=False),
        sa.Column("flag_sha256",sa.String(64),nullable=False),
        sa.Column("snapshot_sha256",sa.String(64),nullable=False),
        sa.Column("window_start",sa.String(10),nullable=False),
        sa.Column("window_end",sa.String(10),nullable=False),
        sa.Column("question",sa.String(600),nullable=False),
        sa.Column("created_by_sub",sa.String(255),nullable=False),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
        sa.ForeignKeyConstraint(["org_id","case_id"],["cases.org_id","cases.id"],
                                name="fk_timeline_clarification_case"),
        sa.UniqueConstraint("org_id","case_id","id",name="uq_timeline_clarification_case"),
        sa.CheckConstraint("kind IN ('address','employment','education')",
                           name="ck_timeline_clarification_kind"),
        sa.CheckConstraint("flag_type IN ('uncovered_period_for_review','overlap_for_review','end_date_not_supplied','invalid_date','reversed_period')",
                           name="ck_timeline_clarification_flag"))
    op.create_index("ix_timeline_clarification_case","timeline_clarifications",
                    ["org_id","case_id","created_at"])
    for table,payload,columns,check in [
        ("timeline_clarification_replies",
         [sa.Column("answer",sa.String(1600),nullable=False),
          sa.Column("answered_by_sub",sa.String(255),nullable=False)],
         "uq_timeline_reply_once",None),
        ("timeline_clarification_decisions",
         [sa.Column("decision",sa.String(30),nullable=False),
          sa.Column("reviewed_by_sub",sa.String(255),nullable=False)],
         "uq_timeline_decision_once",
         sa.CheckConstraint("decision IN ('reviewed','needs_more_information')",
                            name="ck_timeline_clarification_decision"))]:
        fields=[
            sa.Column("id",sa.Uuid(),primary_key=True),
            sa.Column("org_id",sa.Uuid(),sa.ForeignKey("organizations.id"),nullable=False),
            sa.Column("case_id",sa.Uuid(),nullable=False),
            sa.Column("request_id",sa.Uuid(),nullable=False),
            *payload,
            sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
            sa.ForeignKeyConstraint(["org_id","case_id","request_id"],
                ["timeline_clarifications.org_id","timeline_clarifications.case_id",
                 "timeline_clarifications.id"],name="fk_"+table+"_request"),
            sa.UniqueConstraint("org_id","request_id",name=columns)]
        if check is not None:
            fields.append(check)
        op.create_table(table,*fields)
    if op.get_bind().dialect.name!="postgresql":
        return
    for table in ("timeline_clarifications","timeline_clarification_replies",
                  "timeline_clarification_decisions"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    staff=lambda table: f"""({table}.org_id::text=current_setting('app.tenant_id',true)
        AND EXISTS (SELECT 1 FROM memberships m WHERE m.org_id={table}.org_id
          AND m.subject=current_setting('app.principal_sub',true) AND m.is_active))"""
    reviewer=lambda table,column: f"""({staff(table)} AND {table}.{column}=
        current_setting('app.principal_sub',true) AND EXISTS (
          SELECT 1 FROM memberships m WHERE m.org_id={table}.org_id
          AND m.subject=current_setting('app.principal_sub',true)
          AND m.is_active AND m.role IN ('owner','admin','consultant')))"""
    grant=lambda table: f"""({table}.org_id::text=current_setting('app.tenant_id',true)
        AND current_setting('app.verified_email',true) <> ''
        AND EXISTS (SELECT 1 FROM portal_grants g WHERE g.org_id={table}.org_id
          AND g.case_id={table}.case_id
          AND g.principal_sub=current_setting('app.principal_sub',true)
          AND g.revoked_at IS NULL))"""
    t="timeline_clarifications"
    op.execute(f"CREATE POLICY timeline_request_staff_select ON {t} FOR SELECT USING ({staff(t)})")
    op.execute(f"CREATE POLICY timeline_request_staff_insert ON {t} FOR INSERT WITH CHECK ({reviewer(t,'created_by_sub')})")
    op.execute(f"CREATE POLICY timeline_request_client_select ON {t} FOR SELECT USING ({grant(t)})")
    t="timeline_clarification_replies"
    op.execute(f"CREATE POLICY timeline_reply_staff_select ON {t} FOR SELECT USING ({staff(t)})")
    client=f"""({grant(t)} AND answered_by_sub=current_setting('app.principal_sub',true)
        AND EXISTS (SELECT 1 FROM timeline_clarifications q WHERE
          q.org_id={t}.org_id AND q.case_id={t}.case_id AND q.id={t}.request_id))"""
    op.execute(f"CREATE POLICY timeline_reply_client_select ON {t} FOR SELECT USING ({grant(t)})")
    op.execute(f"CREATE POLICY timeline_reply_client_insert ON {t} FOR INSERT WITH CHECK ({client})")
    t="timeline_clarification_decisions"
    op.execute(f"CREATE POLICY timeline_decision_staff_select ON {t} FOR SELECT USING ({staff(t)})")
    op.execute(f"CREATE POLICY timeline_decision_staff_insert ON {t} FOR INSERT WITH CHECK ({reviewer(t,'reviewed_by_sub')})")
    op.execute(f"CREATE POLICY timeline_decision_client_select ON {t} FOR SELECT USING ({grant(t)})")
    op.execute("DROP POLICY portal_audit_insert ON audit_events")
    op.execute("""CREATE POLICY portal_audit_insert ON audit_events FOR INSERT WITH CHECK (
      actor_sub=current_setting('app.principal_sub',true)
      AND action IN ('portal.invitation_accepted','portal.document_received_quarantined',
                     'portal.study_intake_submitted','portal.repeatable_proposal_submitted',
                     'portal.timeline_clarification_replied')
      AND EXISTS (SELECT 1 FROM portal_grants g WHERE g.org_id=audit_events.org_id
        AND g.principal_sub=current_setting('app.principal_sub',true)
        AND g.revoked_at IS NULL))""")
    op.execute("""DO $roles$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles
      WHERE rolname='immigrationos_app') THEN
      GRANT SELECT,INSERT ON timeline_clarifications TO immigrationos_app;
      GRANT SELECT,INSERT ON timeline_clarification_replies TO immigrationos_app;
      GRANT SELECT,INSERT ON timeline_clarification_decisions TO immigrationos_app;
      REVOKE UPDATE,DELETE ON timeline_clarifications,
        timeline_clarification_replies,timeline_clarification_decisions FROM immigrationos_app;
    END IF; END $roles$""")


def downgrade():
    if op.get_bind().dialect.name=="postgresql":
        op.execute("DROP POLICY portal_audit_insert ON audit_events")
        op.execute("""CREATE POLICY portal_audit_insert ON audit_events FOR INSERT WITH CHECK (
          actor_sub=current_setting('app.principal_sub',true)
          AND action IN ('portal.invitation_accepted','portal.document_received_quarantined',
                         'portal.study_intake_submitted','portal.repeatable_proposal_submitted')
          AND EXISTS (SELECT 1 FROM portal_grants g WHERE g.org_id=audit_events.org_id
            AND g.principal_sub=current_setting('app.principal_sub',true)
            AND g.revoked_at IS NULL))""")
    op.drop_table("timeline_clarification_decisions")
    op.drop_table("timeline_clarification_replies")
    op.drop_index("ix_timeline_clarification_case",table_name="timeline_clarifications")
    op.drop_table("timeline_clarifications")
