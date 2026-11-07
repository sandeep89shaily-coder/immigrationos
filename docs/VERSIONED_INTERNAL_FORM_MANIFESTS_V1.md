# Versioned internal IRCC form manifests (v1)

This change introduces immutable form-definition primitives used by the shared
reviewed-evidence coverage endpoint for IMM1294 and IMM5709.

- Each internal schema is pinned to a form code, observed source revision, filing
  context and manifest version. A deterministic SHA-256 covers its section and
  field definitions and is included in evidence-coverage snapshots.
- Sections and fields have stable keys and canonical data paths. Conditions use
  a deliberately constrained equality/inequality model, *not* executable
  expressions, user-provided Python or a legal-rule engine.
- Applicability has **three** states: active, inactive and unresolved. Unknown
  evidence never silently selects a branch. Inactive and unresolved fields
  cannot expose their values in the coverage report.
- Repeatable internal sections require an explicit item count (0-20). Missing
  counts are unresolved, not assumed zero. Indexed canonical paths are internal
  identifiers, not official IRCC PDF/XFA field names.
- Invalid, duplicate and inconsistent definitions are rejected. Tests cover
  conditions, repeats, invalid inputs and manifest revision fingerprints.

The two registered forms still use **only six observed internal preview
fields**, without any claimed official conditional mapping. The manifest engine
supports defining conditional and repeatable sections when their actual
field inventories and rule sources are independently reviewed later.
No new official PDF output, forms, signatures, or submissions are enabled.

## Remaining production gates

Professionally review all official controls per version and route, condition
semantics, item counts, declarations and signatures; pin authentic official
templates; implement full source-linked questionnaires; test real PDF/portal
output and Adobe validation; confirm commercial PDF SDK rights.

Never use the manifest digest or reviewed-subset status as an IRCC acceptance
or entire-form completeness claim.
