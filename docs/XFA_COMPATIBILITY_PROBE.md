# XFA compatibility probe — first real-form engineering prerequisite

This release improves the **existing blank-PDF inspection workflow**, not the form support count.

The probe inventories `/XFA` packet arrays or single-stream XDP, recognizes template and dataset XML structures and conservatively reports repeating/flowed subforms and explicit dynamic rendering requirements. It never strips XFA, never fills applicant data and never creates a replacement barcode.

Only safe structural metadata is returned: named packet list, XML root tags, bounded dynamic indicators, and compatibility uncertainty. No field values or full XFA XML are exposed through the API. Malformed XML, entity declarations, excessive sizes, depth and node counts fail the probe; XFA is not approved simply because a fallback AcroForm exists.

The current monitoring job remains the source-of-truth observation path for **the current blank IMM 5476 government PDF**, from IRCC HTTPS, without saving its bytes or auto-approving a revision.

## Next proof — actual XFA interoperability

1. Obtain the authentic, current PDF and an independently recorded template checksum.
2. Use the observed packet inventory and a reviewed form-specific dataset path map, not guessed AcroForm names.
3. Test dataset insertion in a licensed iText/Aspose/Foxit sandbox.
4. Re-extract the result, open/save with Adobe Reader and validate applicable official behavior.
5. Count official autofill only after the actual form and its entire workflow pass.

**Official supported forms remain zero.** Static-XFA with fallback AcroForm is **not** permission to remove XFA or bypass validation.

## Lab-only dataset writer result

`app/xfa_lab_adapter.py` now provides a fully offline **synthetic-only**
XFA data-packet writer for a named XFA `datasets` stream. A caller must
provide the exact SHA-256 of the source fixture, a complete allowlist of
pre-existing XML element paths, and an explicit synthetic-only authorization.
The writer refuses missing, duplicate or repeated paths, signed/rights-managed
templates and unapproved fields. It does not insert/remove PDF form widgets,
strip XFA, run JavaScript, generate barcodes or support real-client output.

`tests/test_xfa_lab_adapter.py` validates PDF write/readback of synthetic
data and checks that the separate XFA template packet remains byte-identical.
A test pass shows XML mutation is technically viable, not that Adobe Reader
preserves or correctly renders any real IRCC government form.

An additional GitHub Actions read-only probe attempts the **current public
IMM5476 blank** and publishes only structure metadata. A failure to fetch
remains an explicit research blocker; its job status is not an approval signal.

**The next acceptance gate is importing the actual current official blank
PDF bytes in a permitted execution environment and running Adobe validation
on Windows. This lab adapter must not be enabled in production.**
