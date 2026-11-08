"""Unit tests for scoped supplemental disclosure evidence checks."""
from types import SimpleNamespace as Obj
from uuid import uuid4

from app.supplemental_disclosure_review import (
    supplemental_disclosure_review, supplemental_fact_path)


def sample():
    org, case_id, client = uuid4(), uuid4(), uuid4()
    case=Obj(id=case_id, org_id=org, client_id=client)
    return case, Obj(org_id=org, case_id=case_id,
                     answers={"history.has_previous_relationships":"yes",
                              "history.has_foreign_residences":"no"})


def evaluate(case, submission, records, *, proposals=(), decisions=(),
             facts=(), documents=(), scans=None):
    return {row["kind"]: row for row in supplemental_disclosure_review(
        case=case, submission=submission, records=records, proposals=proposals,
        decisions=decisions, facts=facts, documents=documents,
        scans=scans or {})}


def test_canonical_evidence_requires_all_five_matching_document_fields():
    case, submission=sample()
    details={"relationship_type":"married", "family_name":"Former",
             "given_name":"Synthetic", "start_date":"2010-01-01",
             "end_date":"2014-12-31"}
    record=Obj(id=uuid4(),org_id=case.org_id,client_id=case.client_id,
               kind="previous_relationship",details=details)
    doc=Obj(id=uuid4(),org_id=case.org_id,case_id=case.id,sha256="d"*64)
    facts=[Obj(org_id=case.org_id,case_id=case.id,
               field_path=supplemental_fact_path(record,key),value=value,
               review_status="verified",reviewed_by_sub="consultant",
               document_id=doc.id,id=uuid4()) for key,value in details.items()]
    not_scanned=evaluate(case,submission,[record],facts=facts,documents=[doc])
    assert not_scanned["previous_relationship"]["status"]=="supplemental_evidence_review_required"
    with_scan=evaluate(case,submission,[record],facts=facts,documents=[doc],
                       scans={doc.id:"cleared"})
    assert with_scan["previous_relationship"]["status"]=="professional_relevance_review_required"
    evidence=with_scan["previous_relationship"]["evidence"][0]
    assert evidence["verified_required_field_count"]==5
    assert evidence["all_required_fields_supported"] is True
    assert evidence["record_is_professionally_verified"] is False
    assert with_scan["previous_relationship"]["ircc_form_section_complete"] is False
    facts[0].value="different record"
    mismatch=evaluate(case,submission,[record],facts=facts,documents=[doc],
                      scans={doc.id:"cleared"})
    assert mismatch["previous_relationship"]["evidence"][0]["verified_required_field_count"]==4
    assert mismatch["previous_relationship"]["status"]=="supplemental_evidence_review_required"


def test_cross_case_evidence_and_cross_client_records_never_count():
    case, submission=sample()
    other_record=Obj(id=uuid4(),org_id=case.org_id,client_id=uuid4(),
                     kind="previous_relationship",details={"family_name":"Other"})
    other_proposal=Obj(id=uuid4(),org_id=case.org_id,case_id=uuid4(),
                       kind="previous_relationship")
    checks=evaluate(case,submission,[other_record],proposals=[other_proposal])
    assert checks["previous_relationship"]["status"]=="missing_repeatable_records"
    assert checks["previous_relationship"]["accepted_record_count"]==0
    assert checks["previous_relationship"]["pending_proposal_ids"]==[]


def test_no_answer_or_unsure_cannot_silently_clear_contradicting_record():
    case, submission=sample()
    record=Obj(id=uuid4(),org_id=case.org_id,client_id=case.client_id,
               kind="foreign_residence", details={})
    for answer in (None,"unsure","no"):
        submission.answers={"history.has_foreign_residences":answer}
        result=evaluate(case,submission,[record])["foreign_residence"]
        expected=("disclosure_conflict_review_required" if answer=="no"
                  else "declaration_missing_or_unsure")
        assert result["status"]==expected
        assert result["all_records_professionally_verified"] is False
