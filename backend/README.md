# TenderIQ backend domain foundation

PostgreSQL is the source of truth for procurement metadata, relationships, Blueprints, claims, evidence mappings, verification state, and evaluation persistence.

Physical documents are not stored in PostgreSQL. Cloudflare R2 integration will be added in Phase B2; database records contain object storage keys, metadata, and SHA-256 integrity hashes only.

The Vendor Evidence Vault separates each logical `VendorDocument` from immutable `DocumentVersion` records. Proposals attach exact versions, and `ProposalSubmissionDocument` snapshots preserve the versions submitted even when a vendor later uploads a replacement.

Tender and Vendor Blueprints are versioned structured representations. Central tender requirements are reused across every vendor proposal, allowing evidence mappings and evaluation runs to scale without duplicating requirements or certificate files.
