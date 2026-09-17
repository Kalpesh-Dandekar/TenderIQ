# TenderIQ backend domain foundation

PostgreSQL is the source of truth for procurement metadata, relationships, Blueprints, claims, evidence mappings, verification state, and evaluation persistence.

Physical documents are not stored in PostgreSQL. B2 stores real PDFs through a `StorageProvider`; the current `LocalStorageProvider` writes to the private, gitignored `backend/storage` directory. PostgreSQL stores object keys, metadata, versions, and SHA-256 integrity hashes only.

The Vendor Evidence Vault separates each logical `VendorDocument` from immutable `DocumentVersion` records. Proposals attach exact versions, and `ProposalSubmissionDocument` snapshots preserve the versions submitted even when a vendor later uploads a replacement.

Tender and Vendor Blueprints are versioned structured representations. Central tender requirements are reused across every vendor proposal, allowing evidence mappings and evaluation runs to scale without duplicating requirements or certificate files.

Configure storage with `STORAGE_PROVIDER=local`, `LOCAL_STORAGE_PATH=./storage`, and `MAX_DOCUMENT_SIZE_MB=25`. A future R2/S3-compatible provider will implement the same interface without changing document services. The prototype download endpoint is deliberately controlled through the API and never exposes local paths or static storage; full authorization awaits the authentication/RBAC phase.
