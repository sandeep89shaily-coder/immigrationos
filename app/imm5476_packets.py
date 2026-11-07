"""Capture review-only IMM5476 case evidence checkpoints.

No generated PDF, XDP export, signature, commercial vendor call, or submission.
A packet is a human-initiated, case-bound historical snapshot; field values
shown in it are independently source-reviewed but NOT legally sufficient.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.access import OrgAccess, READ_ROLES, allow, get_org_access
from app.db import get_db
from app.form_preparation import EDITORS
from app.imm5476_case_preview import (
    MAPPING_VERSION, build_preview, scan_status_by_document,
)
from app.imm5476_packet_models import IMM5476ReviewPacket
from app.main import record_event
from app.models import Case, CaseDocument, CaseFact, CaseIssue
from app.package_models import CaseApplicationPackage

router = APIRouter(
    prefix="/api/v1/orgs/{org_id}/cases/{case_id}/ircc/IMM5476",
    tags=["imm5476-evidence-preparation"],
)

MAX_HISTORY = 30
DISALLOWED_CAPTURE_FIELD_STATES = {
    "conflicting_evidence", "unreviewed_evidence",
    "invalid_evidence_value", "missing_case_document",
    "source_scan_not_cleared",
}


class CaptureIMM5476Evidence(BaseModel):
    expected_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    acknowledge_internal_only: bool


def current_snapshot(db: Session, org_id: UUID, case_id: UUID):
    case = db.scalar(select(Case).where(
        Case.org_id == org_id, Case.id == case_id))
    if case is None:
        raise HTTPException(404, "Matter not found")
    package = db.scalar(select(CaseApplicationPackage).where(
        CaseApplicationPackage.org_id == org_id,
        CaseApplicationPackage.case_id == case_id))
    if (package is None or package.application_type != "study_permit"
            or case.application_type != "study_permit"
            or not package.include_representative_form):
        raise HTTPException(
            409, "Initialize a study-permit package with IMM5476 selected first")
    facts = db.scalars(select(CaseFact).where(
        CaseFact.org_id == org_id, CaseFact.case_id == case_id)).all()
    documents = db.scalars(select(CaseDocument).where(
        CaseDocument.org_id == org_id, CaseDocument.case_id == case_id)).all()
    issues = db.scalars(select(CaseIssue).where(
        CaseIssue.org_id == org_id, CaseIssue.case_id == case_id,
        CaseIssue.status == "open")).all()
    report = build_preview(
        org_id=org_id, case=case, facts=facts, documents=documents,
        scan_status=scan_status_by_document(db, org_id, case_id),
        open_issue_count=len(issues))
    return package, report


def packet_to_dict(packet: IMM5476ReviewPacket, live_hash: str | None) -> dict:
    return {
        "id": str(packet.id),
        "form_code": "IMM5476",
        "case_id": str(packet.case_id),
        "source_revision": packet.source_revision,
        "mapping_version": packet.mapping_version,
        "snapshot_sha256": packet.snapshot_sha256,
        "is_current": packet.snapshot_sha256 == live_hash,
        "fields": packet.field_snapshot["fields"],
        "blockers_at_capture": packet.blocker_snapshot,
        "verified_observed_subset": packet.verified_observed_subset,
        "created_at": packet.created_at.isoformat(),
        "created_by_sub": packet.created_by_sub,
        "official_pdf_autofill_supported": False,
        "official_ircc_validation_verified": False,
        "submission_supported": False,
        "warning": "Internal reviewed-evidence checkpoint only; not an IRCC form.",
    }


@router.get("/packets")
def list_review_packets(
    org_id: UUID, case_id: UUID, response: Response,
    db: Session = Depends(get_db),
    access: OrgAccess = Depends(get_org_access),
):
    allow(access, READ_ROLES)
    _, live = current_snapshot(db, org_id, case_id)
    packets = db.scalars(select(IMM5476ReviewPacket).where(
        IMM5476ReviewPacket.org_id == org_id,
        IMM5476ReviewPacket.case_id == case_id
    ).order_by(IMM5476ReviewPacket.created_at.desc(),
               IMM5476ReviewPacket.id.desc()).limit(MAX_HISTORY)).all()
    response.headers["Cache-Control"] = "no-store"
    return [packet_to_dict(p, live["snapshot_sha256"]) for p in packets]


@router.post("/packets", status_code=201)
def capture_review_packet(
    org_id: UUID, case_id: UUID, payload: CaptureIMM5476Evidence,
    response: Response,
    db: Session = Depends(get_db),
    access: OrgAccess = Depends(get_org_access),
):
    allow(access, EDITORS)
    if not payload.acknowledge_internal_only:
        raise HTTPException(422, "Acknowledge that this is not a completed IRCC form")
    package, report = current_snapshot(db, org_id, case_id)
    if payload.expected_sha256 != report["snapshot_sha256"]:
        raise HTTPException(409, "The case evidence changed; reload preparation")
    if ("case_closed" in report["blockers"]
            or "open_evidence_issues" in report["blockers"]
            or "source_review_stale" in report["blockers"]):
        raise HTTPException(409, "Resolve case and source-review blockers first")
    if not report["verified_text_fields"]:
        raise HTTPException(409, "At least one evidence-backed field is required")
    invalid = sorted(
        {f["status"] for f in report["fields"]}
        & DISALLOWED_CAPTURE_FIELD_STATES)
    if invalid:
        raise HTTPException(
            409, "Resolve unsafe or disputed field statuses: " + ", ".join(invalid))
    # Missing fields are accepted for an explicitly PARTIAL checkpoint.
    # They remain visible and no official/export-ready status is granted.
    duplicate = db.scalar(select(IMM5476ReviewPacket.id).where(
        IMM5476ReviewPacket.org_id == org_id,
        IMM5476ReviewPacket.case_id == case_id,
        IMM5476ReviewPacket.snapshot_sha256 == report["snapshot_sha256"]
    ).limit(1))
    if duplicate is not None:
        raise HTTPException(409, "This evidence checkpoint already exists")
    packet = IMM5476ReviewPacket(
        org_id=org_id,
        case_id=case_id,
        package_id=package.id,
        source_revision=report["revision"],
        mapping_version=MAPPING_VERSION,
        snapshot_sha256=report["snapshot_sha256"],
        field_snapshot={
            "fields": report["fields"],
            "observed_text_fields": report["observed_text_fields"],
            "verified_text_fields": report["verified_text_fields"],
            "observed_radio_choices": report["observed_radio_choices"],
            "official_template_sha256": report["official_template_sha256"],
        },
        blocker_snapshot=report["blockers"],
        verified_observed_subset=report["verified_observed_subset"],
        created_by_sub=access.principal.sub,
    )
    db.add(packet)
    db.flush()
    record_event(
        db, access, "imm5476.evidence_checkpoint_captured", "case", case_id,
        {"packet_id": str(packet.id),
         "mapping_version": MAPPING_VERSION,
         "snapshot_sha256": report["snapshot_sha256"],
         "verified_text_fields": report["verified_text_fields"]})
    db.commit()
    db.refresh(packet)
    response.headers["Cache-Control"] = "no-store"
    return packet_to_dict(packet, report["snapshot_sha256"])
