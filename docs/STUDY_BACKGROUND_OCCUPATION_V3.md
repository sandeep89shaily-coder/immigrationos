# Study-permit background declarations and ten-year occupation review v3

Official instruction sources checked November 8, 2026:
- https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm1294.html
- https://www.canada.ca/en/immigration-refugees-citizenship/services/application/application-forms-guides/imm5709.html

Both forms' **Background information** sections specify declarations about:
- Unauthorized overstay, unauthorized study/work in Canada (Q2)
- Previous applications to enter or remain in Canada (Q2)
- Criminal offences, arrests, charges and convictions (Q3)
- Military, militia, police, civil defence or security service (Q4)
- Association with violent or criminal organizations (Q5)
- Witnessing/participating in mistreatment, looting or religious desecration (Q6)

The preliminary versioned intake now has **37 questions** (27 previous, 10 added).
Four new yes/no/unsure declarations have obligatory written explanations if
the applicant answers yes. Their hidden details are rejected on the server if
the corresponding declaration is no or unsure. The remaining two declarations
are captured as yes/no/unsure for a consultant to investigate; there is no
automated immigration eligibility assessment.

Official instructions also request ten years of **occupation history**, or ten
years before retirement, for both study-permit routes. The staff-only intake
worklist now checks the non-retirement default ten-calendar-year window against
the already-stored employment records through the existing date timeline audit.
It reports missing intervals, overlaps, invalid dates and unbounded end dates,
and sends an actionable follow-up to the Applicant tab. Missing employment end
dates are **not** automatically presumed to mean current employment. This
check explicitly does *not* determine whether an applicant is retired, whether
the alternative pre-retirement window applies, or whether their history has
been independently verified.

Security and correctness boundaries:
- Incoming answers are stored in the already-existing case-scoped, immutable
  submission and consultant-decision tables. Their contents are not copied
  into audit metadata or preparation-pulse summaries.
- A consultant accepting any declaration creates only a pending CaseFact.
  Professional evidence review remains separate.
- The source-labelled disclosures can concern sensitive personal matters;
  development must continue exclusively with synthetic data until privacy,
  retention and professional practice controls are independently approved.
- This release does not prove form completeness, eligibility, PDF/XFA mapping,
  official validation or submission readiness. The remaining IRCC background
  questions and special circumstances still require careful mapping.
