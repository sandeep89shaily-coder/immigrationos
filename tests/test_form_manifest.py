"""Form-manifest semantics: version identity, conditions, repeats and boundaries."""
import pytest

from app.form_manifest import (
    Condition, FieldDefinition, FormManifest, SectionDefinition,
    MANIFESTS, evaluate_condition, expand_manifest,
)


def sample():
    return FormManifest(
        code="TEST", form_revision="synthetic-r1",
        manifest_version="test-v1", filing_context="test",
        sections=(
            SectionDefinition("person", "Person", (
                FieldDefinition("name", "Name", "identity.given_name"),
                FieldDefinition("extra", "Extra", "identity.extra",
                                condition=Condition("identity.has_extra", "equals", "yes")),
            )),
            SectionDefinition("history", "History", (
                FieldDefinition("employer", "Employer", "history.employer"),
            ), repeatable=True, condition=Condition("identity.has_history", "equals", "yes")),
        ),
    )


def test_registry_manifests_track_pinned_revision_and_guided_fields():
    for code in ("IMM1294", "IMM5709"):
        manifest = MANIFESTS[code]
        assert manifest.code == code
        assert manifest.entire_form_inventoried is False
        expanded = expand_manifest(manifest, {})
        assert len(expanded) == 3
        assert len(expanded[0]["fields"]) == 6
        assert len(expanded[1]["fields"]) == 8
        assert len(expanded[2]["fields"]) == 10
        assert manifest.manifest_version.endswith("-v3")
        assert all(field["source_url"].startswith("https://www.canada.ca/")
                   and field["source_section"]
                   for field in expanded[1]["fields"])
        assert all(field["required"] is False for field in expanded[1]["fields"])
        assert all(field["source_url"].startswith("https://www.canada.ca/")
                   for field in expanded[2]["fields"])
        assert all(field["condition_state"]=="unresolved" for field in expanded[2]["fields"]
                   if field["key"] in ("alias_family", "alias_given",
                                       "national_id_number", "national_id_country",
                                       "national_id_issued", "national_id_expires"))
        assert manifest.entire_form_inventoried is False
        assert len(manifest.digest) == 64
        assert manifest.digest == manifest.digest


def test_conditions_are_three_valued_not_silently_false():
    c = Condition("identity.has_extra", "equals", "yes")
    assert evaluate_condition(c, {}) == "unresolved"
    assert evaluate_condition(c, {"identity.has_extra": "yes"}) == "active"
    assert evaluate_condition(c, {"identity.has_extra": "no"}) == "inactive"
    assert evaluate_condition(Condition("identity.has_extra", "not_equals", "yes"),
                              {"identity.has_extra": "no"}) == "active"
    assert evaluate_condition(c, {"identity.has_extra":"unsure"}) == "unresolved"
    result = expand_manifest(sample(), {})
    assert result[0]["fields"][1]["condition_state"] == "unresolved"
    assert result[1]["state"] == "unresolved"


def test_repeat_sections_require_explicit_bounded_count():
    manifest = sample()
    rows = expand_manifest(manifest, {"identity.has_history": "yes"},
                           {"history": 2})
    assert [r["index"] for r in rows] == [None, 0, 1]
    assert rows[1]["fields"][0]["canonical_path"] == "history.employer.items.0"
    assert rows[2]["fields"][0]["canonical_path"] == "history.employer.items.1"
    for value in (-1, 21, True, 1.5):
        with pytest.raises(ValueError):
            expand_manifest(manifest, {}, {"history": value})
    with pytest.raises(ValueError):
        expand_manifest(manifest, {}, {"unexpected": 1})


def test_malformed_manifests_are_rejected():
    with pytest.raises(ValueError):
        Condition("identity.has_extra", "__import__", "yes")
    with pytest.raises(ValueError):
        FieldDefinition("bad key", "Title", "identity.given_name")
    with pytest.raises(ValueError):
        SectionDefinition("s", "Title", (
            FieldDefinition("name", "Name", "identity.given_name"),
            FieldDefinition("name", "Name Again", "identity.family_name")))
    with pytest.raises(ValueError):
        FormManifest("TEST", "r1", "m1", "test", sample().sections,
                     entire_form_inventoried=True)
    assert sample().digest != FormManifest(
        "TEST", "synthetic-r2", "test-v1", "test", sample().sections).digest


def test_expanded_guidance_source_is_immutable_manifest_identity():
    from app.form_manifest import GUIDED_FIELDS
    from app.ircc_registry import REGISTRY
    assert len({field[2] for field in GUIDED_FIELDS}) == 8
    for code in ("IMM1294", "IMM5709"):
        manifest = MANIFESTS[code]
        assert all(row.source_url == REGISTRY[code].ircc_source_url
                   for row in manifest.sections[1].fields)
        assert len({field.canonical_path for section in manifest.sections
                    for field in section.fields}) == 24
        assert len(manifest.digest) == 64
    with pytest.raises(ValueError):
        FieldDefinition("passport", "Passport", "identity.passport_number",
                        source_url="https://example.com/fake", source_section="Passport")
    with pytest.raises(ValueError):
        FieldDefinition("passport", "Passport", "identity.passport_number",
                        source_url="https://www.canada.ca/official")


def test_conditional_repeats_respect_parent_applicability_without_silent_defaults():
    manifest = sample()
    # A verified 'no' is sufficient to mark the entire repeat section inactive.
    inactive = expand_manifest(manifest, {"identity.has_history": "no"})
    assert inactive[1] == {"section": "history", "state": "inactive", "fields": []}
    # An unknown parent remains unresolved, even when an explicit zero is supplied.
    unknown = expand_manifest(manifest, {}, {"history": 0})
    assert unknown[1] == {"section": "history", "state": "unresolved", "fields": []}
    # A confirmed 'yes' requires an explicit count; zero is accepted only when explicit.
    active_missing = expand_manifest(manifest, {"identity.has_history": "yes"})
    assert active_missing[1]["state"] == "unresolved_repeat_count"
    assert len(expand_manifest(manifest, {"identity.has_history": "yes"},
                               {"history": 0})) == 1
    # Invalid counts remain rejected for inactive as well as active sections.
    for bad in (-1, 21, True, 1.5):
        with pytest.raises(ValueError):
            expand_manifest(manifest, {"identity.has_history": "no"}, {"history": bad})
