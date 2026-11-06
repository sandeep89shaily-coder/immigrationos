"""Development-only form-template inspection endpoint; no storage or publication."""
import re
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.access import OrgAccess, allow, get_org_access
from app.form_template_inspector import (MAX_TEMPLATE_BYTES, TemplateInspectionError,
                                         inspect_pdf_template)
from app.schemas import Role
from app.settings import get_settings

router = APIRouter(prefix="/api/v1/orgs/{org_id}/ircc", tags=["ircc-form-technical-inspection"])
REVIEW_ROLES = {Role.owner, Role.admin, Role.consultant}
FORM_CODE_RE = re.compile(r"^(?:IMM|CIT|IRM|EMP|EIMM)\s?[0-9]{4}(?:\s?[A-Z0-9]{1,4})?$", re.I)


@router.post("/inspect-template")
async def inspect_template_upload(
    org_id: UUID,
    form_code: str = Form(min_length=6, max_length=24),
    file: UploadFile = File(...),
    access: OrgAccess = Depends(get_org_access),
):
    allow(access, REVIEW_ROLES)
    if get_settings().environment == "production":
        raise HTTPException(403, "Untrusted PDF template inspection is not production-approved")
    if not FORM_CODE_RE.fullmatch(form_code.strip()):
        raise HTTPException(422, "Form code does not match the expected IRCC form identifier pattern")
    # Never persist a user-supplied PDF template, claim its provenance, or
    # run extraction with the identity of an immigration client.
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(422, "Only an uncompleted PDF template is accepted")
    blob = await file.read(MAX_TEMPLATE_BYTES + 1)
    if len(blob) > MAX_TEMPLATE_BYTES:
        raise HTTPException(413, "PDF template exceeds size limit")
    try:
        report = inspect_pdf_template(blob)
    except TemplateInspectionError as exc:
        raise HTTPException(422, str(exc)) from None
    return {
        "declared_form_code": form_code.strip().upper().replace(" ", ""),
        "declared_form_code_verified": False,
        "template_source_verified": False,
        "bytes_persisted": False,
        **report,
    }
