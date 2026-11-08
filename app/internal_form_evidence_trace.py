"""Single, read-only case-scoped evidence-to-internal-form trace.

The existing form manifest and evidence evaluators remain authoritative.
Only status, identifiers and source fingerprints are exposed; raw client
answers, sensitive declaration details and verified fact values are omitted.
"""
from hashlib import sha256
import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.access import OrgAccess, READ_ROLES, allow, get_org_access
from app.applicant_models import ApplicantProfile, FamilyMember
from app.applicant_history_models import ApplicantHistory
from app.applicant_supplemental_history_models import ApplicantSupplementalHistory
from app.db import get_db
from app.form_evidence_coverage import reviewed_subset_report
from app.imm5476_case_preview import scan_status_by_document
from app.intake_models import StudyIntakeSubmission, StudyIntakeDecision
from app.ircc_registry import REGISTRY
from app.models import Case, CaseDocument, CaseFact, CaseIssue
from app.package_models import CaseApplicationPackage
from app.repeatable_intake_models import ClientRepeatableProposal, ClientRepeatableDecision
from app.study_intake_worklist import build_worklist
from app.supplemental_disclosure_review import REQUIRED_FIELDS, supplemental_fact_path

router = APIRouter(prefix="/api/v1/orgs/{org_id}/cases/{case_id}",
                   tags=["internal-form-trace"])
VERSION = "internal-evidence-to-form-trace-v1"


def build_trace(*, case, package, coverage, worklist, facts,
                supplemental_records):
    """Join existing truth-source statuses without promoting a client claim."""
    if (package.org_id != case.org_id or package.case_id != case.id or
            coverage["case_id"] != str(case.id) or
            worklist["case_id"] != str(case.id)):
        raise ValueError("Inconsistent case-scoped inputs")
    questions = {q["path"]: q for q in worklist["questions"]}
    record_evidence = {
        (r["kind"], record["record_id"]): record
        for r in worklist["supplemental_disclosure_review"]
        for record in r["evidence"]
    }
    trace = []
    mapped_paths = set()
    for item in coverage["fields"]:
        path = item["canonical_path"]
        mapped_paths.add(path)
        q = questions.get(path)
        evidence_status = item["status"]
        row = {
            "area": "form_field",
            "canonical_path": path,
            "label": item["label"],
            "manifest_mapping": "internal_question_path_only",
            "form_code": coverage["code"],
            "condition_state": item["condition_state"],
            "evidence_status": evidence_status,
            "questionnaire_status": q["status"] if q else "no_questionnaire_mapping",
            "questionnaire_decision": q["latest_answer_decision"] if q else None,
            "has_latest_client_answer": q["has_latest_submitted_answer"] if q else False,
            "source_url": item["source_url"] or coverage["ircc_source_url"],
            "source_section": item["source_section"],
            "verified_evidence_ids": item["evidence_ids"],
            "case_document_ids": item["document_ids"],
            "source_sha256": item["source_hashes"],
            "review_status": (
                "mapped_with_reviewed_document_evidence"
                if evidence_status == "verified_source_value" else
                "review_required"),
            "official_pdf_field_id": None,
            "professional_verified": False,
        }
        trace.append(row)
    # Questionnaire questions not present in the limited form manifest must
    # stay visible as unmapped, not silently treated as completed form fields.
    for path, q in questions.items():
        if path in mapped_paths:
            continue
        trace.append({
            "area": "questionnaire_unmapped",
            "canonical_path": path, "label": q["label"],
            "manifest_mapping": "not_in_reviewed_manifest",
            "form_code": coverage["code"],
            "condition_state": q["condition_state"],
            "evidence_status": q["evidence_status"],
            "questionnaire_status": q["status"],
            "questionnaire_decision": q["latest_answer_decision"],
            "has_latest_client_answer": q["has_latest_submitted_answer"],
            "source_url": None, "source_section": None,
            "verified_evidence_ids": [], "case_document_ids": [],
            "source_sha256": [],
            "review_status": "requires_form_mapping_and_professional_review",
            "official_pdf_field_id": None,
            "professional_verified": False,
        })
    # Each repeatable record keeps its stable own canonical path. Missing
    # evidence metadata is not promoted, even if a staff review imported it.
    for record in supplemental_records:
        if record.org_id != case.org_id or record.client_id != case.client_id:
            continue
        check = record_evidence.get((record.kind, str(record.id)))
        unresolved = set(check["unresolved_field_keys"]) if check else set(
            REQUIRED_FIELDS.get(record.kind, ()))
        for key in REQUIRED_FIELDS.get(record.kind, ()):
            trace.append({
                "area": "repeatable_history",
                "canonical_path": supplemental_fact_path(record, key),
                "label": record.kind.replace("_", " ") + " / " +
                         key.replace("_", " "),
                "manifest_mapping": "not_in_reviewed_manifest",
                "form_code": coverage["code"],
                "condition_state": "professional_applicability_unresolved",
                "evidence_status": (
                    "evidence_review_required" if key in unresolved
                    else "matching_reviewed_document_evidence"),
                "questionnaire_status": "unverified_master_history_claim",
                "questionnaire_decision": None,
                "has_latest_client_answer": False,
                "source_url": None, "source_section": None,
                "verified_evidence_ids": [], "case_document_ids": [],
                "source_sha256": [],
                "review_status": "requires_form_mapping_and_professional_review",
                "official_pdf_field_id": None,
                "professional_verified": False,
                "record_id": str(record.id),
                "record_version": record.version,
            })
    counts = {
        "mapped_field_count": len(coverage["fields"]),
        "mapped_fields_with_reviewed_document_evidence": sum(
            t["review_status"] == "mapped_with_reviewed_document_evidence"
            for t in trace),
        "unmapped_questionnaire_fields": sum(
            t["area"] == "questionnaire_unmapped" for t in trace),
        "unmapped_repeatable_history_fields": sum(
            t["area"] == "repeatable_history" for t in trace),
        "trace_rows": len(trace),
    }
    result = {
        "schema_version": VERSION,
        "case_id": str(case.id),
        "form_code": coverage["code"],
        "filing_context": package.filing_context,
        "manifest_sha256": coverage["manifest_sha256"],
        "evidence_coverage_sha256": coverage["snapshot_sha256"],
        "source_recheck_required": coverage["source_recheck_required"],
        "coverage_blockers": coverage["blockers"],
        "questionnaire_version": worklist["questionnaire_version"],
        "latest_questionnaire_submission_id": worklist["latest_submission_id"],
        "supplemental_disclosure_states": [
            {"kind": r["kind"], "status": r["status"],
             "accepted_record_count": r["accepted_record_count"]}
            for r in worklist["supplemental_disclosure_review"]],
        "counts": counts,
        "rows": trace,
        "official_pdf_fields_verified": False,
        "entire_ircc_form_complete": False,
        "submission_supported": False,
        "warning": "Internal and incomplete trace. Verified document value matching does not establish legal applicability or an official PDF mapping.",
    }
    # Snapshot is deterministic and case-scoped; no applicant field values are
    # returned. Client-provided content is never embedded in this response.
    result["snapshot_sha256"] = sha256(json.dumps(
        result, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return result


@router.get("/internal-form-evidence-trace")
def internal_form_evidence_trace(
        org_id: UUID, case_id: UUID, response: Response,
        db: Session = Depends(get_db),
        access: OrgAccess = Depends(get_org_access)):
    allow(access, READ_ROLES)
    case = db.scalar(select(Case).where(Case.org_id == org_id, Case.id == case_id))
    if case is None:
        raise HTTPException(404, "Matter not available")
    package = db.scalar(select(CaseApplicationPackage).where(
        CaseApplicationPackage.org_id == org_id,
        CaseApplicationPackage.case_id == case_id))
    if (case.application_type != "study_permit" or package is None or
            package.filing_context not in ("inside_canada", "outside_canada")):
        raise HTTPException(409, "Initialize a supported study-permit package first")
    code = "IMM5709" if package.filing_context == "inside_canada" else "IMM1294"
    profile = db.scalar(select(ApplicantProfile).where(
        ApplicantProfile.org_id == org_id, ApplicantProfile.client_id == case.client_id))
    family = db.scalars(select(FamilyMember).where(
        FamilyMember.org_id == org_id, FamilyMember.client_id == case.client_id)).all()
    histories = db.scalars(select(ApplicantHistory).where(
        ApplicantHistory.org_id == org_id, ApplicantHistory.client_id == case.client_id)).all()
    supplemental = db.scalars(select(ApplicantSupplementalHistory).where(
        ApplicantSupplementalHistory.org_id == org_id,
        ApplicantSupplementalHistory.client_id == case.client_id)).all()
    submission = db.scalar(select(StudyIntakeSubmission).where(
        StudyIntakeSubmission.org_id == org_id,
        StudyIntakeSubmission.case_id == case_id
    ).order_by(StudyIntakeSubmission.created_at.desc(),
               StudyIntakeSubmission.id.desc()).limit(1))
    decisions = db.scalars(select(StudyIntakeDecision).where(
        StudyIntakeDecision.org_id == org_id,
        StudyIntakeDecision.case_id == case_id,
        StudyIntakeDecision.submission_id == submission.id)).all() if submission else []
    proposals = db.scalars(select(ClientRepeatableProposal).where(
        ClientRepeatableProposal.org_id == org_id,
        ClientRepeatableProposal.case_id == case_id)).all()
    proposal_decisions = db.scalars(select(ClientRepeatableDecision).where(
        ClientRepeatableDecision.org_id == org_id,
        ClientRepeatableDecision.case_id == case_id)).all()
    facts = db.scalars(select(CaseFact).where(
        CaseFact.org_id == org_id, CaseFact.case_id == case_id)).all()
    documents = db.scalars(select(CaseDocument).where(
        CaseDocument.org_id == org_id, CaseDocument.case_id == case_id)).all()
    issues = db.scalars(select(CaseIssue).where(
        CaseIssue.org_id == org_id, CaseIssue.case_id == case_id,
        CaseIssue.status == "open")).all()
    scans = scan_status_by_document(db, org_id, case_id)
    coverage = reviewed_subset_report(
        source=REGISTRY[code], case=case, facts=facts, documents=documents,
        scan_status=scans, open_issue_count=len(issues))
    worklist = build_worklist(
        case=case, form_code=code, profile=profile, family=family,
        histories=histories, submission=submission, decisions=decisions,
        facts=facts, documents=documents, scans=scans,
        supplemental_records=supplemental, proposals=proposals,
        proposal_decisions=proposal_decisions)
    response.headers["Cache-Control"] = "no-store"
    return build_trace(case=case, package=package, coverage=coverage,
                       worklist=worklist, facts=facts,
                       supplemental_records=supplemental)
