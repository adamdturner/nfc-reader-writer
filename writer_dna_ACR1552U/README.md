# writer_dna_ACR1552U

Research and implementation plan for a secure NTAG424 DNA provisioning station using the ACS ACR1552U USB NFC reader.

Scripts in this folder will use AES authentication and NTAG424 DNA secure messaging to write tags that cannot be overwritten by generic NFC apps or phones. This is distinct from the scripts in `writer_ACR122U/`, which write tags in the open/unprotected mode.

## Status

Planning phase. Hardware (ACR1552U) not yet acquired. No implementation scripts exist yet.

## Folder Contents

### `NTAG424_DNA_SECURE_WRITER_RESEARCH.md`
Research on NTAG424 DNA security model, hardware options, and why a new reader is needed. Explains the difference between open NDEF writing (what the ACR122U scripts do) and AES-backed write protection (what this folder will implement).

### `NFC_TAG_PROVISIONING_AUTOMATION_PLAN.md`
Detailed implementation plan for a high-throughput provisioning station. Covers the provisioning state machine, backend API shape, Firestore status model, key management, and failure handling.

## What This Folder Will Contain

Once the ACR1552U is acquired and the implementation is built:

- A provisioning daemon/CLI that polls for tags automatically.
- NTAG424 DNA authentication and secure messaging implementation.
- Access-right configuration that locks write/clear to AES-authenticated operations.
- Backend API integration for Firestore tag document lifecycle.
- Key management utilities.

## Security Goal

After provisioning with scripts from this folder:

- Any phone or NFC app can read the public NDEF URL.
- Only the provisioning system (with the correct AES key) can overwrite or clear the tag.
- Generic writer apps will fail to overwrite the tag.

See `NTAG424_DNA_SECURE_WRITER_RESEARCH.md` for the full security model.
