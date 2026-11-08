# Applicant timeline audit (internal, read-only)

This increment adds an explicit-period review tool for a study-permit or other
authorized case's reusable address, employment and education histories. No
history records, applicant profiles or verified evidence are changed.

An authorized consultant selects **inclusive** start and end dates in the
Applicant tab. The tool checks separately within each history category for:

- Uncovered dates in the chosen review window, using only entries with both
  valid explicit start and end dates.
- Overlaps between two explicit periods, including same-day boundaries.
- Missing end dates, invalid legacy dates and reversed start/end dates.

**Unknown end dates are not interpreted as "present"**. If an interval has an
unresolved end within the chosen window, the audit suppresses missing-period
claims for that category, because gap inference would be unreliable. It still
shows other mechanical flags for human clarification.

The response is case-scoped and read-only, with `Cache-Control: no-store`.
It contains record IDs, period dates, and status categories, not employer names,
addresses, travel destinations or other answer values. A deterministic SHA-256
changes when relevant history records/versions change. The workspace refreshes
previously selected-period findings after record edits.

The caller supplies the window; the system does **not** infer an IRCC lookback
requirement. Employment overlaps may be legitimate; education histories need
not continuously cover an entire period. Chronology cannot establish accuracy,
documentary verification, immigration eligibility, or official form completeness.
The response always reports those release gates as false. No government PDFs,
form filing, or external AI processing are added.
