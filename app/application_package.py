"""An actual case worklist for IRCC forms and supporting evidence.

Study permits first, using the *existing* evidence template and IRCC sources.
This does not autofill, officially validate, sign, or submit a government form.
Manual form copies are immutable case-scoped evidence with human review.
"""
from datetime import date, datetime, timezone
from hashlib import sha256
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.access import OrgAccess, READ_ROLES, allow, get_org_access
from app.db import get_db, set_db_context
from app.evidence_matrix import _matrix
from app.form_workflow_profiles import SOURCE_URL as REPRESENTATIVE_SOURCE, VERSION as REPRESENTATIVE_REVISION
from app.ircc_registry import REGISTRY, source_metadata
from app.main import record_event
from app.malware_scan import scan_bytes, ScannerUnavailable
from app.models import Case, CaseDocument
from app.package_models import CaseApplicationPackage, PackageFormCopy
from app.portal_models import PortalSubmission
from app.schemas import Role
from app.storage import load_blob

router = APIRouter(prefix="/api/v1/orgs/{org_id}/cases/{case_id}/package",
                   tags=["application-package"])
MANAGERS = {Role.owner, Role.admin, Role.consultant}
INTAKE = MANAGERS | {Role.assistant}
PROFILE_VERSION = "study-permit-form-worklist-v1-2026-11-06"


def now():
    return datetime.now(timezone.utc)


class CreatePackage(BaseModel):
    filing_context: str = Field(pattern=r"^(inside_canada|outside_canada)$")
    include_representative_form: bool


class LinkFormCopy(BaseModel):
    document_id: UUID


class ReviewCopy(BaseModel):
    decision: str = Field(pattern=r"^(accept|reject)$")
    note: str = Field(min_length=25, max_length=900)
    current_ircc_source_checked: bool
    reviewed_pdf_in_appropriate_software: bool

    def model_post_init(self, context):
        self.note = self.note.strip()
        if len(self.note) < 25:
            raise ValueError("Substantive form-copy review note required")


def _case(db, org_id, case_id, *, lock=False) -> Case:
    query = select(Case).where(Case.org_id == org_id, Case.id == case_id)
    case = db.scalar(query.with_for_update() if lock else query)
    if case is None:
        raise HTTPException(404, "Case not found")
    if case.application_type != "study_permit":
        raise HTTPException(409, "The first application package supports study permits only")
    return case


def _package(db, org_id, case_id):
    return db.scalar(select(CaseApplicationPackage).where(
        CaseApplicationPackage.org_id == org_id,
        CaseApplicationPackage.case_id == case_id))


def _slots(pkg: CaseApplicationPackage) -> list[dict]:
    code = "IMM5709" if pkg.filing_context == "inside_canada" else "IMM1294"
    base = REGISTRY[code]
    rows = [{
        "code": code, "title": base.title, "required_in_this_package": True,
        "source_url": base.ircc_source_url, "source_revision": base.revision_label,
        "source_observed_on": base.last_checked.isoformat(),
        "source_recheck_required": (date.today() - base.last_checked).days > 30,
        "reason": "Selected study-permit filing route; applicability requires professional review.",
    }]
    if pkg.include_representative_form:
        rows.append({
            "code": "IMM5476", "title": "Use of a Representative",
            "required_in_this_package": True, "source_url": REPRESENTATIVE_SOURCE,
            "source_revision": REPRESENTATIVE_REVISION,
            "source_observed_on": "2026-11-06",
            "source_recheck_required": (date.today() - date(2026, 11, 6)).days > 30,
            "reason": "Consultant selected representative documentation; operation and signatures require review.",
        })
    return rows


def _copies(db, org_id, case_id) -> list[PackageFormCopy]:
    return db.scalars(select(PackageFormCopy).where(
        PackageFormCopy.org_id == org_id,
        PackageFormCopy.case_id == case_id
    ).order_by(PackageFormCopy.created_at.desc(), PackageFormCopy.id.desc())).all()


def _summary(db, pkg: CaseApplicationPackage):
    form_copies = _copies(db, pkg.org_id, pkg.case_id)
    copies_by_code = {}
    for item in form_copies:
        copies_by_code.setdefault(item.form_code, []).append(item)
    forms = []
    for item in _slots(pkg):
        versions = copies_by_code.get(item["code"], [])
        current = versions[0] if versions else None
        status = ("not_uploaded" if current is None else
                  "quarantined" if current.scan_status == "quarantined" else
                  "scanner_rejected" if current.scan_status == "rejected" else
                  "pending_professional_review" if current.review_status == "pending" else
                  "rejected_by_reviewer" if current.review_status == "rejected" else
                  "staff_reviewed_copy")
        forms.append({**item, "status": status, "copy_count": len(versions),
                      "latest_copy": None if current is None else {
                          "id": str(current.id), "document_id": str(current.document_id),
                          "scan_status": current.scan_status,
                          "review_status": current.review_status,
                          "source_revision": current.source_revision,
                          "document_sha256": current.linked_document_sha256,
                          "reviewed_by_sub": current.reviewed_by_sub,
                          "created_at": current.created_at,
                      }})
    evidence = _matrix(db, pkg.org_id, pkg.case_id, pkg.filing_context)
    return {
        "initialized": True,
        "id": str(pkg.id), "case_id": str(pkg.case_id),
        "application_type": pkg.application_type,
        "filing_context": pkg.filing_context,
        "profile_version": pkg.profile_version,
        "include_representative_form": pkg.include_representative_form,
        "forms": forms,
        "document_requirements": evidence["requirements"],
        "open_evidence_issue_count": evidence["open_evidence_issue_count"],
        "sources_need_recheck": any(f["source_recheck_required"] for f in forms)
                                or evidence["source_recheck_required"],
        "all_selected_form_copies_staff_reviewed": all(
            f["status"] == "staff_reviewed_copy" for f in forms),
        "official_pdf_autofill_supported": False,
        "official_validation_verified": False,
        "submission_supported": False,
        "release_status": "blocked_official_validation_not_implemented",
        "warning": (
            "This is a case worklist, not a complete or officially validated IRCC "
            "application. Document checklists are non-exhaustive; review current "
            "IRCC requirements, applicable exceptions, signatures and any barcodes "
            "independently before preparing a filing."
        ),
    }


@router.get("")
def read_package(org_id: UUID, case_id: UUID,
                 db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    allow(access, READ_ROLES)
    case = _case(db, org_id, case_id)
    pkg = _package(db, org_id, case_id)
    if pkg is None:
        return {
            "initialized": False, "case_id": str(case.id),
            "application_type": case.application_type,
            "available_filing_contexts": ["inside_canada", "outside_canada"],
            "official_pdf_autofill_supported": False,
            "submission_supported": False,
            "warning": "Select a filing context and confirm representative-form applicability.",
        }
    return _summary(db, pkg)


@router.post("", status_code=201)
def create_package(org_id: UUID, case_id: UUID, payload: CreatePackage,
                   db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    allow(access, MANAGERS)
    case = _case(db, org_id, case_id, lock=True)
    if case.status == "closed":
        raise HTTPException(409, "Cannot start a package on a closed matter")
    previous = _package(db, org_id, case_id)
    if previous:
        if (previous.filing_context == payload.filing_context
                and previous.include_representative_form == payload.include_representative_form):
            return _summary(db, previous)
        raise HTTPException(409, "Package route is locked; changing the filing route needs a reviewed revision workflow")
    pkg = CaseApplicationPackage(
        org_id=org_id, case_id=case_id, application_type=case.application_type,
        filing_context=payload.filing_context,
        include_representative_form=payload.include_representative_form,
        profile_version=PROFILE_VERSION, created_by_sub=access.principal.sub)
    db.add(pkg)
    db.flush()
    record_event(db, access, "package.started", "case_application_package", pkg.id,
                 {"filing_context": pkg.filing_context,
                  "representative_form_selected": pkg.include_representative_form,
                  "profile_version": PROFILE_VERSION})
    db.commit()
    # PostgreSQL app.tenant_id is transaction-local; reset it for the SELECTs
    # used by the response after committing the package creation transaction.
    set_db_context(db, access.principal.sub, org_id)
    return _summary(db, pkg)


def _slot(pkg, form_code):
    slot = next((item for item in _slots(pkg)
                 if item["code"] == form_code.upper()), None)
    if slot is None:
        raise HTTPException(409, "Form not selected for this application package")
    return slot


@router.post("/forms/{form_code}/copies", status_code=201)
def link_form_copy(org_id: UUID, case_id: UUID, form_code: str,
                   payload: LinkFormCopy, db: Session = Depends(get_db),
                   access: OrgAccess = Depends(get_org_access)):
    allow(access, INTAKE)
    case = _case(db, org_id, case_id, lock=True)
    if case.status == "closed":
        raise HTTPException(409, "Closed cases cannot receive forms")
    pkg = _package(db, org_id, case_id)
    if not pkg:
        raise HTTPException(409, "Create the application package first")
    slot = _slot(pkg, form_code)
    doc = db.scalar(select(CaseDocument).where(
        CaseDocument.org_id == org_id, CaseDocument.case_id == case_id,
        CaseDocument.id == payload.document_id))
    if doc is None:
        raise HTTPException(404, "Document is not part of this case")
    if doc.mime_type != "application/pdf" or not doc.filename.lower().endswith(".pdf"):
        raise HTTPException(415, "Use a PDF form copy")
    portal = db.scalar(select(PortalSubmission).where(
        PortalSubmission.org_id == org_id, PortalSubmission.case_id == case_id,
        PortalSubmission.document_id == doc.id))
    if portal and portal.scan_status != "cleared":
        raise HTTPException(423, "Client document is still quarantined or rejected")
    raw = load_blob(doc.storage_key)
    if sha256(raw).hexdigest() != doc.sha256 or not raw.startswith(b"%PDF-"):
        raise HTTPException(409, "Stored PDF identity or header does not match")
    if not raw or len(raw) > 15_000_000:
        raise HTTPException(413, "Form copy exceeds the size limit")
    try:
        scan_status = scan_bytes(raw).status
    except ScannerUnavailable:
        scan_status = "quarantined"
    if scan_status not in {"cleared", "quarantined", "rejected"}:
        raise HTTPException(503, "Scanner did not return a recognized disposition")
    entry = PackageFormCopy(
        org_id=org_id, case_id=case_id, package_id=pkg.id,
        document_id=doc.id, form_code=slot["code"],
        source_revision=slot["source_revision"],
        source_observed_on=date.fromisoformat(slot["source_observed_on"]),
        linked_document_sha256=doc.sha256,
        scan_status=scan_status, review_status="pending",
        created_by_sub=access.principal.sub,
    )
    try:
        db.add(entry)
        db.flush()
        record_event(db, access, "package.form_copy_received", "package_form_copy", entry.id,
                     {"form_code": entry.form_code, "scan_status": scan_status})
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "That document was already linked to this package") from None
    return {"copy_id": str(entry.id), "form_code": entry.form_code,
            "scan_status": entry.scan_status, "review_status": entry.review_status,
            "official_pdf_autofill_supported": False,
            "official_validation_verified": False}


def _copy(db, org_id, case_id, copy_id):
    row = db.scalar(select(PackageFormCopy).where(
        PackageFormCopy.org_id == org_id, PackageFormCopy.case_id == case_id,
        PackageFormCopy.id == copy_id))
    if row is None:
        raise HTTPException(404, "Form copy not found")
    return row


@router.post("/copies/{copy_id}/scan")
def rescan_copy(org_id: UUID, case_id: UUID, copy_id: UUID,
                db: Session = Depends(get_db), access: OrgAccess = Depends(get_org_access)):
    allow(access, MANAGERS)
    _case(db, org_id, case_id)
    record = _copy(db, org_id, case_id, copy_id)
    if record.review_status != "pending" or record.scan_status != "quarantined":
        raise HTTPException(409, "Only pending quarantined copies can be rescanned")
    doc = db.scalar(select(CaseDocument).where(
        CaseDocument.org_id == org_id, CaseDocument.case_id == case_id,
        CaseDocument.id == record.document_id))
    if doc is None:
        raise HTTPException(409, "Original document is missing")
    raw = load_blob(doc.storage_key)
    if sha256(raw).hexdigest() != record.linked_document_sha256:
        raise HTTPException(409, "Document content checksum changed")
    try:
        verdict = scan_bytes(raw).status
    except ScannerUnavailable:
        raise HTTPException(503, "Scanner unavailable; form remains quarantined") from None
    if verdict not in {"cleared", "quarantined", "rejected"}:
        raise HTTPException(503, "Invalid scanner disposition")
    record.scan_status = verdict
    record_event(db, access, "package.form_copy_scanned", "package_form_copy", record.id,
                 {"scan_status": verdict})
    db.commit()
    return {"copy_id": str(record.id), "scan_status": verdict}


@router.post("/copies/{copy_id}/review")
def review_copy(org_id: UUID, case_id: UUID, copy_id: UUID,
                payload: ReviewCopy, db: Session = Depends(get_db),
                access: OrgAccess = Depends(get_org_access)):
    allow(access, MANAGERS)
    case = _case(db, org_id, case_id, lock=True)
    if case.status == "closed":
        raise HTTPException(409, "Closed cases are read-only")
    pkg = _package(db, org_id, case_id)
    record = _copy(db, org_id, case_id, copy_id)
    latest = next((x for x in _copies(db, org_id, case_id)
                   if x.form_code == record.form_code), None)
    if latest is None or latest.id != record.id:
        raise HTTPException(409, "A newer document copy must be reviewed instead")
    if record.review_status != "pending":
        raise HTTPException(409, "Form copy already reviewed")
    if record.scan_status != "cleared":
        raise HTTPException(423, "Form copy must pass malware scanning")
    slot = _slot(pkg, record.form_code)
    if slot["source_recheck_required"]:
        raise HTTPException(409, "Official form source observation is stale; recheck and update the registry")
    if not payload.current_ircc_source_checked or not payload.reviewed_pdf_in_appropriate_software:
        raise HTTPException(422, "A professional must check current IRCC form instructions and inspect the PDF")
    record.review_status = "accepted" if payload.decision == "accept" else "rejected"
    record.reviewed_at = now()
    record.reviewed_by_sub = access.principal.sub
    record.review_note = payload.note
    record_event(db, access, "package.form_copy_reviewed", "package_form_copy", record.id,
                 {"form_code": record.form_code, "decision": record.review_status,
                  "source_revision": record.source_revision})
    db.commit()
    return {"copy_id": str(record.id), "review_status": record.review_status,
            "staff_inspection_recorded": True,
            "actual_ircc_validation_independently_verified": False,
            "submission_supported": False}
