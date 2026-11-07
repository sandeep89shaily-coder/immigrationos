# IMM 5476 autofill: alternative engines and no-PDF-edit experiment (2026-11-07)

**Status: research and experiment preparation; not production support.** The official validated forms count remains zero. This memorandum uses publicly documented capabilities; it is not an assertion that any listed vendor can preserve the Adobe usage-rights signature on this specific PDF.

## Existing empirical baseline

- Exact official 11-2025 IMM 5476 blank: SHA-256 `aca5c476b93d1c496b1afbc2cfe843499e852e31dcf0c192153bd01f8d6c56c4`, four pages, hybrid XFA + AcroForm, Reader usage-rights /UR3.
- Our low-level incremental mutations set data but Acrobat displayed raw rich-text XML in two surname boxes. Stop treating that method as a potential production generator.
- **Aspose.PDF for Python via .NET 26.9.0** successfully imported *four* fictional names via `facades.Form.set_xfa_data()` in a Windows runner. 66 XFA names enumerated. Independent XFA and AcroForm readback 4/4 passed and independent rendering displayed both surnames. Actual Adobe Acrobat compatibility **not yet tested**. Its full rewrite changed the original byte prefix and bytes covered by the original Reader usage-rights signature. Rewriting through Aspose is not approved for clients. Proof: merged PR #29, GitHub run `42364296240`.
- Incremental native .NET trial is intentionally isolated in PR #30; its latest GitHub workflow stopped on official-source timeout, not successful signature preservation.

## New alternative #1: Adobe-native XFA import (first compatibility experiment)

Adobe Acrobat JavaScript defines `Doc.importXFAData()`, importing an external XFA data file in batch or privileged JavaScript console events. Acrobat itself processes XFA binding and renders the original official form. `Doc.exportXFAData()` exports XDP or XML data from an existing form; its default XDP packets include datasets and XFDF.

Method:
1. Copy the genuine blank, **never** a previously rewritten output.
2. Prepare an external fictional-data XDP from the matching template's original XFA data tree, no PDF edits.
3. In desktop Acrobat Pro with a permitted JavaScript console context, open the untouched copy and call `this.importXFAData();` (prompts for XDP).
4. Inspect four fields including family names; use Save As to a **new filename**; close and reopen; check field functionality, signatures and permissions.
5. If Acrobat does not expose this feature or does not accept the data, mark the route unsupported. No security bypass, privileged folder installation, signing or client data.

Experiment package: two XDP variants generated against the pinned original; one with scalar surnames and another preserving source XHTML rich-text subtree. Compare each on a **separate fresh copy**. The XML is structurally valid and changes no PDF object. Neither variant has been imported by Acrobat yet.

Official JavaScript API:
https://opensource.adobe.com/dc-acrobat-sdk-docs/library/jsapiref/doc.html#importxfadata

Adobe export:
https://opensource.adobe.com/dc-acrobat-sdk-docs/library/jsapiref/doc.html#exportxfadata

Caveat: Acrobat Reader does not support general Windows OLE automation, and the JavaScript method is restricted to console/batch contexts. Adobe Pro/Reader licensing and permissions must be tested on actual software; do not promise unattended batch automation.
https://opensource.adobe.com/dc-acrobat-sdk-docs/library/interapp/IAC_DevApp_OLE_Support.html

## New alternative #2: Qoppa jPDFFields / jPDFProcess

Qoppa explicitly supports import/export of XDP data into dynamic LiveCycle XFA PDFs and saving interactive forms. Its Java SDK is a practical server-side replacement candidate, distinct from Aspose. Qoppa explicitly says dynamic XFA *rendering* is not supported in its viewing/image components, so Acrobat remains necessary for final visual verification.

Java documented proof:
`new PDFFields(blankPdf, null); pdfDoc.importXDP(dataPath); pdfDoc.saveDocument(outputPath);`.

Sources:
https://kbdeveloper.qoppa.com/fill-populate-xfa-dynamic-form-with-field-data-in-java/
https://kbdeveloper.qoppa.com/livecycle-dynamic-xfa-forms/
https://www.qoppa.com/pdffields/

**Commercial blocker:** Qoppa's EULA imposes restrictions on certain third-party SaaS primarily providing document functions; require explicit written vendor clearance for ImmigrationOS's exact distribution model, regardless of whether forms are part of a broader RCIC case-management platform.
https://www.qoppa.com/pdfautomation/eula/

## Alternative #3: Foxit PDF SDK with XFA module

Foxit supports XFA loading, import/export data **and rendering**, across server/desktop languages. Foxit explicitly requires its separately licensed XFA module. Its sample imports XML through `XFADoc.ImportData`. Test permission/license availability and save mode on the authentic blank. Do not claim /UR3 signature validity merely because /Perms survives.

Source: https://developers.foxit.com/documents/development-guide/pdf-sdk-desktop-server/features/forms/xfa-form.html

## Alternative #4: TallComponents PDFKit.NET 5

The SDK documents `XdpFormData` import into dynamic XFA forms, and its June 2026 changelog notes dynamic XFA improvements. This may be a simpler .NET evaluation candidate if Foxit licensing or integration proves difficult. Check actual support, interactive saving, usage rights and terms before integration.
https://tallcomponents.com/products/pdfkit5/code-samples/dynamic-xfa-merge-xdp/
https://tallcomponents.com/products/pdfkit5/changelog

## Specialized routes / not a universal replacement

- Adobe AEM Forms `FormsService.importData` supports importing data into interactive PDFs and may serve as a licensed enterprise route; significantly heavier integration, and confirm rights to use government form design.
  https://experienceleague.adobe.com/en/docs/experience-manager-65-lts/content/forms/use-document-services/aem-document-services-programmatically
- Adobe PDF Services cloud form import officially supports AcroForm and **static XFA**, not dynamic XFA. We must classify each IRCC template first; do not treat this as universal.
  https://developer.adobe.com/document-services/docs/overview/pdf-services-api/howtos/import-pdf-form-data/
- The IRCC representative Permanent Residence Portal includes **native digital forms** for some categories, alongside PDFs. ImmigrationOS must distinguish web-form workflow from XFA PDF workflow rather than promise 400 PDFs. Do not automate logins/submissions without an authorized integration and professional review.
  https://www.canada.ca/en/immigration-refugees-citizenship/corporate/partners-service-providers/authorized-paid-representatives-portal/sign-in-permanent-residence-portal-representatives.html
- Power Automate Desktop could fill Adobe via visible user-approved UI automation as an audited fallback. It is not scalable form-field technology, and timing/layout changes can make it fragile.
  https://learn.microsoft.com/en-us/power-automate/desktop-flows/desktop-automation

## Acceptance gates for each template + engine

1. Exact current government source and hash locked.
2. Fixed canonical data mapping covers mandatory, optional, conditional, repeating fields and controls.
3. PDF opens in current desktop Adobe Acrobat without XML code or warnings.
4. Exact on-screen rendering; save/reopen/reset/print work; buttons and any barcodes/validation continue to function.
5. Reader usage-rights/signature/permissions explicitly tested, including cryptographic byte-range verification when applicable.
6. No flattening or overlay for forms whose interactivity, validation or embedded barcode is required.
7. No watermark, trial banners, unsigned representative declarations mistakenly presented as signed.
8. Vendor provides a written licence covering commercial multi-tenant RCIC SaaS and appropriate data locality/processing.
9. Independent IRCC/RCIC legal-workflow validation and human review before submission.

## Recommended implementation order

**First:** controlled Adobe-native import on a fresh original PDF, four names. No PDF edits.

**Second:** Qoppa jPDFFields + XDP proof and Foxit XFA-module trial against exact IMM5476 using the same comparison harness. Add TallComponents if a commercial .NET option is needed.

**Third:** choose one engine per form class from empirical evidence. For all cases, store one canonical client profile + a versioned map, and include explicit human review and a 'manual assisted' fallback. Keep proprietary SDKs as isolated backends rather than coupling the core CRM to a vendor.

**Do not** start a large form catalog or claim official IRCC validation from SDK feature descriptions alone.
