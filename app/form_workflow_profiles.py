"""Source-anchored, version-pinned RCIC form workflow profiles.

This first profile covers IMM 5476 (11-2025). It is guidance to a licensed
professional, not a PDF mapping, eligibility opinion or submission authority.
"""
from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, Query
from uuid import UUID

from app.access import OrgAccess, READ_ROLES, allow, get_org_access

SOURCE_URL = ("https://www.canada.ca/en/immigration-refugees-citizenship/"
              "services/application/application-forms-guides/imm5476.html")
PDF_URL = ("https://www.canada.ca/content/dam/ircc/documents/pdf/english/"
           "kits/forms/imm5476/01-11-2025/imm5476e.pdf")
VERSION = "11-2025"
REVIEWED_ON = "2026-11-06"
SECTIONS = {
    "A": "Applicant information",
    "B": "Appointment of representative",
    "C": "Cancel the appointment of a representative",
    "D": "Withdraw role as a representative",
    "E": "Applicant declaration",
}


@dataclass(frozen=True)
class RepresentativeOperation:
    key: str
    title: str
    sections: tuple[str, ...]
    notes: tuple[str, ...] = ()


OPERATIONS = {
    "appoint": RepresentativeOperation("appoint", "Appoint a representative", ("A", "B", "E")),
    "update_contact": RepresentativeOperation(
        "update_contact", "Update appointed representative contact information", ("A", "B", "E")),
    "cancel": RepresentativeOperation("cancel", "Cancel the representative", ("A", "C", "E")),
    "replace": RepresentativeOperation(
        "replace", "Cancel and appoint a new representative", ("A", "B", "C", "E")),
    "withdraw": RepresentativeOperation(
        "withdraw", "Withdraw as representative", ("A", "D", "E"),
        ("The representative must review the Section D declaration, and sign it "
         "when they cannot obtain the applicant's signature in Section E.",)),
}
CHANNELS = {"portal_or_secure_account", "outside_portal"}


def imm5476_workflow(operation: str, channel: str, *, now: str = REVIEWED_ON) -> dict:
    choice = OPERATIONS.get(operation)
    if choice is None or channel not in CHANNELS:
        raise ValueError("Unsupported IMM 5476 operation or submission channel")
    signature = (
        "IRCC's published instructions permit the specified electronic signature "
        "methods when submitted through a portal or secure account; verify who "
        "must sign each applicable declaration and current portal instructions."
        if channel == "portal_or_secure_account" else
        "IRCC's published instructions call for handwritten signatures when "
        "submitted outside a portal or secure account; check any applicable "
        "alternative or accommodation in the current instructions."
    )
    return {
        "form_code": "IMM5476",
        "revision": VERSION,
        "source_url": SOURCE_URL,
        "official_pdf_url": PDF_URL,
        "source_observed_on": REVIEWED_ON,
        "operation": choice.key,
        "operation_title": choice.title,
        "submission_channel": channel,
        "sections": [{"code": key, "title": SECTIONS[key]} for key in choice.sections],
        "notes": [
            "The applicant and representative must review the information "
            "and applicable declarations; appointment is not implied by an uploaded PDF.",
            "Applicants with dependent children 18 or older need separate "
            "representation forms when they are also represented.",
            "Spouses/common-law partners may need separate authorization outside "
            "the specific sponsorship instructions described by IRCC.",
            signature,
            *choice.notes,
        ],
        "representative_identity_required": "B" in choice.sections,
        "applicant_signature_review_required": "E" in choice.sections,
        "reviewed_information_only": True,
        "field_mapping_available": False,
        "official_pdf_autofill_supported": False,
        "official_pdf_validation_verified": False,
        "submission_supported": False,
        "warning": (
            "Review the latest official IMM 5476 version, applicability, representative "
            "licence status and exact signature instructions. This internal checklist "
            "is not a completed form or proof that a client appointed an RCIC."
        ),
    }


router = APIRouter(prefix="/api/v1/orgs/{org_id}/ircc", tags=["ircc-form-workflows"])


@router.get("/forms/IMM5476/workflow")
def review_imm5476_workflow(
    org_id: UUID,
    operation: str = Query(min_length=4, max_length=32),
    submission_channel: str = Query(min_length=6, max_length=40),
    access: OrgAccess = Depends(get_org_access),
):
    allow(access, READ_ROLES)
    try:
        return imm5476_workflow(operation, submission_channel)
    except ValueError:
        raise HTTPException(422, "Unsupported IMM 5476 operation or submission channel") from None
