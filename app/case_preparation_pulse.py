"""Staff-only case preparation pulse composed from existing review systems.

This is a unified *worklist* (not a new readiness score or IRCC determination).
Unsupported or uninitialized components remain explicit blockers.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.access import OrgAccess, READ_ROLES, allow, get_org_access
from app.applicant_history_models import ApplicantHistory
from app.applicant_models import ApplicantProfile, FamilyMember
from app.db import get_db
from app.document_requirements import _read as document_worklist
from app.form_preflight import _snapshot as preflight_snapshot
from app.imm5476_case_preview import scan_status_by_document
from app.intake_models import StudyIntakeSubmission, StudyIntakeDecision
from app.ircc_registry import REGISTRY
from app.models import Case, CaseDocument, CaseFact, CaseIssue, CaseTask
from app.package_models import CaseApplicationPackage
from app.repeatable_intake_models import ClientRepeatableProposal, ClientRepeatableDecision
from app.study_intake_worklist import build_worklist
from app.timeline_clarification_models import (
    TimelineClarification, TimelineClarificationReply, TimelineClarificationDecision)
from app.timeline_history_correction_models import TimelineHistoryCorrection

router = APIRouter(prefix="/api/v1/orgs/{org_id}/cases/{case_id}",
                   tags=["case-preparation-pulse"])
SCHEMA_VERSION = "internal-case-pulse-2026-11-08"


def compose_pulse(*, case, package, worklist, requirements, preflight,
                  repeatables, repeatable_decisions, clarifications, replies,
                  clarification_decisions, corrections, issues, tasks):
    """Pure composition of already-reviewed domain states. No automatic verification."""
    items = []
    def add(area, code, state, label, *, ref=None, count=1):
        items.append({"area":area,"code":code,"status":state,"label":label,
                      "reference_id":str(ref) if ref is not None else None,
                      "count":count})

    if package is None:
        add("package","package_not_initialized","action_required",
            "Initialize the case application package")
    if worklist is not None:
        for question in worklist["questions"]:
            if question["status"] not in ("evidence_verified", "not_applicable_to_latest_answer"):
                add("intake", question["path"], question["status"],
                    question["label"])
    else:
        add("intake","intake_unavailable","unsupported",
            "No supported study-permit questionnaire worklist")
    if requirements is not None:
        for row in requirements["requirements"]:
            if row["key"] in requirements["unresolved_requirements"]:
                add("documents", row["key"], row["status"], row["title"])
        if requirements["source_recheck_required"]:
            add("documents","source_recheck","source_review_required",
                "Recheck source observations for document checklist")
    else:
        add("documents","document_worklist_unavailable","unsupported",
            "Document requirements not initialized or unsupported")
    if preflight is not None:
        for blocker in preflight["blockers"]:
            add("form_preflight","blocker","blocked",blocker)
        if preflight["acknowledgement"] != "current":
            add("form_preflight","acknowledgement", "staff_review_required",
                "Current internal form-preflight acknowledgement is absent or stale")
    else:
        add("form_preflight","preflight_unavailable","unsupported",
            "No supported internal form preflight")

    resolved = {d.proposal_id for d in repeatable_decisions}
    for proposal in repeatables:
        if proposal.id not in resolved:
            add("client_records", proposal.kind, "awaiting_staff",
                "Review client-submitted " + proposal.kind + " record",ref=proposal.id)
    replies_by_request={r.request_id:r for r in replies}
    decisions_by_request={d.request_id:d for d in clarification_decisions}
    corrected={c.request_id for c in corrections}
    for request in clarifications:
        reply=replies_by_request.get(request.id)
        decision=decisions_by_request.get(request.id)
        if reply is None:
            status="awaiting_client"
            label="Await client explanation for " + request.kind + " timeline"
        elif decision is None:
            status="awaiting_staff"
            label="Review client timeline explanation"
        elif decision.decision=="needs_more_information":
            status="needs_more_information"
            label="Follow up on unresolved " + request.kind + " timeline explanation"
        elif request.id not in corrected:
            status="reviewed_not_corrected"
            label="Reviewed timeline explanation; assess need for a history correction"
        else:
            continue
        add("timeline",request.flag_type,status,label,ref=request.id)

    for issue in issues:
        if issue.status=="open":
            add("case_issues","open_issue","action_required",
                "Resolve open case evidence issue",ref=issue.id)
    for task in tasks:
        if task.status=="open":
            add("case_tasks","open_task","action_required",
                "Review open case task",ref=task.id)

    areas=("intake","client_records","timeline","documents",
           "case_issues","case_tasks","form_preflight","package")
    counts={area:sum(i["area"]==area for i in items) for area in areas}
    return {
        "schema_version":SCHEMA_VERSION,"case_id":str(case.id),
        "case_status":case.status,
        "filing_context":package.filing_context if package else None,
        "worklist_items":items,"unresolved_count":len(items),
        "area_counts":counts,
        "preliminary_question_count":worklist["preliminary_question_count"] if worklist else None,
        "verified_preliminary_question_count":worklist["document_verified_question_count"] if worklist else None,
        "outstanding_client_record_reviews":sum(i["area"]=="client_records" for i in items),
        "outstanding_timeline_clarifications":sum(i["area"]=="timeline" for i in items),
        "internal_preflight_status":preflight["internal_preflight_status"] if preflight else "unavailable",
        "preflight_acknowledgement":preflight["acknowledgement"] if preflight else "unavailable",
        "sources_need_recheck":(
            (requirements["source_recheck_required"] if requirements else True) or
            (preflight["source_recheck_required"] if preflight else True)),
        "operational_worklist_clear":len(items)==0,
        "professional_eligibility_verified":False,
        "entire_ircc_form_complete":False,
        "official_pdf_generation_supported":False,
        "submission_supported":False,
        "warning":"Internal preparation only. A cleared worklist never proves legal eligibility, exhaustive document/form coverage, validated IRCC PDFs, or permission to submit.",
    }


@router.get("/preparation-pulse")
def preparation_pulse(org_id:UUID,case_id:UUID,response:Response,
                      db:Session=Depends(get_db),
                      access:OrgAccess=Depends(get_org_access)):
    allow(access, READ_ROLES)
    case=db.scalar(select(Case).where(Case.org_id==org_id,Case.id==case_id))
    if case is None:
        raise HTTPException(404,"Case not available")
    package=db.scalar(select(CaseApplicationPackage).where(
        CaseApplicationPackage.org_id==org_id,
        CaseApplicationPackage.case_id==case_id))
    worklist=None
    requirements=None
    preflight=None
    if package and case.application_type=="study_permit" and package.filing_context in ("inside_canada","outside_canada"):
        code="IMM5709" if package.filing_context=="inside_canada" else "IMM1294"
        profile=db.scalar(select(ApplicantProfile).where(
            ApplicantProfile.org_id==org_id,ApplicantProfile.client_id==case.client_id))
        family=db.scalars(select(FamilyMember).where(
            FamilyMember.org_id==org_id,FamilyMember.client_id==case.client_id)).all()
        histories=db.scalars(select(ApplicantHistory).where(
            ApplicantHistory.org_id==org_id,ApplicantHistory.client_id==case.client_id)).all()
        submission=db.scalar(select(StudyIntakeSubmission).where(
            StudyIntakeSubmission.org_id==org_id,
            StudyIntakeSubmission.case_id==case_id
        ).order_by(StudyIntakeSubmission.created_at.desc(),
                   StudyIntakeSubmission.id.desc()).limit(1))
        decisions=db.scalars(select(StudyIntakeDecision).where(
            StudyIntakeDecision.org_id==org_id,
            StudyIntakeDecision.case_id==case_id,
            StudyIntakeDecision.submission_id==submission.id)).all() if submission else []
        facts=db.scalars(select(CaseFact).where(
            CaseFact.org_id==org_id,CaseFact.case_id==case_id)).all()
        documents=db.scalars(select(CaseDocument).where(
            CaseDocument.org_id==org_id,CaseDocument.case_id==case_id)).all()
        worklist=build_worklist(
            case=case,form_code=code,profile=profile,family=family,
            histories=histories,submission=submission,decisions=decisions,
            facts=facts,documents=documents,
            scans=scan_status_by_document(db,org_id,case_id))
        requirements=document_worklist(db,org_id,case_id)
        source=REGISTRY[code]
        preflight=preflight_snapshot(db,case,source)
        # Preserve existing acknowledgement logic; never infer a valid review.
        from app.form_preflight import _with_ack
        preflight=_with_ack(db,org_id,case_id,preflight)
    repeatables=db.scalars(select(ClientRepeatableProposal).where(
        ClientRepeatableProposal.org_id==org_id,
        ClientRepeatableProposal.case_id==case_id)).all()
    repeatable_decisions=db.scalars(select(ClientRepeatableDecision).where(
        ClientRepeatableDecision.org_id==org_id,
        ClientRepeatableDecision.case_id==case_id)).all()
    clarifications=db.scalars(select(TimelineClarification).where(
        TimelineClarification.org_id==org_id,
        TimelineClarification.case_id==case_id)).all()
    replies=db.scalars(select(TimelineClarificationReply).where(
        TimelineClarificationReply.org_id==org_id,
        TimelineClarificationReply.case_id==case_id)).all()
    clarification_decisions=db.scalars(select(TimelineClarificationDecision).where(
        TimelineClarificationDecision.org_id==org_id,
        TimelineClarificationDecision.case_id==case_id)).all()
    corrections=db.scalars(select(TimelineHistoryCorrection).where(
        TimelineHistoryCorrection.org_id==org_id,
        TimelineHistoryCorrection.case_id==case_id)).all()
    issues=db.scalars(select(CaseIssue).where(
        CaseIssue.org_id==org_id,CaseIssue.case_id==case_id)).all()
    tasks=db.scalars(select(CaseTask).where(
        CaseTask.org_id==org_id,CaseTask.case_id==case_id)).all()
    response.headers["Cache-Control"]="no-store"
    return compose_pulse(
        case=case,package=package,worklist=worklist,
        requirements=requirements,preflight=preflight,
        repeatables=repeatables,repeatable_decisions=repeatable_decisions,
        clarifications=clarifications,replies=replies,
        clarification_decisions=clarification_decisions,
        corrections=corrections,issues=issues,tasks=tasks)
