"""Conservative cross-check between study-intake declarations and supplemental histories.

A client's yes/no/unsure answer never certifies legal applicability. Staff
acceptance imports an unverified claim, not verified case evidence.
"""
from uuid import UUID

from app.imm5476_case_preview import _field_status

CONTROLLERS = {
    "previous_relationship": "history.has_previous_relationships",
    "foreign_residence": "history.has_foreign_residences",
}
REQUIRED_FIELDS = {
    "previous_relationship": ("relationship_type", "family_name", "given_name",
                              "start_date", "end_date"),
    "foreign_residence": ("country", "status", "start_date", "end_date"),
}


def supplemental_fact_path(record, field: str) -> str:
    return f"supplemental.{record.kind}.r_{record.id.hex}.{field}"


def supplemental_disclosure_review(*, case, submission, proposals, decisions,
                                   records, facts, documents, scans):
    """Return non-sensitive statuses and stable IDs; never include values.

    All inputs are constrained to the active case/organization; supplemental
    reusable records may be shared across cases of the *same client*.
    """
    scoped_proposals = [
        p for p in proposals if p.org_id == case.org_id and p.case_id == case.id]
    scoped_decisions = {
        d.proposal_id: d for d in decisions
        if d.org_id == case.org_id and d.case_id == case.id}
    scoped_records = [
        r for r in records if r.org_id == case.org_id and
        r.client_id == case.client_id]
    scoped_facts = [
        f for f in facts if f.org_id == case.org_id and f.case_id == case.id]
    scoped_docs = {
        d.id: d for d in documents
        if d.org_id == case.org_id and d.case_id == case.id}
    results = []
    for kind, controller in CONTROLLERS.items():
        answer = (submission.answers.get(controller)
                  if submission is not None and
                  submission.org_id == case.org_id and
                  submission.case_id == case.id else None)
        category_proposals = [p for p in scoped_proposals if p.kind == kind]
        pending = [p for p in category_proposals if p.id not in scoped_decisions]
        rejected = [p for p in category_proposals
                    if p.id in scoped_decisions and
                    scoped_decisions[p.id].decision == "dismiss"]
        accepted = [r for r in scoped_records if r.kind == kind]
        evidence_rows = []
        for record in accepted:
            missing = []
            for field in REQUIRED_FIELDS[kind]:
                canonical = supplemental_fact_path(record, field)
                candidate = [f for f in scoped_facts if f.field_path == canonical]
                evidence = _field_status(canonical, candidate, scoped_docs, scans)
                # Verified facts must match the actual current historical claim,
                # even when a document and scan status are otherwise cleared.
                if (evidence["status"] != "verified_source_value" or
                    evidence["value"] != str(record.details.get(field, ""))):
                    missing.append(field)
            evidence_rows.append({
                "record_id": str(record.id),
                "verified_required_field_count": len(REQUIRED_FIELDS[kind]) - len(missing),
                "required_field_count": len(REQUIRED_FIELDS[kind]),
                "unresolved_field_keys": missing,
                "all_required_fields_supported": not missing,
                "record_is_professionally_verified": False,
            })
        if answer not in ("yes", "no"):
            status = "declaration_missing_or_unsure"
        elif answer == "no" and (category_proposals or accepted):
            status = "disclosure_conflict_review_required"
        elif answer == "no":
            status = "no_disclosure_reported"
        elif pending:
            status = "awaiting_staff_record_review"
        elif not accepted:
            status = ("dismissed_records_need_recollection" if rejected
                      else "missing_repeatable_records")
        elif any(not r["all_required_fields_supported"] for r in evidence_rows):
            status = "supplemental_evidence_review_required"
        else:
            status = "professional_relevance_review_required"
        results.append({
            "kind": kind, "controller_path": controller,
            "declaration_state": answer if answer in ("yes", "no", "unsure")
                                 else "not_answered",
            "status": status,
            "pending_proposal_ids": [str(p.id) for p in pending],
            "accepted_record_ids": [str(r.id) for r in accepted],
            "dismissed_proposal_count": len(rejected),
            "accepted_record_count": len(accepted),
            "evidence": evidence_rows,
            "all_records_professionally_verified": False,
            "ircc_form_section_complete": False,
        })
    return results
