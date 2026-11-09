# Independent XFA / AcroForm readback gate — technical proof, not IRCC validation

The experimental native .NET Aspose trial in PR #30 builds successfully but is
**blocked during acquisition of the pinned official IMM 5476 blank PDF**.
The Windows CI download repeatedly times out. No successful official-PDF
write/readback has yet occurred, and the result must **not** be counted as a
vendor-engine failure or as official-form validation.

This separate, deterministic verifier checks a new PDF created only with
fictional values. It is independent of the vendor writer.

## Run after a fictional Aspose trial

With an already legally obtained authentic official blank and an independent
XFA-writing experiment output (both local files), run:

```powershell
python scripts/verify_xfa_trial_readback.py --original C:\temp\imm5476-blank.pdf --output C:\temp\IMM5476-ASPOSE-NATIVE-FICTIONAL-UNVALIDATED.pdf --report C:\temp\xfa-readback-report.json --expected-input-sha256 aca5c476b93d1c496b1afbc2cfe843499e852e31dcf0c192153bd01f8d6c56c4 --official-imm5476
```

The verifier requires **all** of the following:
- The SHA-256-pinned official original (when `--official-imm5476` is set).
- Exact preservation of the original signed byte prefix, and an appended
  incremental update rather than a rewritten form.
- A strictly re-openable PDF and unchanged page count.
- The four fixed *fictional* field values present in AcroForm.
- The four same values read independently from the XFA `datasets` packet,
  matching full hierarchical paths, not merely ambiguous family-name tags.

The JSON report contains only statuses, hashes, counts and technical blockers.
A successful technical result is explicitly named
`technical_subset_passed_not_adobe_validated`. The return code is nonzero
for inaccessible files, mismatched checksums, malformed or missing XFA
datasets, contradictory AcroForm values, signed-prefix loss or other
unsupported structures. Unit tests generate their own one-page **synthetic**
XFA PDFs and use incremental updates; no proprietary or official government
PDF is stored in this repository.

**Not acceptance:** The four-field synthetic test proves this checker can
detect common output corruption. It does not prove Aspose can fill IMM 5476,
Adobe usage rights survive a real update, Adobe Reader works as required, XFA
JavaScript/barcodes validate, or IRCC accepts the resulting document. Those
must be independently tested on the actual pinned official blank and in Adobe,
with licensing review, before any production integration.

Avoid committing government blanks, generated PDFs or client documents to the
public repository. Keep the native Aspose experiment out of live case-data
paths. Never substitute an unverified mirror or different PDF revision merely
to make CI green.
