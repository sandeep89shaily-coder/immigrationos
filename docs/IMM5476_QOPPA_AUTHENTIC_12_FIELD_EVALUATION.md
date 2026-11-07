# IMM 5476 / Qoppa jPDFFields authentic-form experiment

**Date:** 2026-11-07. **State:** experimental, *not production-ready*.

## Source and engine

- Official blank: IMM 5476 E (11-2025), the exact user-supplied 4-page 2,016,187-byte government PDF.
- Pinned SHA-256: `aca5c476b93d1c496b1afbc2cfe843499e852e31dcf0c192153bd01f8d6c56c4`.
- SDK: Qoppa jPDFFields v2022R1.20, vendor-published Java evaluation JAR, downloaded for private research only. No vendor binary added to the repository, packaged with user downloads, or deployed.
- Engine call: `PDFFields(input, null); importXDP(dataPath); saveDocument(newOutputPath)`.
- Data: twelve fixed fictional applicant and representative fields (no real applicant data).

## Empirical outcomes

| Measurement | Scalar surname XDP | Rich-XHTML surname XDP |
| --- | --- | --- |
| Four-page PDF generated from original | PASS | PASS |
| Original PDF bytes retained as exact prefix | PASS | PASS |
| Original `/UR3` signed ByteRange bytes unchanged | PASS | PASS |
| Applicant and representative surname visible with Poppler | PASS | FAIL |
| Applicant and representative name text in XFA payload | PASS | Present, but problematic rich-text serialization |
| Evaluated in actual Adobe Acrobat | NOT TESTED | NOT TESTED |

After expanding to **12 synthetic text fields**, Qoppa's scalar variant produced a 2,153,760-byte PDF with SHA-256:

`5391059a30f32a4d108744a909a009df60bf3c31570cb39cd4b8954a70c9bcdc`

Independent **PyMuPDF widget reads verified 12/12 values**, including applicant names, DOB, email, application type, representative names, firm, city, province, country and email. Independent Poppler images of pages 1–2 displayed all supplied test data as ordinary text. PDF page count stayed 4; all 10 named XFA packets remained accessible. The original full byte prefix and the original bytes in the usage-rights `/UR3 /ByteRange [0, 2002846, 2015078, 1109]` were unchanged. Preserving signed bytes is necessary but does **not** certify that Adobe accepts the usage-rights signature or save operation.

**Important structural warning:** `pypdf.get_fields()` raises `KeyError('/N')` for Qoppa's output. We isolated it to a `/Btn` field at
`IMM_5476[0].Page1[0].disclaimer[0].websitelink[0]` whose `/AP` becomes an empty dictionary; the same original field did not have that problem. PyMuPDF still enumerates 12/12 filled text widgets. Acrobat may handle this differently; it is a release blocker pending real Adobe testing.

**Radio button test:** the top appointment-choice group and the paid-CICC group were assigned the source-template's own observed XFA item value `1`, not a guessed PDF on-state. Qoppa preserved the values in XFA datasets, but the associated AcroForm radio widgets stayed `Off`, and independent rendering showed no circles selected. **Radio and conditional controls have NOT passed.** The test must not be used as proof of a completed appointment workflow.

The evaluation PDF is watermarked `Qoppa Software - For Evaluation Only` and contains a large diagonal `Qoppa Software` watermark. Neither trial PDF is appropriate for client use, signatures, filing or IRCC submission.

## Decision and next gates

1. **Adobe compatibility:** open the scalar 12-field output in Windows Acrobat; check that names render without raw XML, form remains interactive, and save/reopen works. Compare original and output's security/usage-rights warnings.
2. **Radio control mapping:** independently test XFA choices and Acrobat recalculation; do not merely write `0` or `1` into XFA and assume the UI selected it. Verify proper top-level operation, representative type and conditional fields.
3. **Form completeness:** map all form operations, repeated sections, signatures and required fields with professional review.
4. **SDK license:** request written confirmation from Qoppa for a commercial multi-tenant RCIC SaaS and a non-watermarked license. Ensure SDK and end-user PDF licensing respects vendor terms.
5. **Negative regression:** confirm Adobe save/reopen, Reset and Print buttons and any form-specific behaviors; `/UR3` marker/byte preservation alone is insufficient.
6. **Deployment:** keep the engine behind a version-pinned adapter. Do not connect to real applicant data or expose an official supported-form flag until all gates pass.

## Reproducibility

The experimental CI workflow `.github/workflows/imm5476-xdp-engine-trial.yml` downloads the public blank when available, enforces its SHA-256, generates both scalar and rich XDP files using `scripts/imm5476_xdp_vendor_trial.py`, and tests native vendor implementations. CI's official-source download is temporarily blocked by Canada.ca read timeouts; it must not be interpreted as a vendor failure. A private local test against the exact uploaded source was therefore performed, not a different government form.

Compare to prior Aspose output: Aspose successfully filled four test values and rendered names, but performed a full PDF rewrite changing the signed original bytes. Qoppa's incremental output preserved the original signed bytes while leaving UI/control and structural issues to resolve.

**Official validated forms: 0. Production enabled: NO.**
