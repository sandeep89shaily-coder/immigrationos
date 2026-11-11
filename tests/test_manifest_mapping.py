"""Synthetic-only tests for versioned manifest-to-evidence mapping."""
from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.form_manifest import Condition, FieldDefinition, FormManifest, SectionDefinition
from app.form_mapping import FormMappingBlocked
from app.manifest_mapping import resolve_manifest_evidence


def manifest(revision="synthetic-r1"):
    return FormManifest(
        "SYNTHETIC", revision, "internal-v1", "outside",
        (
            SectionDefinition("person", "Person", (
                FieldDefinition("given", "Given", "identity.given_name"),
                FieldDefinition("alias", "Alias", "identity.alias",
                                condition=Condition("identity.has_alias", "equals", "yes")),
            )),
            SectionDefinition("history", "Employment", (
                FieldDefinition("employer", "Employer", "history.employer"),
            ), repeatable=True,
                condition=Condition("history.has_employment", "equals", "yes")),
        ),
    )


def fixture():
    org, case = uuid4(), uuid4()
    documents, facts, scans = [], [], {}
    def add(path, value, scan="cleared"):
        doc_id = uuid4()
        documents.append(SimpleNamespace(
            id=doc_id, org_id=org, case_id=case, sha256=uuid4().hex * 2))
        facts.append(SimpleNamespace(
            id=uuid4(), org_id=org, case_id=case, document_id=doc_id,
            field_path=path, value=value, review_status="verified",
            reviewed_by_sub="synthetic-rcic"))
        scans[doc_id] = scan
    return org, case, documents, facts, scans, add


def resolve(m, org, case, docs, facts, scans, repeats=None):
    return resolve_manifest_evidence(
        manifest=m, org_id=org, case_id=case, documents=docs, facts=facts,
        scan_status_by_document=scans, repeats=repeats)


def test_verified_conditional_yes_and_repeated_sections_have_traceable_names():
    org, case, docs, facts, scans, add = fixture()
    for path, value in [
        ("identity.given_name", "Sample"),
        ("identity.has_alias", "yes"),
        ("identity.alias", "Example"),
        ("history.has_employment", "yes"),
        ("history.employer.items.0", "Company A"),
        ("history.employer.items.1", "Company B"),
    ]:
        add(path, value)
    packet = resolve(manifest(), org, case, docs, facts, scans, {"history": 2})
    assert packet.field_to_canonical["history__employer__1"] == "history.employer.items.1"
    assert packet.resolved.values["person__alias"] == "Example"
    assert packet.resolved.values["history__employer__0"] == "Company A"
    assert packet.resolved.review_only and packet.review_only
    assert packet.official_pdf_supported is False
    assert len(packet.snapshot_sha256) == 64
    assert all(packet.resolved.evidence_ids.values())
    changed = resolve(manifest("synthetic-r2"), org, case, docs, facts, scans,
                      {"history": 2})
    assert changed.manifest_sha256 != packet.manifest_sha256
    assert changed.snapshot_sha256 != packet.snapshot_sha256


def test_negative_parent_hides_branch_without_fabricating_repeat_count():
    org, case, docs, facts, scans, add = fixture()
    add("identity.given_name", "Sample")
    add("identity.has_alias", "no")
    add("history.has_employment", "no")
    packet = resolve(manifest(), org, case, docs, facts, scans)
    assert packet.resolved.values == {"person__given": "Sample"}
    assert "person__alias" not in packet.field_to_canonical
    assert not any(k.startswith("history__") for k in packet.field_to_canonical)


def test_unknown_or_uncleared_controller_is_never_interpreted_as_negative():
    org, case, docs, facts, scans, add = fixture()
    add("identity.given_name", "Sample")
    add("history.has_employment", "no")
    with pytest.raises(FormMappingBlocked, match="conditional parent unresolved"):
        resolve(manifest(), org, case, docs, facts, scans)
    add("identity.has_alias", "no", scan="quarantined")
    with pytest.raises(FormMappingBlocked, match="cleared malware"):
        resolve(manifest(), org, case, docs, facts, scans)
    scans[facts[-1].document_id] = "cleared"
    facts[-1].value = "unsure"
    with pytest.raises(FormMappingBlocked, match="applicability unresolved"):
        resolve(manifest(), org, case, docs, facts, scans)


def test_active_repeat_requires_explicit_count_and_all_instance_evidence():
    org, case, docs, facts, scans, add = fixture()
    for path, value in [
        ("identity.given_name", "Sample"),
        ("identity.has_alias", "no"),
        ("history.has_employment", "yes"),
        ("history.employer.items.0", "Company A"),
    ]:
        add(path, value)
    with pytest.raises(FormMappingBlocked, match="count unresolved"):
        resolve(manifest(), org, case, docs, facts, scans)
    with pytest.raises(FormMappingBlocked, match="Missing or contradictory"):
        resolve(manifest(), org, case, docs, facts, scans, {"history": 2})
    packet = resolve(manifest(), org, case, docs, facts, scans, {"history": 1})
    assert packet.resolved.values["history__employer__0"] == "Company A"
    with pytest.raises(FormMappingBlocked, match="repeat declarations"):
        resolve(manifest(), org, case, docs, facts, scans, {"history": True})


def test_cross_case_and_unreviewed_parent_never_drives_conditions():
    org, case, docs, facts, scans, add = fixture()
    add("identity.given_name", "Sample")
    add("identity.has_alias", "no")
    add("history.has_employment", "no")
    facts[-1].review_status = "pending"
    with pytest.raises(FormMappingBlocked):
        resolve(manifest(), org, case, docs, facts, scans)
    facts[-1].review_status = "verified"
    facts[1].case_id = uuid4()
    with pytest.raises(FormMappingBlocked, match="different matter"):
        resolve(manifest(), org, case, docs, facts, scans)
