"""Case-wide preparation pulse joins operational states without legal-ready claims."""
from types import SimpleNamespace
from uuid import UUID, uuid4

from app.case_preparation_pulse import compose_pulse
from app.models import Membership
from tests.test_application_package import case_setup, start


def obj(**kw):
    return SimpleNamespace(**kw)


def base(**kwargs):
    values=dict(
        case=obj(id=uuid4(),status="draft"),package=None,
        worklist=None,requirements=None,preflight=None,
        repeatables=[],repeatable_decisions=[],
        clarifications=[],replies=[],clarification_decisions=[],
        corrections=[],issues=[],tasks=[])
    values.update(kwargs)
    return compose_pulse(**values)


def test_empty_case_never_claims_ircc_ready():
    result=base()
    assert result["unresolved_count"]>=4
    assert result["area_counts"]["package"]==1
    assert result["internal_preflight_status"]=="unavailable"
    assert result["sources_need_recheck"] is True
    assert result["entire_ircc_form_complete"] is False
    assert result["submission_supported"] is False
    assert result["professional_eligibility_verified"] is False


def test_aggregate_distinguishes_pending_client_and_timeline_states():
    proposal=obj(id=uuid4(),kind="employment")
    req1,req2,req3=(obj(id=uuid4(),kind="address",flag_type="uncovered_period_for_review"),
                    obj(id=uuid4(),kind="employment",flag_type="overlap_for_review"),
                    obj(id=uuid4(),kind="education",flag_type="end_date_not_supplied"))
    result=base(
        package=obj(filing_context="outside_canada"),
        worklist={"questions":[
            {"status":"missing_answer","path":"identity.given_name","label":"Given name"},
            {"status":"evidence_verified","path":"identity.family_name","label":"Family name"},
            {"status":"not_applicable_to_latest_answer","path":"history.x","label":"N/A"}
        ],"preliminary_question_count":3,"document_verified_question_count":1},
        requirements={
            "requirements":[
                {"key":"passport","status":"missing","title":"Passport"},
                {"key":"funding","status":"staff_reviewed_document","title":"Funds"}],
            "unresolved_requirements":["passport"],"source_recheck_required":False},
        preflight={"blockers":["No supporting documents have been uploaded"],
                   "acknowledgement":"not_acknowledged",
                   "internal_preflight_status":"blocked",
                   "source_recheck_required":False},
        repeatables=[proposal],
        clarifications=[req1,req2,req3],
        replies=[obj(request_id=req2.id),obj(request_id=req3.id)],
        clarification_decisions=[obj(request_id=req3.id,decision="reviewed")],
        issues=[obj(id=uuid4(),status="open")],
        tasks=[obj(id=uuid4(),status="open")])
    assert result["area_counts"]["intake"]==1
    assert result["area_counts"]["documents"]==1
    assert result["area_counts"]["client_records"]==1
    assert result["area_counts"]["timeline"]==3
    assert result["area_counts"]["form_preflight"]==2
    assert result["area_counts"]["case_issues"]==1
    assert result["area_counts"]["case_tasks"]==1
    assert result["verified_preliminary_question_count"]==1
    assert {r["status"] for r in result["worklist_items"] if r["area"]=="timeline"}=={
        "awaiting_client","awaiting_staff","reviewed_not_corrected"}
    assert result["submission_supported"] is False


def test_corrected_clarification_and_decided_proposal_no_longer_pending():
    request=obj(id=uuid4(),kind="address",flag_type="end_date_not_supplied")
    proposal=obj(id=uuid4(),kind="family")
    result=base(
        clarifications=[request],
        replies=[obj(request_id=request.id)],
        clarification_decisions=[obj(request_id=request.id,decision="reviewed")],
        corrections=[obj(request_id=request.id)],
        repeatables=[proposal],
        repeatable_decisions=[obj(proposal_id=proposal.id)])
    assert result["area_counts"]["timeline"]==0
    assert result["area_counts"]["client_records"]==0
    assert not result["operational_worklist_clear"]


def test_live_case_scope_without_package_and_after_package(api):
    client, who, factory=api
    org,case,root=case_setup(api,"preparation-pulse-live")
    url=f"/api/v1/orgs/{org}/cases/{case}/preparation-pulse"
    initial=client.get(url)
    assert initial.status_code==200,initial.text
    assert initial.headers["cache-control"]=="no-store"
    assert initial.json()["area_counts"]["package"]==1
    assert initial.json()["official_pdf_generation_supported"] is False
    assert start(client,root,representative=False).status_code==201
    ready=client.get(url)
    assert ready.status_code==200,ready.text
    result=ready.json()
    assert result["filing_context"]=="outside_canada"
    assert result["preliminary_question_count"]>=18
    assert result["area_counts"]["intake"]>0
    assert result["area_counts"]["documents"]>0
    assert result["internal_preflight_status"]=="blocked"
    assert result["official_pdf_generation_supported"] is False
    with factory() as db:
        db.add(Membership(org_id=UUID(org),subject="unassigned-pulse",
                          role="consultant",is_active=True))
        db.commit()
    who["sub"]="unassigned-pulse"
    assert client.get(url).status_code==404
    who["sub"]="unrelated-pulse"
    assert client.get(url).status_code==404
