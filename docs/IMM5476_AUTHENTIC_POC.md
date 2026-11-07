# IMM 5476 — Authentic form autofill proof of concept

**Source file:** User-provided blank government IMM5476 (11-2025), four pages.
**Pinned SHA-256:** `aca5c476b93d1c496b1afbc2cfe843499e852e31dcf0c192153bd01f8d6c56c4`.

## Technical observations (actual PDF, not an inference)

The real document is a hybrid AcroForm + XFA PDF with 84 `pypdf.get_fields()`
entries, including grouping nodes, and 10 XFA packet elements:
`preamble, config, template, localeSet, datasets, xmpmeta, xfdf, PDFSecurity,
form, postamble`. The PDF uses AES-128 encryption with an empty opening
password, allows form filling, and carries a `/Perms /UR3` Reader usage-rights
entry. Do not strip `/XFA`, flatten or replace the original file.

An initial `pypdf.PdfWriter(..., incremental=True)` experiment saved
inconsistent encrypted XFA stream bytes, so that approach was rejected for
the real government form. The succeeding synthetic-data experiment used
**PyMuPDF incremental save** with updates to both the named XFA `datasets`
stream and the corresponding AcroForm text widgets, followed by an independent
`pypdf` re-open and field/XFA XML readback. The output retained all original
bytes as its prefix and preserved the original XFA template stream and
`/UR3` dictionary marker.

This is **not proof that Adobe's usage-rights signature is still valid**.
Only the official Adobe Reader workflow can assess that, and it remains
unverified here.

## Reproducible developer-only demonstration

Install development dependencies:

```
pip install -e ".[test]"
python -m scripts.try_imm5476_poc \
  --input "/path/to/imm5476e.pdf" \
  --output "/path/to/IMM5476-fictional-UNVALIDATED.pdf"
```

The script accepts **no applicant inputs**. It populates exactly twelve
hard-coded **fictional** text fields with `example.test` addresses. Each XFA
binding and complete corresponding AcroForm field name was observed in the
original PDF. This partial prototype deliberately leaves representative
category, ID/standing, operation choice, declarations and signatures empty.

The output is neither a completed form nor submission-ready. The script
rejects a changed source PDF checksum, form layout, unexpected existing data,
same source/output path, or existing output. It never overwrites the source.
The current form revision must be reverified with IRCC before any real use.

## What is still missing

1. Independently review current official form version and all Sections A–E.
2. Confirm the output opens correctly in **Adobe Acrobat Reader on Windows**,
   maintains all Reader usage rights, supports Save/Reset/Print and is still
   interactive. A standalone PDF renderer cannot certify this.
3. Complete the five operation choices and representative paid/unpaid
   classifications; support their unique field states and mandatory/conditional
   sections with RCIC review. Avoid generating or impersonating signatures.
4. Implement real case/evidence-backed data paths, secure storage and tenant
   controls. This **experiment is intentionally not wired to the SaaS API**.
5. Ship a production-supported adapter only after professional/technical QA
   of a complete current form, with regression cases and rollout controls.

**Official validated form count remains zero.** This proof addresses the
technical form-writing obstacle with the first authentic IRCC PDF. It
does not establish that an officially accepted application has been created.
