"""Fail-closed bridge from versioned INTERNAL manifests to reviewed evidence.

This module deliberately does not map to official XFA/AcroForm identifiers,
render a PDF, decide eligibility, or authorize an IRCC submission.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Iterable, Mapping
from uuid import UUID

from app.form_manifest import FormManifest, expand_manifest
from app.form_mapping import FormMappingBlocked, ResolvedFieldPacket, resolve_verified_form_fields


@dataclass(frozen=True)
class ManifestEvidencePacket:
    manifest_sha256: str
    manifest_version: str
    form_revision: str
    filing_context: str
    field_to_canonical: dict[str, str]
    resolved: ResolvedFieldPacket
    snapshot_sha256: str
    review_only: bool = True
    official_pdf_supported: bool = False


def resolve_manifest_evidence(
    *, manifest: FormManifest, org_id: UUID, case_id: UUID,
    facts: Iterable, documents: Iterable,
    scan_status_by_document: Mapping[UUID, str],
    repeats: Mapping[str, int] | None = None,
) -> ManifestEvidencePacket:
    """Resolve applicable fields, including verified parents and repeat instances.

    Every condition parent is independently resolved through the same case-scoped,
    human-reviewed and scan-cleared evidence gate as the final mapped values.
    Unknown conditions or repeat counts block rather than silently omit fields.
    Supplied repeat counts are *explicit caller assertions*, not independently
    verified family cardinality; RCIC review is still mandatory.
    """
    facts = tuple(facts)
    documents = tuple(documents)
    parents: set[str] = set()
    for section in manifest.sections:
        if section.condition is not None:
            parents.add(section.condition.field_path)
        for field in section.fields:
            if field.condition is not None:
                parents.add(field.condition.field_path)

    verified_conditions: dict[str, str] = {}
    if parents:
        parent_map = {f"condition_{i}": path
                      for i, path in enumerate(sorted(parents))}
        try:
            parent_packet = resolve_verified_form_fields(
                org_id=org_id, case_id=case_id,
                field_to_canonical=parent_map, facts=facts, documents=documents,
                scan_status_by_document=scan_status_by_document)
        except FormMappingBlocked as exc:
            raise FormMappingBlocked("Manifest conditional parent unresolved: " + str(exc)) from exc
        verified_conditions = {
            path: parent_packet.values[name] for name, path in parent_map.items()
        }

    # A verified affirmative declaration cannot be reconciled with an
    # explicitly empty repeated collection; don't produce a false complete
    # packet just because the caller supplied zero items.
    for section in manifest.sections:
        condition = section.condition
        if (section.repeatable and condition is not None
                and condition.operator == "equals" and condition.expected == "yes"
                and verified_conditions.get(condition.field_path) == "yes"
                and repeats is not None and repeats.get(section.key) == 0):
            raise FormMappingBlocked("Affirmative repeat declaration cannot have zero records")

    try:
        sections = expand_manifest(manifest, verified_conditions, repeats)
    except ValueError as exc:
        raise FormMappingBlocked("Invalid manifest repeat declarations: " + str(exc)) from exc

    field_map: dict[str, str] = {}
    for section in sections:
        if section["state"].startswith("unresolved"):
            raise FormMappingBlocked("Manifest section applicability/count unresolved")
        if section["state"] == "inactive":
            continue
        for field in section["fields"]:
            if field["condition_state"] == "unresolved":
                raise FormMappingBlocked("Manifest field applicability unresolved")
            if field["condition_state"] == "inactive":
                continue
            # Internal deterministic keys, never official PDF control names.
            suffix = ("" if section.get("index") is None
                      else f"__{section['index']}")
            name = f"{section['section']}__{field['key']}{suffix}"
            if name in field_map:
                raise FormMappingBlocked("Duplicate expanded manifest key")
            field_map[name] = field["canonical_path"]
    if not field_map:
        raise FormMappingBlocked("No applicable internal manifest fields")

    resolved = resolve_verified_form_fields(
        org_id=org_id, case_id=case_id, field_to_canonical=field_map,
        facts=facts, documents=documents,
        scan_status_by_document=scan_status_by_document)
    identity = {
        "org_id": str(org_id), "case_id": str(case_id),
        "manifest_sha256": manifest.digest,
        "manifest_version": manifest.manifest_version,
        "form_revision": manifest.form_revision,
        "filing_context": manifest.filing_context,
        "field_to_canonical": field_map,
        "evidence_sha256": resolved.source_sha256,
        "explicit_repeats": dict(sorted((repeats or {}).items())),
    }
    digest = sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False,
                              separators=(",", ":")).encode("utf-8")).hexdigest()
    return ManifestEvidencePacket(
        manifest_sha256=manifest.digest,
        manifest_version=manifest.manifest_version,
        form_revision=manifest.form_revision,
        filing_context=manifest.filing_context,
        field_to_canonical=field_map, resolved=resolved,
        snapshot_sha256=digest)
