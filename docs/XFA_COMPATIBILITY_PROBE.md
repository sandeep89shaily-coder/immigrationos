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
