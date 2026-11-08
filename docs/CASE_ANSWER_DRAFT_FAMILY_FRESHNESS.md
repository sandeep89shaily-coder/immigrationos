# Case answer drafts: family snapshot and source freshness

New synthetic case answer drafts include the current linked applicant's family records alongside existing address, education, employment, and travel history snapshots. These snapshots are **internal preparation materials** and are not verified evidence or completed IRCC PDFs.

A saved draft now contains the observed form-manifest SHA-256. When listing drafts for an assigned case, the server compares:
- Applicant profile version
- Set of history record IDs and their versions
- Set of family member IDs and their versions
- Form code, observed form revision, and manifest digest

The result is `source_freshness=current` or `stale`. Old drafts without the new snapshot metadata return `unknown_legacy`, never a fabricated current status. When family or history records change, the saved draft is not overwritten: it remains a historical record and a new draft can be generated. New drafts are forbidden on closed cases. Firm/case access and existing audit metadata rules remain in force.

No migration is necessary: the existing JSON snapshot column carries the additional family and manifest data. These checks detect ordinary versioned edits, **not** external IRCC revision publication, deleted record restoration with identical IDs/versions, unversioned database tampering, or legal sufficiency. No live applicant or client data may be used in this development-stage release.
