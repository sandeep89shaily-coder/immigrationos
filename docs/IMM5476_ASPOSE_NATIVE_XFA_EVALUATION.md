# IMM 5476 native XFA engine trial — evidence and release criteria

**Experiment date:** 2026-11-07. **Official government blank:** IMM 5476 E (11-2025), obtained by a GitHub-hosted runner from the exact IRCC URL and checked against the previously uploaded authentic PDF.

**Pinned blank SHA-256:** `aca5c476b93d1c496b1afbc2cfe843499e852e31dcf0c192153bd01f8d6c56c4`

## Completed real-form compatibility measurement

**Aspose.PDF for Python via .NET 26.9.0**, on Windows GitHub Actions, was able to:
- Load and enumerate **66** real XFA fields.
- Import synthetic XML datasets using its officially documented `facades.Form.set_xfa_data()` method.
- Save a four-page PDF with four fictional name values.
- Pass independent `pypdf` readback for **4/4 XFA dataset values and 4/4 AcroForm values**.
- Keep 84 AcroForm entries and ten XFA named packets, with the XFA `template` and `config` streams byte-identical to the authentic blank.
- Render the two problematic surnames as ordinary text in an independent Poppler rendering; no raw XML visible.

Evidence: GitHub Actions run `42364296240`, job `128379015015`, artifact `13570519681`. Output SHA-256 `e42b6ee685519fc69a9594984db076ef04ee1f98a24b5a092f050238b6f5d105`.

This output has the Aspose trial watermark, is incomplete and unsigned, and **has not been tested in Adobe Reader or accepted by IRCC**.

## Crucial incremental-save / Adobe-usage-rights risk

The Python `facades.Form.save(output_path)` path performed a **full PDF rewrite**. The output did not retain the original PDF bytes as a prefix. The original `/Perms /UR3` signature's signed ByteRange remained `[0, 2002846, 2015078, 1109]`, but the bytes covered by that range were changed in the Aspose output. The visible `/UR3` dictionary is NOT proof that its usage-rights signature remains valid. **Do not production-enable this output.**

Aspose documents a native .NET `Document.Save()` incremental mode when the document is opened with a writable stream. A separate C# trial in `experiments/AsposeXfaTrial` copies the exact official original first, applies the true XFA indexer mapping on that copy, uses parameterless `Save()`, and rejects output that fails original-byte-prefix preservation.

Even a byte-preserving incremental update requires an actual Adobe Reader test to determine whether the form still allows all expected operations.

## Runtime findings

- Linux hosted trial with Aspose 26.9 aborted due to missing compatible ICU and OpenSSL runtime components. We rejected deploying legacy OpenSSL into the main service.
- Windows runner loaded the SDK and PDF successfully.
- The Python XFA indexer is NOT writable (`TypeError`). Use the documented Python `facades.Form.set_xfa_data()` method, or native C# `Document.Form.XFA[field] = value`; do not infer identical language bindings.
- Entire experiment uses **only fictional values**. This is not connected to client data or the SaaS API.

## Release blockers

1. Confirm generated PDF behaviour with real Adobe Acrobat Reader on Windows, including save/reopen, field interactions, Reset and Print.
2. Inspect the `/UR3` signature and entitlement behaviour after generation; the PDF dictionary marker alone is insufficient.
3. Obtain proper commercial licensing; trial output has a watermark and must never be submitted.
4. Complete a reviewed, source-pinned field map and conditional logic for all five IMM5476 operations, not just four names.
5. Human RCIC legal review of sections, declarations, signatures and actual submission route.
6. Separate customer-facing generator with tenant security, document scan controls and versioned immutable output and review. This is explicitly not yet implemented.

**Official validated form count remains 0.** Successful first-stage XFA autofill is a test result, not full official-form support.
