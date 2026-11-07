# IMM5476 11-2025 — Paid-CICC appointment, 23-control proof

**Experimental research only. Official validated form count: zero.**

## Source and scope

The source was the exact original four-page IMM5476 E (11-2025) user-uploaded government PDF, SHA-256 aca5c476b93d1c496b1afbc2cfe843499e852e31dcf0c192153bd01f8d6c56c4. It contains hybrid XFA and AcroForm fields and original Adobe Reader usage rights. No real applicant information was used.

The generator in app/imm5476_paid_cicc_poc.py accepts **only** that pinned blank. Its fixed fictional XDP populates 21 observed text inputs in Sections A and B: applicant names, DOB, email, application type, application number and UCI; representative names, CICC number, organization, unit/street address, city, province, country, postal code, phone and email. It specifies the top-level **appoint** operation and **paid-CICC** radio choice, leaving unpaid-representative choices off.

Applicant, representative, and supervising lawyer signatures, declaration dates, other operations, cancellation/withdrawal details, and optional fax are untouched. The output is **XDP data only**, not a rewritten original PDF.

## Validated real-form trial

Using the vendor-published Qoppa jPDFFields v2022R1.20 evaluation SDK in Java 21 with the original uploaded PDF and the controlled fictional data produced a four-page output with SHA-256:

30be713ed9e4a44615734d67bbd6f87ad1acdf99ef1ebb62099edf2a42e5ef34

An independent PyMuPDF/PDF/XFA review found:

- 21/21 matched text values in the XFA data and AcroForm widgets.
- Both intended radio groups selected (first operation and paid CICC), all five unpaid widgets off; XFA and widget radio states agreed.
- The concatenated XFA packet XML and standalone XFA dataset packet parse as XML.
- Original PDF bytes were preserved as a byte-identical prefix, including the full original Adobe usage-rights ByteRange.
- All inspected declaration signature widgets and signature dates remain blank.
- Poppler rendered the text and both radio groups in the intended boxes.

**This is not an Acrobat compatibility pass.** The PDF is watermarked, incomplete and unsigned.

## Discovered release blockers

1. **Rich surname XHTML corrected using the vendor-supported API.** Raw XDP import originally generated nested unescaped quotes in the font-style attribute. Calling Qoppa TextField.setRichValue() on exactly the two fictional surname widgets after XDP import produced well-formed XHTML for both names; XFA data, visible widgets, two radio choices and original signed bytes still match. Acrobat compatibility is NOT yet established.
2. **Appearance dictionary issue.** pypdf.get_fields() fails with KeyError('/N') on the vendor output; another renderer can still display the form.
3. **Adobe, usage rights, signatures and save/reopen remain untested.** Preserving signed bytes does not establish that Adobe accepts every Reader entitlement.
4. **Vendor commercial licensing has not been verified.** Trial watermark output must not be supplied as a client-ready form.
5. Only a fixed appoint-paid-CICC scenario was exercised, not the five operation flows in the original form.
6. Form values are synthetic and not evidence-backed. No API is connected to real case facts and no form is approved for submission.

## Reproduce the proof

Produce XDP from the exact government blank (this refuses mismatched source hashes and existing outputs):

    python -m app.imm5476_paid_cicc_poc original.pdf fictional-appointing-paid-cicc.xdp

The existing Qoppa evaluation Java adapter can import that XDP and set the two PDF radio appearances via its supported radio API. This is a licensed/evaluation-tool operation; no proprietary SDK binary is committed.

Verify an output independently:

    python -m scripts.verify_imm5476_paid_cicc original.pdf output.pdf report.json

The verifier checks 21 text fields, both radio groups, the unpaid-off state, XFA XML structure, original signed bytes and untouched signature fields. It fails the structural trial if XHTML is malformed, and still explicitly reports any PDF field-parser failures; **it never calls the output Adobe-verified, IRCC-validated, licensed or submit-ready**.

## Next hard acceptance criteria

Have a current Windows Acrobat build open the vendor PDF, change an ordinary field, save under a new name, close and reopen. Check radio selection persists, no XML is shown, buttons behave as expected, and any usage-rights/signature warnings. The malformed surname XHTML has now been fixed through Qoppa's native API. Fix or independently clear the remaining PDF appearance dictionary issue, or choose another engine if Adobe rejects the output. Then map and test all remaining operation/conditional branches, connect only verified case facts, obtain commercial SaaS licensing, and complete an RCIC legal workflow review.

**Production flags remain false: official_pdf_autofill_supported, official_ircc_validation_verified, submission_supported.**
