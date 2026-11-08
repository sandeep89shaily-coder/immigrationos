# Unified internal evidence-to-form trace, version 1

This milestone provides a read-only, staff-only, case-scoped join across existing
authoritative services. It does not introduce a new kind of evidence, duplicate
a form mapping, or write applicant data.

**Endpoint:** `GET /api/v1/orgs/{org_id}/cases/{case_id}/internal-form-evidence-trace`

A study-permit package must exist with a supported filing context. It selects
the currently registered IMM1294 (outside Canada) or IMM5709 (inside Canada)
internal 14-field *incomplete* manifest, and uses its already implemented
source/evidence coverage. The same evaluation is joined with the 39-question
client-intake worklist and accepted former relationship / foreign-residence
records. The result contains:

- Every mapped internal question's canonical path, original source section
  where checked, submission/review status, document identifiers, verified fact
  identifiers, source-file hashes and the existing evidence disposition.
- All questionnaire questions outside the 14-field reviewed manifest, visibly
  flagged `not_in_reviewed_manifest`—not silently treated as mapped or complete.
- Individual record-specific canonical paths for the essential fields of each
  accepted supplemental history record. These remain unmapped to any official
  PDF/XFA widget, even if their values are backed by verified facts.
- A case-scoped trace fingerprint, underlying evidence coverage fingerprint,
  source recency flag, and mismatch/blocker counts.

**Provenance rules.** A verified internal mapped question requires a case-owned
document, completed document-scanning gate, explicit staff verification, no
conflicting candidate facts, and valid field syntax where supported. Client
submissions and reusable profile claims never substitute for documentary
evidence. An unsupported or unverified repeatable field stays unverified.
Changes in source facts or scan status alter the trace fingerprint. All rows
omit applicant answer values and client-supplied personal narrative. Only
staff-authorized case requests can retrieve document and evidence identifiers.
Responses are non-cacheable.

**Not a completion certificate.** Official PDF field identifiers are always
null. Professional verification, entire-form completion, validated PDF
generation, signing and submission are always false or unsupported. This
remains a synthetic-data engineering feature pending a complete IRCC form
field inventory and independently validated form-processing technology.
