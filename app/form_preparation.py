"""Review-only evidence-backed study-permit form preparation.

Never treats a canonical path as an official PDF field identifier. Cleared
source documents, reviewed case facts and unchanged source context required.
The packet records the subset only; complete IRCC forms are NOT supported.
"""
import hashlib
import json
from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.access import OrgAccess, READ_ROLES, allow, get_org_access
from app.db import get_db
from app.form_preparation_models import FormPreparationPacket
from app.form_evidence_coverage import reviewed_subset_report
from app.form_manifest import MANIFESTS
from app.manifest_mapping import resolve_manifest_evidence
from app.form_mapping import FormMappingBlocked
from app.ircc_registry import REGISTRY
from app.main import record_event
from app.models import Case, CaseDocument, CaseFact, CaseIssue
from app.package_models import CaseApplicationPackage
from app.portal_models import PortalSubmission
from app.schemas import Role

router = APIRouter(prefix="/api/v1/orgs/{org_id}/cases/{case_id}/form-preparation",
                   tags=["form-preparation"])
EDITORS = {Role.owner, Role.admin, Role.consultant}
MAPPING_VERSION = "canonical-study-reviewed-manifest-v2"
MAX_SNAPSHOTS = 30


class CapturePacket(BaseModel):
    expected_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    acknowledge_internal_subset_only: bool


def _context(db, org_id, case_id):
    case = db.scalar(select(Case).where(Case.org_id == org_id, Case.id == case_id))
    if case is None:
        raise HTTPException(404, "Matter not found")
    pkg = db.scalar(select(CaseApplicationPackage).where(
        CaseApplicationPackage.org_id == org_id, CaseApplicationPackage.case_id == case_id))
    if pkg is None:
        raise HTTPException(409, "Initialize the case application package first")
    if pkg.application_type != "study_permit" or case.application_type != "study_permit":
        raise HTTPException(409, "Study permit cases only")
    code = "IMM5709" if pkg.filing_context == "inside_canada" else "IMM1294"
    return case, pkg, REGISTRY[code]


def _scan_map(db, org_id, case_id):
    scans = db.scalars(select(PortalSubmission).where(
        PortalSubmission.org_id == org_id,
        PortalSubmission.case_id == case_id)).all()
    return {s.document_id: s.scan_status for s in scans}


def _render_snapshot(db, org_id, case_id):
    case, pkg, source = _context(db, org_id, case_id)
    facts = db.scalars(select(CaseFact).where(
        CaseFact.org_id == org_id, CaseFact.case_id == case_id)).all()
    docs = db.scalars(select(CaseDocument).where(
        CaseDocument.org_id == org_id, CaseDocument.case_id == case_id)).all()
    issues = db.scalars(select(CaseIssue).where(
        CaseIssue.org_id == org_id, CaseIssue.case_id == case_id,
        CaseIssue.status == "open")).all()
    scans = _scan_map(db, org_id, case_id)
    # Never infer clearance for staff uploads lacking explicit scan evidence.
    usable = {d.id: d for d in docs if scans.get(d.id) == "cleared"}
    blocked = []
    if case.status == "closed":
        blocked.append("case_closed")
    if (date.today() - source.last_checked).days > 30:
        blocked.append("official_source_observation_stale")
    if issues:
        blocked.append("open_case_evidence_issues")
    fields = []
    for label, path in source.preview_fields:
        matched = [f for f in facts if f.field_path == path and f.review_status != "rejected"]
        verified = [f for f in matched if f.review_status == "verified" and f.reviewed_by_sub]
        eligible = [f for f in verified if f.document_id in usable]
        values = {f.value.strip() for f in eligible if f.value and f.value.strip()}
        if len({f.value.strip() for f in matched if f.value and f.value.strip()}) > 1:
            status = "conflicting_evidence"
        elif matched and (any(f.review_status != "verified" for f in matched) or
                          any(not f.reviewed_by_sub for f in matched)):
            status = "unreviewed_facts"
        elif not verified:
            status = "missing_verified_fact"
        elif len(eligible) != len(verified):
            status = "source_scan_not_cleared"
        elif len(values) != 1:
            status = "conflicting_evidence"
        else:
            status = "verified_subset_field"
        fields.append({
            "label": label, "canonical_path": path, "status": status,
            "value": next(iter(values)) if status == "verified_subset_field" else None,
            "fact_ids": sorted(str(f.id) for f in eligible) if status == "verified_subset_field" else [],
            "document_ids": sorted({str(f.document_id) for f in eligible})
                            if status == "verified_subset_field" else [],
            "source_sha256": sorted({usable[f.document_id].sha256 for f in eligible})
                             if status == "verified_subset_field" else [],
        })
    if any(f["status"] != "verified_subset_field" for f in fields):
        blocked.append("required_preview_fields_unresolved")
    # The six legacy preview fields are no longer a sufficient packet gate.
    # Recheck the full current INTERNAL manifest, including conditional
    # applicability and date/choice syntax, before capturing any snapshot.
    coverage = reviewed_subset_report(
        source=source, case=case, facts=facts, documents=docs,
        scan_status=scans, open_issue_count=len(issues))
    if not coverage["verified_internal_subset"]:
        blocked.append("current_internal_manifest_unresolved")
    if coverage["source_recheck_required"]:
        blocked.append("current_internal_manifest_source_stale")
    # A complete INTERNAL evidence subset must also resolve through the
    # independently reviewed manifest-to-evidence kernel. This binds reviewed
    # conditional controller documents, including inactive branches, into a
    # separate provenance hash and blocks divergent resolver interpretations.
    mapping_evidence_sha256 = None
    mapping_resolved_field_count = 0
    if coverage["verified_internal_subset"]:
        try:
            mapping = resolve_manifest_evidence(
                manifest=MANIFESTS[source.code], org_id=org_id, case_id=case_id,
                facts=facts, documents=docs, scan_status_by_document=scans)
        except FormMappingBlocked:
            blocked.append("manifest_evidence_resolution_blocked")
        else:
            mapping_evidence_sha256 = mapping.snapshot_sha256
            mapping_resolved_field_count = len(mapping.field_to_canonical)
            if mapping.manifest_sha256 != coverage["manifest_sha256"]:
                blocked.append("manifest_evidence_revision_mismatch")
    data = {"case_id": str(case_id), "package_id": str(pkg.id),
            "form_code": source.code, "source_revision": source.revision_label,
            "source_observed_on": source.last_checked.isoformat(),
            "mapping_version": MAPPING_VERSION, "fields": fields,
            "manifest_version": coverage["manifest_version"],
            "manifest_sha256": coverage["manifest_sha256"],
            "manifest_coverage_sha256": coverage["snapshot_sha256"],
            "manifest_evidence_sha256": mapping_evidence_sha256,
            "manifest_evidence_field_count": mapping_resolved_field_count,
            "manifest_field_count": coverage["internal_preview_field_count"],
            "manifest_verified_field_count": coverage["verified_preview_field_count"],
            "manifest_unresolved_condition_count": sum(
                x["status"] == "unresolved_condition" for x in coverage["fields"]),
            "blockers": sorted(set(blocked))}
    digest = hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True,
                                       separators=(",", ":")).encode("utf-8")).hexdigest()
    return {**data, "snapshot_sha256": digest,
            "verified_subset_complete": not data["blockers"],
            "all_official_form_fields_mapped": False,
            "official_pdf_autofill_supported": False,
            "official_ircc_validation_verified": False,
            "submission_supported": False,
            "warning": "The current partial 24-field internal manifest and legacy preview are checked together. This is not a complete official IRCC form; no validated PDF, barcode or submission."}


def _view(packet):
    return {"id": str(packet.id), "case_id": str(packet.case_id),
            "form_code": packet.form_code, "source_revision": packet.source_revision,
            "mapping_version": packet.mapping_version,
            "snapshot_sha256": packet.snapshot_sha256,
            "fields": packet.field_snapshot["fields"],
            "manifest_version": packet.field_snapshot.get("manifest_version"),
            "manifest_sha256": packet.field_snapshot.get("manifest_sha256"),
            "manifest_coverage_sha256": packet.field_snapshot.get("manifest_coverage_sha256"),
            "manifest_evidence_sha256": packet.field_snapshot.get("manifest_evidence_sha256"),
            "manifest_evidence_field_count": packet.field_snapshot.get("manifest_evidence_field_count"),
            "manifest_field_count": packet.field_snapshot.get("manifest_field_count"),
            "manifest_verified_field_count": packet.field_snapshot.get("manifest_verified_field_count"),
            "blockers": packet.blocker_snapshot,
            "verified_subset_complete": packet.verified_subset_complete,
            "created_at": packet.created_at.isoformat(),
            "all_official_form_fields_mapped": False,
            "official_pdf_autofill_supported": False,
            "submission_supported": False}


@router.get("/preview")
def preview_packet(org_id: UUID, case_id: UUID, db: Session = Depends(get_db),
                   access: OrgAccess = Depends(get_org_access)):
    allow(access, READ_ROLES)
    return _render_snapshot(db, org_id, case_id)


@router.get("/packets")
def list_packets(org_id: UUID, case_id: UUID, db: Session = Depends(get_db),
                 access: OrgAccess = Depends(get_org_access)):
    allow(access, READ_ROLES)
    _context(db, org_id, case_id)
    packets = db.scalars(select(FormPreparationPacket).where(
        FormPreparationPacket.org_id == org_id,
        FormPreparationPacket.case_id == case_id
    ).order_by(FormPreparationPacket.created_at.desc(),
               FormPreparationPacket.id.desc()).limit(MAX_SNAPSHOTS)).all()
    return [_view(p) for p in packets]


@router.post("/packets", status_code=201)
def capture_packet(org_id: UUID, case_id: UUID, payload: CapturePacket,
                   db: Session = Depends(get_db),
                   access: OrgAccess = Depends(get_org_access)):
    allow(access, EDITORS)
    if not payload.acknowledge_internal_subset_only:
        raise HTTPException(422, "Acknowledge that this is not an official IRCC form")
    snapshot = _render_snapshot(db, org_id, case_id)
    if snapshot["snapshot_sha256"] != payload.expected_sha256:
        raise HTTPException(409, "Case facts or source status changed; reload preview")
    if not snapshot["verified_subset_complete"]:
        raise HTTPException(409, "Resolve all preview field and case evidence blockers first")
    pkt = FormPreparationPacket(
        org_id=org_id, case_id=case_id, package_id=UUID(snapshot["package_id"]),
        form_code=snapshot["form_code"], source_revision=snapshot["source_revision"],
        mapping_version=snapshot["mapping_version"],
        snapshot_sha256=snapshot["snapshot_sha256"],
        field_snapshot={key: snapshot[key] for key in (
            "fields", "manifest_version", "manifest_sha256",
            "manifest_coverage_sha256", "manifest_evidence_sha256",
            "manifest_evidence_field_count", "manifest_field_count",
            "manifest_verified_field_count")},
        blocker_snapshot=snapshot["blockers"], verified_subset_complete=True,
        created_by_sub=access.principal.sub)
    db.add(pkt)
    db.flush()
    record_event(db, access, "form.preparation_packet_captured", "case", case_id,
                 {"packet_id": str(pkt.id), "form_code": pkt.form_code,
                  "mapping_version": pkt.mapping_version,
                  "snapshot_sha256": pkt.snapshot_sha256})
    db.commit()
    return _view(pkt)
