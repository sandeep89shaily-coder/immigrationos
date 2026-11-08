"""Staff-only gap worklist joining existing study intake, applicant, and evidence.

No form completion, applicant eligibility finding, or automatic evidence promotion.
This is a read-only view; questionnaire submissions remain append-only and
staff accept decisions create *pending*, not verified, CaseFacts.
"""
from uuid import UUID
from datetime import date
from calendar import monthrange
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.access import OrgAccess, allow, get_org_access
from app.applicant_models import ApplicantProfile, FamilyMember
from app.applicant_history_models import ApplicantHistory
from app.applicant_supplemental_history_models import ApplicantSupplementalHistory
from app.repeatable_intake_models import ClientRepeatableProposal, ClientRepeatableDecision
from app.supplemental_disclosure_review import supplemental_disclosure_review
from app.db import get_db
from app.form_manifest import MANIFESTS
from app.history_timeline_audit import audit_history_timeline
from app.imm5476_case_preview import _field_status, scan_status_by_document
from app.intake_models import StudyIntakeDecision, StudyIntakeSubmission
from app.models import Case, CaseDocument, CaseFact
from app.package_models import CaseApplicationPackage
from app.schemas import Role
from app.study_intake import QUESTIONS, TEMPLATE_VERSION

router = APIRouter(prefix="/api/v1/orgs/{org_id}/cases/{case_id}",
                   tags=["study-permit-intake-worklist"])
READERS = {Role.owner, Role.admin, Role.consultant, Role.assistant}
PROFILE_PATHS = {
    "identity.given_name": "given_name",
    "identity.family_name": "family_name",
    "identity.date_of_birth": "date_of_birth",
    "identity.citizenship": "citizenship",
    "identity.passport_number": "passport_number",
    "identity.passport_expiry_date": "passport_expiry",
}
FORMAT_KEYS = {"identity.date_of_birth": "applicant_dob"}


def build_worklist(*, case: Case, form_code: str, profile: ApplicantProfile | None,
                   family: list[FamilyMember], histories: list[ApplicantHistory],
                   submission: StudyIntakeSubmission | None,
                   decisions: list[StudyIntakeDecision],
                   facts: list[CaseFact], documents: list[CaseDocument],
                   scans: dict[UUID, str],
                   supplemental_records=(), proposals=(), proposal_decisions=()) -> dict:
    if form_code not in MANIFESTS or case.application_type != "study_permit":
        raise ValueError("Incompatible study-permit worklist context")
    docs = {d.id: d for d in documents
            if d.org_id == case.org_id and d.case_id == case.id}
    scoped_facts = [f for f in facts
                    if f.org_id == case.org_id and f.case_id == case.id]
    accepted = {d.field_path: d.decision for d in decisions
                if submission is not None and d.submission_id == submission.id}
    profile_identity = profile.data.get("identity", {}) if profile else {}
    rows = []
    for question in QUESTIONS:
        path = question.path
        candidate_facts = [f for f in scoped_facts if f.field_path == path]
        evidence = _field_status(FORMAT_KEYS.get(path, path),
                                 candidate_facts, docs, scans)
        submitted = submission is not None and bool(submission.answers.get(path))
        profile_claim = bool(profile_identity.get(PROFILE_PATHS.get(path, "")))
        controller = (submission.answers.get(question.condition_path)
                      if submission is not None and question.condition_path else None)
        condition_state = ("active" if question.condition_path is None else
                           "unresolved" if controller in (None, "", "unsure") else
                           "active" if controller == question.condition_value else
                           "inactive")
        if condition_state == "inactive":
            state = "not_applicable_to_latest_answer"
        elif condition_state == "unresolved":
            state = "conditional_applicability_unresolved"
        elif evidence["status"] == "verified_source_value":
            state = "evidence_verified"
        elif evidence["status"] not in ("missing_evidence",):
            state = "evidence_review_required"
        elif submitted and accepted.get(path) == "accept":
            state = "accepted_pending_documentary_verification"
        elif submitted and accepted.get(path) == "dismiss":
            state = "dismissed_answer_needs_recollection"
        elif submitted:
            state = "submitted_waiting_staff_decision"
        elif profile_claim:
            state = "reusable_profile_claim_needs_evidence"
        else:
            state = "missing_answer"
        # Avoid returning raw values in a summary, even when evidence is verified.
        rows.append({
            "path": path, "label": question.label, "group": question.group,
            "required_by_preliminary_questionnaire": question.required,
            "status": state, "evidence_status": evidence["status"],
            "condition_state": condition_state,
            "condition_path": question.condition_path,
            "has_profile_claim": profile_claim,
            "has_latest_submitted_answer": submitted,
            "latest_answer_decision": accepted.get(path),
        })
    outstanding = [x["path"] for x in rows if x["status"] not in
                   ("evidence_verified", "not_applicable_to_latest_answer")]
    applicable = [x for x in rows if x["condition_state"] != "inactive"]
    # Official instructions ask for ten years of occupation history or the
    # ten years preceding retirement. This preview cannot infer retirement.
    today = date.today()
    lookback_start = date(today.year - 10, today.month,
                          min(today.day, monthrange(today.year - 10, today.month)[1]))
    employment_audit = audit_history_timeline(
        records=histories, client_id=case.client_id, org_id=case.org_id,
        start=lookback_start, end=today)["categories"]["employment"]
    occupation_review = {
        "window_start": lookback_start.isoformat(),
        "window_end": today.isoformat(),
        "instruction_window": "last_10_years_or_pre_retirement_10_years",
        "record_count": employment_audit["record_count"],
        "coverage_evaluable": employment_audit["coverage_evaluable"],
        "flag_types": sorted({flag["type"] for flag in employment_audit["flags"]}),
        "flag_count": len(employment_audit["flags"]),
        "status": ("timeline_clarifications_needed"
                   if employment_audit["flags"] else
                   "chronology_needs_documentary_review"),
        "verified_complete": False,
        "retirement_exception_assessed": False,
        "source_url": ("https://www.canada.ca/en/immigration-refugees-citizenship/"
                       "services/application/application-forms-guides/" +
                       form_code.lower() + ".html"),
        "source_section": "Employment (work or occupation)",
    }
    supplemental_review = supplemental_disclosure_review(
        case=case, submission=submission, proposals=proposals,
        decisions=proposal_decisions, records=supplemental_records,
        facts=facts, documents=documents, scans=scans)
    manifest = MANIFESTS[form_code]
    return {
        "case_id": str(case.id), "form_code": form_code,
        "manifest_version": manifest.manifest_version,
        "manifest_sha256": manifest.digest,
        "questionnaire_version": TEMPLATE_VERSION,
        "latest_submission_id": str(submission.id) if submission else None,
        "profile_version": profile.version if profile else None,
        "family_member_count": len(family),
        "history_record_counts": {
            kind: sum(row.kind == kind for row in histories)
            for kind in ("address", "education", "employment", "travel")
        },
        "questions": rows,
        "employment_history_review": occupation_review,
        "supplemental_disclosure_review": supplemental_review,
        "preliminary_question_count": len(rows),
        "document_verified_question_count": sum(
            x["status"] == "evidence_verified" for x in rows),
        "applicable_question_count": len(applicable),
        "unresolved_conditional_question_count": sum(
            x["condition_state"] == "unresolved" for x in rows),
        "questions_still_requiring_evidence_or_review": outstanding,
        "official_form_complete": False,
        "official_pdf_autofill_supported": False,
        "submission_supported": False,
        "warning": "Staff-only preliminary questionnaire worklist. Reused profile values and client answers are not independent verified evidence; not an official IRCC field inventory.",
    }


@router.get("/study-intake/worklist")
def study_intake_worklist(org_id: UUID, case_id: UUID, response: Response,
                          db: Session = Depends(get_db),
                          access: OrgAccess = Depends(get_org_access)):
    allow(access, READERS)
    case = db.scalar(select(Case).where(
        Case.org_id == org_id, Case.id == case_id))
    if case is None:
        raise HTTPException(404, "Matter not found")
    package = db.scalar(select(CaseApplicationPackage).where(
        CaseApplicationPackage.org_id == org_id,
        CaseApplicationPackage.case_id == case_id))
    if case.application_type != "study_permit" or package is None:
        raise HTTPException(409, "Initialize a study-permit application package first")
    if package.filing_context not in ("inside_canada", "outside_canada"):
        raise HTTPException(409, "Unsupported study-permit filing context")
    form_code = "IMM5709" if package.filing_context == "inside_canada" else "IMM1294"
    profile = db.scalar(select(ApplicantProfile).where(
        ApplicantProfile.org_id == org_id,
        ApplicantProfile.client_id == case.client_id))
    family = db.scalars(select(FamilyMember).where(
        FamilyMember.org_id == org_id,
        FamilyMember.client_id == case.client_id)).all()
    histories = db.scalars(select(ApplicantHistory).where(
        ApplicantHistory.org_id == org_id,
        ApplicantHistory.client_id == case.client_id)).all()
    submission = db.scalar(select(StudyIntakeSubmission).where(
        StudyIntakeSubmission.org_id == org_id,
        StudyIntakeSubmission.case_id == case_id,
    ).order_by(StudyIntakeSubmission.created_at.desc(),
               StudyIntakeSubmission.id.desc()).limit(1))
    decisions = db.scalars(select(StudyIntakeDecision).where(
        StudyIntakeDecision.org_id == org_id,
        StudyIntakeDecision.case_id == case_id,
        StudyIntakeDecision.submission_id == submission.id
    )).all() if submission else []
    facts = db.scalars(select(CaseFact).where(
        CaseFact.org_id == org_id, CaseFact.case_id == case_id)).all()
    documents = db.scalars(select(CaseDocument).where(
        CaseDocument.org_id == org_id, CaseDocument.case_id == case_id)).all()
    supplemental = db.scalars(select(ApplicantSupplementalHistory).where(
        ApplicantSupplementalHistory.org_id == org_id,
        ApplicantSupplementalHistory.client_id == case.client_id)).all()
    proposals = db.scalars(select(ClientRepeatableProposal).where(
        ClientRepeatableProposal.org_id == org_id,
        ClientRepeatableProposal.case_id == case_id)).all()
    proposal_decisions = db.scalars(select(ClientRepeatableDecision).where(
        ClientRepeatableDecision.org_id == org_id,
        ClientRepeatableDecision.case_id == case_id)).all()
    response.headers["Cache-Control"] = "no-store"
    return build_worklist(
        case=case, form_code=form_code, profile=profile, family=family,
        histories=histories, submission=submission, decisions=decisions,
        facts=facts, documents=documents,
        scans=scan_status_by_document(db, org_id, case_id),
        supplemental_records=supplemental, proposals=proposals,
        proposal_decisions=proposal_decisions)
