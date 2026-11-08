# Study permit intake worklist (staff-only, read-only)

This connects the existing 17-question preliminary study-permit intake with reusable applicant identity, family/history summaries, and independently verified case evidence.

GET `/api/v1/orgs/{org_id}/cases/{case_id}/study-intake/worklist`

For assigned, authorized practice staff, the response records a per-question state: missing answer, reusable profile claim awaiting evidence, latest submission awaiting review, dismissed/recollection, accepted but pending independent verification, evidence review required, or independently verified source evidence. The endpoint shows no raw question answer values. It also includes counts of family members and applicant history records and pins the internal IMM1294/IMM5709 manifest checksum.

A submitted or accepted client answer never becomes verified on this worklist. Only human-reviewed, case-bound CaseFacts backed by explicitly malware-cleared documents satisfy the evidence gate. Wrong filing contexts and cases without initialized study packages are rejected. The endpoint never sends changes to IRCC or changes the authoritative client profile.

This is **not a comprehensive IRCC form questionnaire**: it joins the preliminary questions already in the product, not all conditional/repeatable form controls. Current study permit case records use a single provisional intake template. The worklist is for synthetic development cases only.
