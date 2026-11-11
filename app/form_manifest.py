"""Immutable internal form schemas with safe conditions and repeated sections.

These are authored *preparation* manifests, never official IRCC PDF field
inventories. Conditions use three-valued logic: unknown is not false.
No user-defined expressions or Python evaluation.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
import re
from typing import Mapping

from app.ircc_registry import ObservedForm, REGISTRY

_PATH = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*$")
_ID = re.compile(r"^[a-z][a-z0-9_]*$")
_ALLOWED = {"equals", "not_equals"}
MAX_REPEATS = 20


@dataclass(frozen=True)
class Condition:
    field_path: str
    operator: str
    expected: str

    def __post_init__(self):
        if not _PATH.fullmatch(self.field_path) or self.operator not in _ALLOWED:
            raise ValueError("Unapproved condition")
        if not isinstance(self.expected, str) or not self.expected or len(self.expected) > 128:
            raise ValueError("Invalid condition expected value")


@dataclass(frozen=True)
class FieldDefinition:
    key: str
    label: str
    canonical_path: str
    required: bool = True
    condition: Condition | None = None
    source_url: str | None = None
    source_section: str | None = None

    def __post_init__(self):
        if (self.source_url is None) != (self.source_section is None):
            raise ValueError("Source URL and section must be provided together")
        if self.source_url is not None and (
            not self.source_url.startswith("https://www.canada.ca/") or
            not self.source_section or len(self.source_section) > 140
        ):
            raise ValueError("Only source-traceable IRCC guidance is supported")
        if not _ID.fullmatch(self.key) or not self.label.strip():
            raise ValueError("Invalid field definition")
        if not _PATH.fullmatch(self.canonical_path):
            raise ValueError("Invalid canonical field path")


@dataclass(frozen=True)
class SectionDefinition:
    key: str
    title: str
    fields: tuple[FieldDefinition, ...]
    repeatable: bool = False
    condition: Condition | None = None

    def __post_init__(self):
        if not _ID.fullmatch(self.key) or not self.title.strip() or not self.fields:
            raise ValueError("Invalid section")
        keys = [field.key for field in self.fields]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate field key in section")


@dataclass(frozen=True)
class FormManifest:
    code: str
    form_revision: str
    manifest_version: str
    filing_context: str
    sections: tuple[SectionDefinition, ...]
    entire_form_inventoried: bool = False

    def __post_init__(self):
        if self.entire_form_inventoried:
            raise ValueError("Internal manifests cannot assert official full coverage")
        if not self.sections or len({x.key for x in self.sections}) != len(self.sections):
            raise ValueError("Duplicate or missing section")
        if not self.form_revision or not self.manifest_version or not self.filing_context:
            raise ValueError("Missing revision or filing context")

    def serializable(self) -> dict:
        return {
            "code": self.code, "form_revision": self.form_revision,
            "manifest_version": self.manifest_version, "filing_context": self.filing_context,
            "entire_form_inventoried": False,
            "sections": [
                {"key": section.key, "title": section.title,
                 "repeatable": section.repeatable,
                 "condition": condition_json(section.condition),
                 "fields": [
                     {"key": field.key, "label": field.label,
                      "canonical_path": field.canonical_path,
                      "required": field.required,
                      "condition": condition_json(field.condition),
                      "source_url": field.source_url,
                      "source_section": field.source_section}
                     for field in section.fields]}
                for section in self.sections],
        }

    @property
    def digest(self) -> str:
        return sha256(json.dumps(self.serializable(), sort_keys=True,
                                 separators=(",", ":")).encode("utf-8")).hexdigest()


def condition_json(condition: Condition | None) -> dict | None:
    return ({"field_path": condition.field_path,
             "operator": condition.operator, "expected": condition.expected}
            if condition is not None else None)


def evaluate_condition(condition: Condition | None, verified_values: Mapping[str, str]) -> str:
    """Return active, inactive or unresolved. Missing/conflicted facts are unresolved."""
    if condition is None:
        return "active"
    value = verified_values.get(condition.field_path)
    if value is None or value.strip().lower() == "unsure":
        return "unresolved"
    matched = value == condition.expected
    if condition.operator == "not_equals":
        matched = not matched
    return "active" if matched else "inactive"


def expand_manifest(manifest: FormManifest, verified_values: Mapping[str, str],
                    repeats: Mapping[str, int] | None = None) -> list[dict]:
    """Explicit repeat counts only: absent count is unresolved, never presumed zero.

    Repeat suffixes use .items.<index> for internal canonical paths, and do not
    claim the official IRCC XFA/PDF naming convention.
    """
    repeats = repeats or {}
    unknown = set(repeats) - {s.key for s in manifest.sections if s.repeatable}
    if unknown:
        raise ValueError("Unexpected repeat section")
    rows = []
    for section in manifest.sections:
        section_state = evaluate_condition(section.condition, verified_values)
        if section.repeatable:
            # Validate supplied counts even when a conditional section is hidden;
            # malformed inputs must never be silently accepted.
            count = repeats.get(section.key)
            if count is not None and (type(count) is not int or count < 0 or count > MAX_REPEATS):
                raise ValueError("Repeat count out of bounds")
            # A verified-negative parent makes the whole section inapplicable.
            # Do not demand a count for an inapplicable section. Conversely,
            # an unknown parent must remain unresolved even with count=0.
            if section_state != "active":
                rows.append({"section": section.key, "state": section_state, "fields": []})
                continue
            if count is None:
                rows.append({"section": section.key, "state": "unresolved_repeat_count",
                             "fields": []})
                continue
            indices = range(count)
        else:
            indices = (None,)
        for index in indices:
            fields = []
            for field in section.fields:
                field_state = evaluate_condition(field.condition, verified_values)
                state = section_state if section_state != "active" else field_state
                path = (field.canonical_path if index is None else
                        f"{field.canonical_path}.items.{index}")
                fields.append({"key": field.key, "label": field.label,
                               "canonical_path": path, "required": field.required,
                               "condition_state": state,
                               "source_url": field.source_url,
                               "source_section": field.source_section})
            rows.append({"section": section.key, "index": index,
                         "state": section_state, "fields": fields})
    return rows


def observed_subset_manifest(source: ObservedForm) -> FormManifest:
    fields = tuple(FieldDefinition(
        key=f"observed_{i}", label=label, canonical_path=path)
        for i, (label, path) in enumerate(source.preview_fields, start=1))
    return FormManifest(
        code=source.code, form_revision=source.revision_label,
        manifest_version="internal-preview-v1", filing_context=source.filing_context,
        sections=(SectionDefinition("observed", "Observed internal preview fields", fields),))


# Questions listed in both official IMM1294 and IMM5709 instruction pages.
# These identifiers are *internal* canonical paths, not observed XFA field IDs.
# Optional here means the software has not established the conditional rules for
# every applicant; it does not override the form's instructions.
GUIDED_FIELDS: tuple[tuple[str, str, str, str], ...] = (
    ("passport_issued_by", "Passport issuing country or territory",
     "identity.passport_issuing_country", "Passport / Question 2"),
    ("passport_issue_date", "Passport issue date",
     "identity.passport_issue_date", "Passport / Question 3"),
    ("passport_expiry_date", "Passport expiry date",
     "identity.passport_expiry_date", "Passport / Question 4"),
    ("institution_dli", "Designated Learning Institution number",
     "education.dli_number", "Details of Intended Study in Canada / Question 2"),
    ("study_from", "Expected study start date",
     "education.program_start_date", "Details of Intended Study in Canada / Question 3"),
    ("study_to", "Expected study end date",
     "education.program_end_date", "Details of Intended Study in Canada / Question 3"),
    ("tuition_cad", "Expected tuition in Canadian dollars",
     "finance.tuition_cad", "Details of Intended Study in Canada / Question 4"),
    ("available_funds_cad", "Available funds in Canadian dollars",
     "finance.available_funds_cad", "Details of Intended Study in Canada / Question 5"),
)


# Cross-checked against Personal details and National identity document
# instructions on BOTH IMM1294 and IMM5709. Source labels are per-form because
# the former relationship question number differs (1294 Q11, 5709 Q10).
# These are questionnaire-level canonical paths, NOT official XFA control IDs.
CONDITIONAL_GUIDED_FIELDS: tuple[tuple[str, str, str, str, str | None], ...] = (
    ("alias_flag", "Other name/alias ever used", "identity.has_other_names",
     "Personal details / Question 2", None),
    ("alias_family", "Other family name(s)", "identity.other_family_name",
     "Personal details / Question 2", "identity.has_other_names"),
    ("alias_given", "Other given name(s)", "identity.other_given_name",
     "Personal details / Question 2", "identity.has_other_names"),
    ("national_id_flag", "Has national identity document", "identity.has_national_id",
     "National identity document / Question 1", None),
    ("national_id_number", "National ID document number", "identity.national_id_number",
     "National identity document / Question 2", "identity.has_national_id"),
    ("national_id_country", "National ID issuing country", "identity.national_id_country",
     "National identity document / Question 3", "identity.has_national_id"),
    ("national_id_issued", "National ID issue date", "identity.national_id_issue_date",
     "National identity document / Question 4", "identity.has_national_id"),
    ("national_id_expires", "National ID expiry date", "identity.national_id_expiry_date",
     "National identity document / Question 5", "identity.has_national_id"),
    ("prior_relationship_flag", "Previous marriage/common-law relationship",
     "history.has_previous_relationships", "Personal details / Previous relationships", None),
    ("prior_residence_flag", "Other countries of residence, prior five years",
     "history.has_foreign_residences", "Personal details / Question 8", None),
)


def guided_subset_manifest(source: ObservedForm) -> FormManifest:
    observed = observed_subset_manifest(source)
    guided = SectionDefinition(
        key="ircc_guided_extra",
        title="Additional independently checked IRCC instruction questions",
        fields=tuple(FieldDefinition(
            key=key, label=label, canonical_path=path,
            required=False, source_url=source.ircc_source_url,
            source_section=section
        ) for key, label, path, section in GUIDED_FIELDS))
    extra = SectionDefinition(
        key="ircc_guided_conditional",
        title="Official guidance questions with explicit applicability checks",
        fields=tuple(FieldDefinition(
            key=key, label=label, canonical_path=path, required=False,
            condition=(Condition(parent, "equals", "yes") if parent else None),
            source_url=source.ircc_source_url,
            source_section=(("Personal details / Question 11" if source.code == "IMM1294"
                             else "Personal details / Question 10")
                            if key == "prior_relationship_flag" else section),
        ) for key, label, path, section, parent in CONDITIONAL_GUIDED_FIELDS))
    return FormManifest(
        code=source.code, form_revision=source.revision_label,
        manifest_version="ircc-guidance-conditional-subset-2026-11-08-v3",
        filing_context=source.filing_context,
        sections=(*observed.sections, guided, extra))


MANIFESTS: dict[str, FormManifest] = {
    code: guided_subset_manifest(source) for code, source in REGISTRY.items()
}
