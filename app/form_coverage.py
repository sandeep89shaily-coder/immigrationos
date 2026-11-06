"""Publicly honest form-coverage ledger for each authenticated RCIC practice.

A discovered index entry is NEVER reported as a working/validated form.
"""
from uuid import UUID

from fastapi import APIRouter, Depends

from app.access import OrgAccess, READ_ROLES, allow, get_org_access
from app.ircc_registry import REGISTRY

router = APIRouter(prefix="/api/v1/orgs/{org_id}/ircc", tags=["ircc-form-factory"])


@router.get("/coverage")
def form_coverage(org_id: UUID, access: OrgAccess = Depends(get_org_access)):
    allow(access, READ_ROLES)
    forms = [{
        "code": s.code,
        "title": s.title,
        "filing_context": s.filing_context,
        "application_type": s.application_type,
        "observed_revision": s.revision_label,
        "source_url": s.ircc_source_url,
        "current_capability": "internal_read_only_preview",
        "official_pdf_autofill": False,
        "ircc_pdf_validation": False,
    } for s in REGISTRY.values()]
    forms.sort(key=lambda x: x["code"])
    return {
        "benchmark": "400+ forms advertised by an established competitor; not an official IRCC form count",
        "official_index_source": (
            "https://www.canada.ca/en/immigration-refugees-citizenship/"
            "services/application/application-forms-guides.html"
        ),
        "catalog_discovery": "research-only workflow; findings require manual publication",
        "indexed_contexts_with_internal_preview": len(forms),
        "official_pdf_autofill_supported": 0,
        "official_pdf_validation_verified": 0,
        "official_submission_integrations": 0,
        "synthetic_static_acroform_adapter": True,
        "forms": forms,
        "disclaimer": "Indexed or previewed forms are not automatically completed, validated, "
                      "submitted, or certified current. Use official IRCC instructions.",
    }
