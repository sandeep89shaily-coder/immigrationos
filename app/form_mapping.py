"""Evidence-to-form mapping kernel: fail closed without verified, cleared sources.

Only call this with an independently reviewed per-revision field mapping.
It does not approve legal sufficiency or generate any official IRCC form.
"""
from dataclasses import dataclass
import hashlib
import json
from typing import Iterable, Mapping
from uuid import UUID


class FormMappingBlocked(ValueError):
    pass


@dataclass(frozen=True)
class ResolvedFieldPacket:
    values: dict[str, str]
    evidence_ids: dict[str, list[str]]
    document_ids: dict[str, list[str]]
    source_sha256: str
    review_only: bool = True


def resolve_verified_form_fields(
    *, org_id: UUID, case_id: UUID,
    field_to_canonical: Mapping[str, str],
    facts: Iterable,
    documents: Iterable,
    scan_status_by_document: Mapping[UUID, str],
) -> ResolvedFieldPacket:
    """Resolve one-to-one PDF field mappings against verified source documents.

    Every selected fact must be human-reviewed, case/tenant bound, document
    linked, and in a document with an explicitly cleared scan. No fallback to
    client answers, AI suggestions, stale snapshots, or a second tenant.
    """
    if not field_to_canonical or len(field_to_canonical) != len(set(field_to_canonical.values())):
        raise FormMappingBlocked("Review a nonempty unambiguous one-to-one mapping first")
    allowed = {str(d.id): d for d in documents if d.org_id == org_id and d.case_id == case_id}
    candidates = {}
    for fact in facts:
        if fact.org_id != org_id or fact.case_id != case_id:
            raise FormMappingBlocked("Evidence belongs to a different matter or firm")
        if fact.field_path not in field_to_canonical.values():
            continue
        if fact.review_status != "verified" or not fact.reviewed_by_sub:
            raise FormMappingBlocked("Mapped evidence has not been human-verified")
        doc = allowed.get(str(fact.document_id)) if fact.document_id else None
        if doc is None:
            raise FormMappingBlocked("Mapped fact has no case-bound source document")
        if scan_status_by_document.get(doc.id) != "cleared":
            raise FormMappingBlocked("Mapped source document has no cleared malware disposition")
        value = fact.value.strip()
        if not value or len(value) > 1000:
            raise FormMappingBlocked("Mapped fact value invalid or too long")
        candidates.setdefault(fact.field_path, []).append((value, fact, doc))

    values, evidence_ids, document_ids = {}, {}, {}
    for pdf_name, canonical_path in field_to_canonical.items():
        if not isinstance(pdf_name, str) or not pdf_name or not isinstance(canonical_path, str):
            raise FormMappingBlocked("Invalid reviewed form field mapping")
        sources = candidates.get(canonical_path, [])
        distinct = {v for v, _, _ in sources}
        if len(distinct) != 1:
            raise FormMappingBlocked("Missing or contradictory verified field: " + canonical_path)
        values[pdf_name] = next(iter(distinct))
        evidence_ids[pdf_name] = sorted(str(fact.id) for _, fact, _ in sources)
        document_ids[pdf_name] = sorted({str(doc.id) for _, _, doc in sources})

    canonical = json.dumps({
        "org_id": str(org_id), "case_id": str(case_id),
        "values": values, "evidence_ids": evidence_ids,
        "document_ids": document_ids,
        "source_hashes": sorted((str(doc_id), allowed[str(doc_id)].sha256)
                                for ids in document_ids.values() for doc_id in ids),
    }, separators=(",", ":"), sort_keys=True, ensure_ascii=False)
    return ResolvedFieldPacket(values, evidence_ids, document_ids,
                               hashlib.sha256(canonical.encode("utf-8")).hexdigest())
