# Study permit form preparation: enforce current internal manifest

This migration-free change closes an important preparation integrity gap. The
legacy immutable form-preparation packet was guarded only by six internal
preview fields, while IMM1294 and IMM5709 now have 24-field *incomplete*
internal manifests. The legacy six-field result alone must not permit a new
packet to be captured.

The packet preview now calls the same evidence-coverage evaluator used by the
consultant Preflight and unified trace. To capture a packet, all **applicable
fields in the current 24-field internal manifest** must be independently
verified against case-owned documents with explicitly cleared malware scans;
conditional questions must be resolved, conflicts reconciled, and the source
must not be stale. A parent declaration supported by reviewed evidence can
make dependent fields inactive, but a missing or unsure answer leaves the
branch unresolved.

The immutable snapshot now binds its hash to the current manifest version,
manifest digest, evidence coverage digest, and number of verified internal
fields. A subsequent fact, scan, source revision or condition change requires
recapturing. Earlier packet rows remain readable as legacy six-field
snapshots, not recertified by the new evaluator.

**Boundary:** Even the new capture is a reviewed *partial internal packet*,
not an official IRCC PDF, form validation, completion certificate, signature,
legal assessment, or government submission. Official controls and actual PDF
save/reopen validation remain separate from this milestone. Synthetic records
only.
