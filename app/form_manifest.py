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

    def __post_init__(self):
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
                      "condition": condition_json(field.condition)}
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
    if value is None:
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
            count = repeats.get(section.key)
            if count is None:
                rows.append({"section": section.key, "state": "unresolved_repeat_count",
                             "fields": []})
                continue
            if type(count) is not int or count < 0 or count > MAX_REPEATS:
                raise ValueError("Repeat count out of bounds")
            if section_state != "active":
                rows.append({"section": section.key, "state": section_state, "fields": []})
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
                               "condition_state": state})
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


MANIFESTS: dict[str, FormManifest] = {
    code: observed_subset_manifest(source) for code, source in REGISTRY.items()
}
