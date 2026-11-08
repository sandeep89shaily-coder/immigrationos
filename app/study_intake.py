"""Study-permit client intake v1: versioned, source-linked, consent-noted and human reviewed.

This is a preliminary questionnaire, not IMM 1294, IMM 5709, a complete
application, an eligibility determination or advice. Client answers are NEVER
marked verified on submission, and accepting one creates a PENDING CaseFact.
"""
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.access import OrgAccess, allow, get_org_access
from app.auth import Principal, get_principal
from app.db import get_db
from app.intake_models import StudyIntakeDecision, StudyIntakeSubmission
from app.main import record_event
from app.models import Case, CaseFact
from app.portal import active_grant, db_verified_email
from app.schemas import Role
from app.workspace import insert_fact_with_conflicts
from app.workspace_schemas import FactCreate


SOURCE = "https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm1294.html"
TEMPLATE_VERSION = "study-permit-conditional-identity-finance-2026-11-08-v2"
NOTICE_VERSION = "development-intake-notice-v1"
NOTICE = (
    "ImmigrationOS is an experimental system for fictitious test cases only. "
    "Answers will be stored in the connected practice's development database and "
    "shown to its permitted staff for verification. Submitting does not authorize "
    "external AI processing, establish eligibility, or submit anything to IRCC."
)

client_router = APIRouter(prefix="/api/v1/client/cases/{case_id}/study-intake",
                          tags=["study-permit-client-intake"])
staff_router = APIRouter(prefix="/api/v1/orgs/{org_id}/cases/{case_id}/study-intake",
                         tags=["study-permit-staff-intake"])
STAFF_REVIEW = {Role.owner, Role.admin, Role.consultant}
STAFF_READ = STAFF_REVIEW | {Role.assistant}


@dataclass(frozen=True)
class Question:
    path: str
    label: str
    group: str
    kind: str = "text"
    required: bool = False
    choices: tuple[str, ...] = ()
    condition_path: str | None = None
    condition_value: str | None = None
    source_section: str | None = None


QUESTIONS = (
    Question("identity.given_name", "Given name(s), as on passport", "Identity", required=True),
    Question("identity.family_name", "Family name, as on passport", "Identity", required=True),
    Question("identity.date_of_birth", "Date of birth", "Identity", "date", True),
    Question("identity.citizenship", "Country or territory of citizenship", "Identity", required=True),
    Question("identity.has_other_names", "Have you ever used another name or alias?", "Identity", "choice",
             choices=("yes", "no", "unsure"), source_section="Personal details / Question 2"),
    Question("identity.other_family_name", "Other family name(s) used", "Identity",
             required=True, condition_path="identity.has_other_names", condition_value="yes",
             source_section="Personal details / Question 2"),
    Question("identity.other_given_name", "Other given name(s) used (if any)", "Identity",
             condition_path="identity.has_other_names", condition_value="yes",
             source_section="Personal details / Question 2"),
    Question("identity.passport_number", "Passport / travel document number", "Passport", required=True),
    Question("identity.passport_issue_date", "Passport issue date", "Passport", "date"),
    Question("identity.passport_expiry_date", "Passport expiry date", "Passport", "date"),
    Question("identity.has_national_id", "Do you have a national identity document?", "National identity", "choice",
             choices=("yes", "no", "unsure"), source_section="National identity document / Question 1"),
    Question("identity.national_id_number", "National identity document number", "National identity",
             required=True, condition_path="identity.has_national_id", condition_value="yes",
             source_section="National identity document / Question 2"),
    Question("identity.national_id_country", "Country or territory issuing national identity document", "National identity",
             required=True, condition_path="identity.has_national_id", condition_value="yes",
             source_section="National identity document / Question 3"),
    Question("identity.national_id_issue_date", "National identity document issue date", "National identity", "date",
             condition_path="identity.has_national_id", condition_value="yes",
             source_section="National identity document / Question 4"),
    Question("identity.national_id_expiry_date", "National identity document expiry date", "National identity", "date",
             condition_path="identity.has_national_id", condition_value="yes",
             source_section="National identity document / Question 5"),
    Question("education.institution", "Canadian school / institution name", "Study plans"),
    Question("education.dli_number", "Designated learning institution number", "Study plans"),
    Question("education.program_name", "Proposed course / program", "Study plans"),
    Question("education.program_start_date", "Expected program start date", "Study plans", "date"),
    Question("education.program_end_date", "Expected program end date", "Study plans", "date"),
    Question("finance.tuition_cad", "Expected tuition amount (CAD)", "Finances", "money"),
    Question("finance.available_funds_cad", "Available funds for stay (CAD)", "Finances", "money"),
    Question("finance.expenses_paid_by", "Who is paying for expenses?", "Finances", "choice",
             choices=("myself", "parents", "other", "unsure")),
    Question("finance.expenses_payer_details", "Explain who will pay your expenses", "Finances",
             required=True, condition_path="finance.expenses_paid_by", condition_value="other",
             source_section="Details of intended study / Expenses"),
    Question("history.prior_refusal", "Any previous visa or permit refusal?", "Background", "choice",
             choices=("yes", "no", "unsure")),
    Question("history.prior_refusal_details", "Describe the prior refusal(s)", "Background",
             required=True, condition_path="history.prior_refusal", condition_value="yes"),
    Question("planning.filing_location", "Where do you expect to apply?", "Application", "choice",
             choices=("inside_canada", "outside_canada", "unsure")),
)
QUESTION_BY_PATH = {q.path: q for q in QUESTIONS}


class SubmitAnswers(BaseModel):
    template_version: str = Field(min_length=5, max_length=80)
    acknowledged_notice: bool
    answers: dict[str, str] = Field(min_length=1, max_length=len(QUESTIONS))


class AnswerDecision(BaseModel):
    decision: str = Field(pattern=r"^(accept|dismiss)$")


def validate_answers(answers: dict[str, str]) -> dict[str, str]:
    """Strict known-field validation; never derive immigration eligibility."""
    normalized = {}
    for path, value in answers.items():
        question = QUESTION_BY_PATH.get(path)
        if question is None:
            raise HTTPException(422, "Questionnaire contains an unsupported field")
        if not isinstance(value, str):
            raise HTTPException(422, "All answer values must be text")
        value = value.strip()
        if len(value) > 300:
            raise HTTPException(422, "Answer exceeds maximum length")
        if not value:
            continue
        if question.kind == "choice" and value not in question.choices:
            raise HTTPException(422, "Invalid option for questionnaire field")
        if question.kind == "date":
            try:
                parsed = date.fromisoformat(value)
            except ValueError:
                raise HTTPException(422, "Date must be a valid YYYY-MM-DD") from None
            if parsed.isoformat() != value:
                raise HTTPException(422, "Date must be in canonical YYYY-MM-DD format")
        if question.kind == "money":
            try:
                number = Decimal(value)
            except InvalidOperation:
                raise HTTPException(422, "Amount must be a number") from None
            if (not number.is_finite() or number < 0 or number > Decimal("999999999")
                    or number.as_tuple().exponent < -2):
                raise HTTPException(422, "Amount must be a finite positive CAD amount")
            value = format(number, "f")
        normalized[path] = value

    # Conditional data is rejected when the predicate is not satisfied. This
    # prevents hidden, stale answers from being submitted accidentally.
    for q in QUESTIONS:
        if q.condition_path is not None:
            active = normalized.get(q.condition_path) == q.condition_value
            if not active and q.path in normalized:
                raise HTTPException(422, "Answer belongs to an inactive conditional question")
    missing = [q.path for q in QUESTIONS if q.required
               and (q.condition_path is None or
                    normalized.get(q.condition_path) == q.condition_value)
               and not normalized.get(q.path)]
    if missing:
        raise HTTPException(422, "Complete required active questionnaire fields before submitting")

    pairs = (("identity.passport_issue_date", "identity.passport_expiry_date"),
             ("identity.national_id_issue_date", "identity.national_id_expiry_date"),
             ("education.program_start_date", "education.program_end_date"))
    for begin, end in pairs:
        if normalized.get(begin) and normalized.get(end) and normalized[begin] > normalized[end]:
            raise HTTPException(422, "An end date precedes its start date")

    return normalized


def questionnaire():
    return {
        "id": "study_permit_preliminary",
        "template_version": TEMPLATE_VERSION,
        "notice_version": NOTICE_VERSION,
        "notice": NOTICE,
        "source_url": SOURCE,
        "not_official_ircc_form": True,
        "submission_supported": False,
        "fields": [{
            "path": q.path, "label": q.label, "group": q.group,
            "kind": q.kind, "required": q.required, "choices": list(q.choices),
            "condition_path": q.condition_path, "condition_value": q.condition_value,
            "source_section": q.source_section
        } for q in QUESTIONS],
    }


def study_case(db: Session, org_id: UUID, case_id: UUID, lock: bool = False):
    # Client portal principals have case SELECT but intentionally no UPDATE.
    # PostgreSQL SELECT ... FOR UPDATE would require broader case privileges.
    # Use a transaction-scoped advisory lock shared by client submissions and
    # consultant decisions; RLS still authorizes the case read independently.
    if lock and db.bind is not None and db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 1))"),
                   {"key": str(org_id) + ":" + str(case_id)})
    query = select(Case).where(Case.org_id == org_id, Case.id == case_id)
    case = db.scalar(query)
    if case is None:
        raise HTTPException(404, "Matter not found")
    if case.application_type != "study_permit":
        raise HTTPException(409, "This questionnaire is for study permit matters only")
    return case


def latest_for_case(db: Session, org_id: UUID, case_id: UUID):
    return db.scalar(select(StudyIntakeSubmission).where(
        StudyIntakeSubmission.org_id == org_id,
        StudyIntakeSubmission.case_id == case_id
    ).order_by(StudyIntakeSubmission.created_at.desc(),
               StudyIntakeSubmission.id.desc()).limit(1))


def submission_view(row, decisions=None):
    return {
        "id": str(row.id),
        "case_id": str(row.case_id),
        "template_version": row.template_version,
        "submitted_at": row.created_at,
        "answer_sha256": row.answer_sha256,
        "answers": row.answers,
        "decisions": [{
            "field_path": d.field_path, "decision": d.decision,
            "created_fact_id": str(d.created_fact_id) if d.created_fact_id else None,
            "reviewed_by_sub": d.reviewed_by_sub
        } for d in (decisions or [])],
        "not_official_ircc_form": True,
    }


@client_router.get("")
def client_questions(case_id: UUID, db: Session = Depends(get_db),
                     principal: Principal = Depends(get_principal)):
    db_verified_email(db, principal)
    grant = active_grant(db, principal, case_id)
    study_case(db, grant.org_id, case_id)
    current = db.scalar(select(StudyIntakeSubmission).where(
        StudyIntakeSubmission.org_id == grant.org_id,
        StudyIntakeSubmission.case_id == case_id,
        StudyIntakeSubmission.created_by_sub == principal.sub
    ).order_by(StudyIntakeSubmission.created_at.desc(),
               StudyIntakeSubmission.id.desc()).limit(1))
    return {
        **questionnaire(),
        "last_submitted_at": current.created_at if current else None,
        "last_submission_id": str(current.id) if current else None,
    }


@client_router.post("/submissions", status_code=201)
def submit_intake(case_id: UUID, payload: SubmitAnswers,
                  db: Session = Depends(get_db),
                  principal: Principal = Depends(get_principal)):
    db_verified_email(db, principal)
    grant = active_grant(db, principal, case_id)
    case = study_case(db, grant.org_id, case_id, lock=True)
    if case.status == "closed":
        raise HTTPException(409, "This matter no longer accepts intake")
    if payload.template_version != TEMPLATE_VERSION:
        raise HTTPException(409, "Questionnaire version changed. Reload and resubmit.")
    if payload.acknowledged_notice is not True:
        raise HTTPException(422, "The development data-use notice must be acknowledged")
    answers = validate_answers(payload.answers)
    digest = hashlib.sha256(json.dumps(
        {"version": TEMPLATE_VERSION, "answers": answers},
        ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    submission = StudyIntakeSubmission(
        org_id=grant.org_id, case_id=case_id, created_by_sub=principal.sub,
        template_version=TEMPLATE_VERSION, notice_version=NOTICE_VERSION,
        answers=answers, answer_sha256=digest)
    db.add(submission)
    db.flush()
    from app.access import OrgAccess
    record_event(db, OrgAccess(grant.org_id, principal, Role.viewer),
                 "portal.study_intake_submitted", "study_intake_submission",
                 submission.id, {"template_version": TEMPLATE_VERSION,
                                 "answer_count": len(answers)})
    db.commit()
    return {"id": str(submission.id), "submitted_at": submission.created_at,
            "answer_count": len(answers), "review_status": "awaiting_staff_review",
            "not_official_ircc_form": True}


@staff_router.get("")
def consultant_submissions(org_id: UUID, case_id: UUID,
                           db: Session = Depends(get_db),
                           access: OrgAccess = Depends(get_org_access)):
    allow(access, STAFF_READ)
    study_case(db, org_id, case_id)
    rows = db.scalars(select(StudyIntakeSubmission).where(
        StudyIntakeSubmission.org_id == org_id,
        StudyIntakeSubmission.case_id == case_id
    ).order_by(StudyIntakeSubmission.created_at.desc(),
               StudyIntakeSubmission.id.desc()).limit(20)).all()
    if not rows:
        return {"template": questionnaire(), "current_submission_id": None,
                "submissions": []}
    ids = [row.id for row in rows]
    decisions = db.scalars(select(StudyIntakeDecision).where(
        StudyIntakeDecision.org_id == org_id,
        StudyIntakeDecision.case_id == case_id,
        StudyIntakeDecision.submission_id.in_(ids))).all()
    decisions_by_submission = {}
    for decision in decisions:
        decisions_by_submission.setdefault(decision.submission_id, []).append(decision)
    return {
        "template": questionnaire(),
        "current_submission_id": str(rows[0].id),
        "submissions": [submission_view(row, decisions_by_submission.get(row.id, []))
                        for row in rows],
    }


@staff_router.post("/{submission_id}/answers/{field_path}/decide", status_code=201)
def decide_answer(org_id: UUID, case_id: UUID, submission_id: UUID, field_path: str,
                  payload: AnswerDecision, db: Session = Depends(get_db),
                  access: OrgAccess = Depends(get_org_access)):
    allow(access, STAFF_REVIEW)
    case = study_case(db, org_id, case_id, lock=True)
    if case.status == "closed":
        raise HTTPException(409, "Closed matter")
    row = db.scalar(select(StudyIntakeSubmission).where(
        StudyIntakeSubmission.org_id == org_id,
        StudyIntakeSubmission.case_id == case_id,
        StudyIntakeSubmission.id == submission_id))
    if row is None:
        raise HTTPException(404, "Submission not found")
    if row.template_version != TEMPLATE_VERSION or row.id != latest_for_case(db, org_id, case_id).id:
        raise HTTPException(409, "Older questionnaire revision is read-only")
    if field_path not in QUESTION_BY_PATH or field_path not in row.answers:
        raise HTTPException(404, "Questionnaire answer not found")
    prior = db.scalar(select(StudyIntakeDecision).where(
        StudyIntakeDecision.org_id == org_id,
        StudyIntakeDecision.submission_id == submission_id,
        StudyIntakeDecision.field_path == field_path))
    if prior is not None:
        raise HTTPException(409, "Answer already decided")
    fact_id = None
    if payload.decision == "accept":
        # A client-provided answer is not independent documentary evidence:
        # it becomes a PENDING fact, not a verified fact usable for IRCC preflight.
        fact = insert_fact_with_conflicts(db, access, case_id, FactCreate(
            field_path=field_path, value=row.answers[field_path],
            source_excerpt="Client questionnaire submission " + str(row.id) +
                           "; pending independent evidence verification"))
        fact_id = fact.id
    decision = StudyIntakeDecision(
        org_id=org_id, case_id=case_id, submission_id=submission_id,
        field_path=field_path, decision=payload.decision,
        created_fact_id=fact_id, reviewed_by_sub=access.principal.sub)
    db.add(decision)
    db.flush()
    record_event(db, access, "study_intake.answer_decided", "study_intake_decision",
                 decision.id, {"decision": payload.decision, "field_path": field_path,
                               "submission_id": str(submission_id)})
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Answer decision already exists") from None
    return {"decision": decision.decision, "field_path": decision.field_path,
            "created_fact_id": str(fact_id) if fact_id else None,
            "fact_status": "pending" if fact_id else None}
