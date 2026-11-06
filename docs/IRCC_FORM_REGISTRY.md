# Official IRCC form-source registry — implementation decision

**Status: internal preparation preview only. Not official forms, not a government portal integration, not an eligibility assessment.**

## Verified starting sources (checked 2026-11-05)

| Code | Context | Official instructions | Observed PDF update |
|---|---|---|---|
| IMM 1294 | Study permit made **outside** Canada | https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm1294.html | June 2026 |
| IMM 5709 | Apply/change/extend study permit **inside** Canada | https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm5709.html | June 2026 |

IRCC instructs users to download PDF forms and open them using Adobe Acrobat Reader. Browser preview/PDF generators cannot be assumed to preserve validation and barcode behavior. IRCC form and application lists are subject to revision; the source observation above does not certify a form revision for future filing. Country-specific document checklists, conditional requirements and submission channels remain separate issues.

## Implementation policy

1. Maintain exact source-page URL, observed last-update label, observation date, and filing context.
2. A catalogue record cannot be considered current after 30 days without source re-check; the frontend must display age and source warnings. Even a recent review **never** permits automatic filing.
3. Preparation previews read only **human-verified** case facts, display source fact/document IDs, and flag conflicting verified values as ambiguous.
4. Form route must match both case category and declared filing context. No inferred filing context from nationality or postal address.
5. Never equate a subset of mapped identity fields with a complete application or PDF-ready status. A validated form-generation adapter requires independent engineering, version regression tests and an RCIC reviewer sign-off.
6. Do not embed government forms as static downloadable assets in the repository or assume that IRCC permits automated website submissions.

## Next implementation gate

For **one** selected supported official IRCC PDF: capture the document checksum, revision, detailed field mapping and official instructions; manually validate it in Adobe Acrobat Reader (including barcode behavior if applicable). Add regression fixtures for the exact revision and test the full consultant approval/handoff workflow. This remains blocked until reviewed by an authorized immigration professional.
