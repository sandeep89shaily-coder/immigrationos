# Verified internal form preparation — first end-to-end evidence gate

**Status:** Development-only; synthetic cases. The software does **not** generate, barcode-validate, sign, or submit IRCC forms.

## What was implemented

The consultant study-permit package now has a **verified field preparation** panel. It selects IMM1294 for a case filed outside Canada or IMM5709 for inside Canada, then evaluates the canonical internal preview paths published in `app/ircc_registry.py`. It never invents an official PDF field identifier.

For each field, the API requires reviewed, source-linked case facts. A source document must have an explicit recorded cleared scan result. Conflicts, pending fact reviews, missing facts, missing scan clearance, unresolved case issues, closed cases and stale IRCC observations block capture. A packet is an immutable, source-hashed snapshot of the internal preview subset with evidence IDs, document IDs and source hashes. The user must explicitly acknowledge that it is not an official form. Captures use an expected snapshot digest so changed source facts do not silently create stale packets.

The endpoints are:

- `GET /api/v1/orgs/{org_id}/cases/{case_id}/form-preparation/preview`
- `GET /api/v1/orgs/{org_id}/cases/{case_id}/form-preparation/packets`
- `POST /api/v1/orgs/{org_id}/cases/{case_id}/form-preparation/packets`

The database table `form_preparation_packets` has composite case/package constraints, PostgreSQL FORCE RLS and insert-only application-role permissions. Audit logs store the packet ID, form code, mapping revision and digest — no client answers.

## Important limitations

This is explicitly not a completed official government form. The registry covers **a small internal subset** of IMM1294/IMM5709, not a complete current official field inventory. Official PDFs may contain XFA, JavaScript, mandatory Adobe validation and barcodes. The existing static AcroForm adapter must remain disabled for unsupported dynamic government forms.

The packet does not imply sufficiency of evidence or legal eligibility and must not be called an official auto-filled IRCC form. Both `official_pdf_autofill_supported` and `submission_supported` stay false. Staff-uploaded documents lacking explicit scan clearance are blocked, rather than presumed safe.

## Next essential engineering gate

Obtain an official IRCC blank form through the approved research workflow, preserve its checksum, inspect its actual fields and technology, confirm jurisdiction/version and signatures, develop a complete human-approved field map, then independently validate any supported generated output in Adobe/official workflow. Do not promote a government form to supported until tested end-to-end with RCIC review and current instructions.
