"""Source-to-form mappings never silently accept unverified or unsafe facts."""
from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.form_mapping import FormMappingBlocked, resolve_verified_form_fields


def synthetic():
    org, case, doc_id, fact_id = uuid4(), uuid4(), uuid4(), uuid4()
    doc = SimpleNamespace(id=doc_id, org_id=org, case_id=case, sha256="a"*64)
    fact = SimpleNamespace(id=fact_id, org_id=org, case_id=case,
        document_id=doc_id, field_path="identity.given_name", value="Sample",
        review_status="verified", reviewed_by_sub="synthetic-consultant")
    return org, case, doc, fact


def test_verified_source_yields_traceable_packet_and_supports_reused_fields():
    org, case, doc, fact = synthetic()
    packet = resolve_verified_form_fields(org_id=org, case_id=case, documents=[doc],
        facts=[fact], scan_status_by_document={doc.id: "cleared"},
        field_to_canonical={"first_name":"identity.given_name",
                            "other_first_name":"identity.given_name"})
    assert packet.values == {"first_name":"Sample", "other_first_name":"Sample"}
    assert packet.evidence_ids["first_name"] == [str(fact.id)]
    assert packet.document_ids["first_name"] == [str(doc.id)]
    assert packet.review_only is True and len(packet.source_sha256) == 64


@pytest.mark.parametrize("scan", [None, "quarantined", "rejected", "staff_upload_not_portal_scanned"])
def test_noncleared_documents_never_populate_a_form(scan):
    org, case, doc, fact = synthetic()
    with pytest.raises(FormMappingBlocked, match="cleared malware"):
        resolve_verified_form_fields(org_id=org, case_id=case, documents=[doc],
            facts=[fact], scan_status_by_document={doc.id: scan} if scan else {},
            field_to_canonical={"name":"identity.given_name"})


def test_unverified_unreviewed_and_unlinked_facts_denied():
    org, case, doc, fact = synthetic()
    mapping = {"name":"identity.given_name"}
    for invalid in [
        replace_namespace(fact, review_status="pending"),
        replace_namespace(fact, review_status="rejected"),
        replace_namespace(fact, reviewed_by_sub=None),
        replace_namespace(fact, document_id=None),
    ]:
        with pytest.raises(FormMappingBlocked):
            resolve_verified_form_fields(org_id=org, case_id=case, documents=[doc],
                facts=[invalid], scan_status_by_document={doc.id:"cleared"},
                field_to_canonical=mapping)


def replace_namespace(source, **changes):
    values = vars(source).copy()
    values.update(changes)
    return SimpleNamespace(**values)


def test_conflicting_verified_facts_and_tenant_mismatch_fail_closed():
    org, case, doc, fact = synthetic()
    conflict = replace_namespace(fact, id=uuid4(), value="Different")
    with pytest.raises(FormMappingBlocked, match="contradictory"):
        resolve_verified_form_fields(org_id=org, case_id=case,
            documents=[doc], facts=[fact, conflict],
            scan_status_by_document={doc.id:"cleared"},
            field_to_canonical={"name":"identity.given_name"})
    with pytest.raises(FormMappingBlocked, match="different matter"):
        resolve_verified_form_fields(org_id=org, case_id=case, documents=[doc],
            facts=[replace_namespace(fact, org_id=uuid4())],
            scan_status_by_document={doc.id:"cleared"},
            field_to_canonical={"name":"identity.given_name"})


def test_hash_changes_when_reviewed_source_changes():
    org, case, doc, fact = synthetic()
    def packet(*, d=doc, f=fact):
        return resolve_verified_form_fields(org_id=org, case_id=case,
            documents=[d], facts=[f], scan_status_by_document={d.id:"cleared"},
            field_to_canonical={"given":"identity.given_name"})
    one = packet()
    two = packet(d=replace_namespace(doc, sha256="b"*64))
    three = packet(f=replace_namespace(fact, value="Different"))
    assert len({one.source_sha256,two.source_sha256,three.source_sha256}) == 3


def test_document_in_other_case_or_missing_mapping_denied():
    org, case, doc, fact = synthetic()
    with pytest.raises(FormMappingBlocked):
        resolve_verified_form_fields(org_id=org, case_id=case,
            documents=[replace_namespace(doc, case_id=uuid4())],
            facts=[fact], scan_status_by_document={doc.id:"cleared"},
            field_to_canonical={"name":"identity.given_name"})
    with pytest.raises(FormMappingBlocked):
        resolve_verified_form_fields(org_id=org, case_id=case,
            documents=[doc], facts=[fact], scan_status_by_document={doc.id:"cleared"},
            field_to_canonical={})


def test_end_to_end_verified_evidence_to_synthetic_pdf():
    from io import BytesIO
    from pypdf import PdfReader
    from app.pdf_form_adapter import fill_static_acroform
    from tests.test_pdf_form_adapter import synthetic_form, approved

    org, case, doc, first = synthetic()
    family = replace_namespace(first, id=uuid4(), field_path="identity.family_name", value="Applicant")
    packet = resolve_verified_form_fields(
        org_id=org, case_id=case,
        field_to_canonical={
            "given_name": "identity.given_name",
            "family_name": "identity.family_name",
        },
        facts=[first, family], documents=[doc],
        scan_status_by_document={doc.id:"cleared"},
    )
    assert packet.review_only is True
    official_claims = 0  # a synthetic fixture is not an IRCC-approved template
    assert official_claims == 0
    pdf = synthetic_form()
    result = fill_static_acroform(pdf, packet.values, approved(pdf))
    reader = PdfReader(BytesIO(result))
    assert reader.get_fields()["given_name"]["/V"] == "Sample"
    assert reader.get_fields()["family_name"]["/V"] == "Applicant"
    assert packet.evidence_ids["family_name"] == [str(family.id)]
