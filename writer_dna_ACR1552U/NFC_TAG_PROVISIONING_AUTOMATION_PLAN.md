# NFC Tag Provisioning Automation Plan

Status: tentative implementation plan  
Last updated: 2026-04-29

## Goal

Build a high-throughput NFC tag provisioning station for NTAG424 DNA tags. The operator should only need to place a tag on the reader, wait for the success/failure signal, remove the tag, and place the next one.

The initial security goal is tamper resistance for the original tag:

- Write a URL payload to the tag.
- Keep the payload readable by normal phones.
- Prevent unauthorized users from clearing or overwriting the tag.
- Use AES-backed NTAG424 DNA access rights for write protection.

Anti-cloning is a future enhancement. The current phase does not need to prove that a copied URL came from the original physical chip.

## Current Product Model

The existing Firebase project already owns the product and NFC document model.

Each NFC chip is represented by a Firestore document. Example document ID:

```text
0b452473-1a29-bcb4-491e-cf2e50ee3513
```

The tag payload is a public URL derived from that document ID:

```text
https://www.example.com/nfc/0b452473-1a29-bcb4-491e-cf2e50ee3513
```

The document ID is not a secret. It is part of the public scan URL. Ownership and authorization are enforced in the backend through Firebase/Firestore security rules and backend-controlled writes.

Typical NFC document fields may include:

```text
ownerId
productId
payload
status
uid
readerId
batchId
provisionedAt
provisionedBy
writeProtected
failureReason
```

## Recommended Implementation Stack

```text
Reader:        ACS ACR1552U
Transport:     PC/SC via pyscard
Crypto:        PyCryptodome
Database:      Firestore, accessed through backend provisioning APIs
Local state:   Optional SQLite queue/cache for retry and recovery
Key storage:   Development: OS keychain or encrypted local config
               Production: SAM AV3, KMS, HSM, or equivalent secure key storage
App style:     CLI/TUI daemon with automatic polling and success/failure signals
```

### Why This Stack

The ACR1552U is a good desktop reader choice because it supports PC/SC, CCID, ISO 14443 Type A/B, Type 4 Tag communication, extended APDUs, and includes a SAM slot for future key-storage hardening.

Python remains appropriate for high-throughput provisioning because the bottlenecks are expected to be:

- manual tag placement/removal;
- NFC RF communication;
- backend API round trips;
- verification steps.

AES and CMAC operations are not expected to be the performance bottleneck. PyCryptodome is suitable for implementing the cryptographic primitives needed by NTAG424 DNA secure messaging.

Firestore should remain the source of truth, but the writer should not directly hold broad Firestore write credentials if that can be avoided. The preferred design is for the writer to call a backend provisioning API. The backend uses Firebase Admin privileges to create and update Firestore documents.

## Backend API Shape

The writer should call backend APIs rather than writing directly to Firestore.

Recommended endpoints:

```text
POST /api/nfc-tags/provision-intent
POST /api/nfc-tags/provision-complete
POST /api/nfc-tags/provision-failed
```

### `provision-intent`

Called after the writer detects that a tag needs to be written.

Inputs may include:

```json
{
  "uid": "04AABBCCDDEE...",
  "readerId": "writer-station-01",
  "batchId": "batch-2026-04-29-a",
  "productId": "product_123",
  "ownerId": "owner_456"
}
```

Backend responsibilities:

- Validate that the writer station is allowed to provision tags.
- Create a Firestore NFC document.
- Reserve the document with a non-final status such as `reserved` or `writing`.
- Generate the public payload URL.
- Return the document ID and payload.

Example response:

```json
{
  "nfcId": "0b452473-1a29-bcb4-491e-cf2e50ee3513",
  "payload": "https://www.example.com/nfc/0b452473-1a29-bcb4-491e-cf2e50ee3513",
  "status": "writing"
}
```

### `provision-complete`

Called only after the tag has been written, protected, and verified.

Inputs may include:

```json
{
  "nfcId": "0b452473-1a29-bcb4-491e-cf2e50ee3513",
  "uid": "04AABBCCDDEE...",
  "readerId": "writer-station-01",
  "writeProtected": true,
  "payload": "https://www.example.com/nfc/0b452473-1a29-bcb4-491e-cf2e50ee3513"
}
```

Backend responsibilities:

- Mark the Firestore document as `provisioned`.
- Store the physical chip UID.
- Store provisioning metadata.
- Make the tag available to the rest of the product workflow.

### `provision-failed`

Called when writing, protection, or verification fails.

Inputs may include:

```json
{
  "nfcId": "0b452473-1a29-bcb4-491e-cf2e50ee3513",
  "uid": "04AABBCCDDEE...",
  "readerId": "writer-station-01",
  "failureReason": "failed_to_set_write_access_rights"
}
```

Backend responsibilities:

- Mark the document as `failed`.
- Preserve enough diagnostic information to understand what happened.
- Optionally allow the failed document to be retried, retired, or manually inspected.

## Firestore Status Model

Recommended statuses:

```text
reserved
writing
provisioned
failed
retired
```

Status meanings:

- `reserved`: backend created a document, but the physical tag has not yet been successfully written.
- `writing`: writer is actively attempting to write/protect the tag.
- `provisioned`: tag was written, protected, verified, and is ready for use.
- `failed`: provisioning did not complete cleanly.
- `retired`: tag/document should no longer be treated as active.

The backend should not treat a tag as fully active until the writer reports `provision-complete`.

## Provisioning State Machine

The provisioning application should run as a daemon or TUI loop.

```text
idle
wait_for_tag
read_tag
classify_tag
request_provision_intent
write_payload
apply_write_protection
verify_tag
report_success
wait_for_removal
repeat
```

Failure states:

```text
report_failure
operator_attention_required
wait_for_removal
repeat
```

### State Details

#### `idle`

Initialize the reader, load configuration, verify backend connectivity, verify key storage access, and prepare the terminal UI or status output.

#### `wait_for_tag`

Poll the ACR1552U through PC/SC until a tag is detected. The writer should not require a keyboard action for each tag.

#### `read_tag`

Read basic tag information:

- UID;
- ATR or card type data;
- existing NDEF payload, if readable;
- write/protection status, if detectable.

#### `classify_tag`

Decide whether the tag should be written.

Example classifications:

```text
blank_or_empty
invalid_payload
already_provisioned
write_protected_unknown
unsupported_tag
read_error
```

Recommended behavior:

- `blank_or_empty`: provision it.
- `invalid_payload`: provision only if the workflow allows overwriting unprotected tags.
- `already_provisioned`: skip and signal that the tag is already written.
- `write_protected_unknown`: fail safely and require operator review.
- `unsupported_tag`: reject.
- `read_error`: retry a limited number of times, then fail.

#### `request_provision_intent`

Call the backend API to create or reserve a Firestore NFC document. The backend returns the generated document ID and payload URL.

The writer should not generate final document IDs locally unless the backend explicitly supports that workflow.

#### `write_payload`

Write the returned URL to the tag as an NDEF URI record:

```text
https://www.example.com/nfc/<nfcDocumentId>
```

The payload remains public and phone-readable.

#### `apply_write_protection`

Provision the NTAG424 DNA access rights so that:

- read access remains public;
- write/clear/overwrite requires AES authentication;
- default keys are replaced or access rights are set to keys controlled by the provisioning system;
- future changes require the provisioning key path.

This is the security-critical step. It is not the same as writing the NDEF bytes. It requires NTAG424 DNA secure messaging support in the writer software.

#### `verify_tag`

Verify enough to trust the result:

- read the NDEF URL back if possible;
- confirm the payload matches the backend response;
- attempt or inspect write-protection state;
- optionally attempt a non-authenticated overwrite test in development mode only;
- confirm the backend document is still in the expected provisional state.

In production, avoid destructive verification. Do not perform an overwrite test on every live tag.

#### `report_success`

Call `provision-complete` on the backend. Mark the document `provisioned` only after the tag has passed local verification.

The writer should signal success with a clear terminal message, LED, beep, or all three.

#### `wait_for_removal`

Wait until the operator removes the tag before returning to `wait_for_tag`. This prevents accidentally processing the same tag multiple times.

#### `report_failure`

Call `provision-failed` if a backend document was already reserved. Include a concrete failure reason.

The writer should signal failure differently than success so the operator can separate failed tags from provisioned tags.

## Example Full Provisioning Flow

### 1. Operator Places a Blank NTAG424 DNA Tag

The daemon is already running:

```text
writer-station-01: waiting for tag...
```

The operator places a tag on the ACR1552U.

The writer detects the tag and reads its UID:

```text
UID: 04AABBCCDDEE11
Detected: NTAG424 DNA / Type 4 Tag
Existing NDEF: empty
Classification: blank_or_empty
```

### 2. Writer Requests a Backend Provisioning Intent

The writer calls:

```text
POST /api/nfc-tags/provision-intent
```

Example request:

```json
{
  "uid": "04AABBCCDDEE11",
  "readerId": "writer-station-01",
  "batchId": "batch-2026-04-29-a",
  "productId": "product_123",
  "ownerId": "owner_456"
}
```

The backend creates a Firestore document:

```text
nfcTags/0b452473-1a29-bcb4-491e-cf2e50ee3513
```

Initial document state:

```json
{
  "ownerId": "owner_456",
  "productId": "product_123",
  "payload": "https://www.example.com/nfc/0b452473-1a29-bcb4-491e-cf2e50ee3513",
  "status": "writing",
  "uid": "04AABBCCDDEE11",
  "readerId": "writer-station-01",
  "batchId": "batch-2026-04-29-a"
}
```

The backend returns:

```json
{
  "nfcId": "0b452473-1a29-bcb4-491e-cf2e50ee3513",
  "payload": "https://www.example.com/nfc/0b452473-1a29-bcb4-491e-cf2e50ee3513",
  "status": "writing"
}
```

### 3. Writer Encodes the Public Payload

The writer creates an NDEF URI record containing:

```text
https://www.example.com/nfc/0b452473-1a29-bcb4-491e-cf2e50ee3513
```

It writes that payload to the tag's NDEF file.

At this point the tag is readable, but the provisioning is not complete until write protection has been applied and verified.

### 4. Writer Applies NTAG424 DNA Write Protection

The writer authenticates with the appropriate AES key path and configures access rights.

Target result:

```text
NDEF read: public
NDEF write: authenticated only
NDEF clear/overwrite: authenticated only
File/key configuration changes: authenticated only
```

The exact command sequence belongs in the implementation code and should be validated against NXP documentation and test tags before production use.

### 5. Writer Verifies the Tag

The writer verifies:

```text
Payload readback: matches expected URL
Protection status: expected authenticated-write configuration
Backend status: still writing/reserved for this station
```

If verification passes, the writer proceeds.

If verification fails, the writer reports failure to the backend and tells the operator to remove the tag into a failed/review bin.

### 6. Writer Reports Completion

The writer calls:

```text
POST /api/nfc-tags/provision-complete
```

Example request:

```json
{
  "nfcId": "0b452473-1a29-bcb4-491e-cf2e50ee3513",
  "uid": "04AABBCCDDEE11",
  "readerId": "writer-station-01",
  "writeProtected": true,
  "payload": "https://www.example.com/nfc/0b452473-1a29-bcb4-491e-cf2e50ee3513"
}
```

The backend updates Firestore:

```json
{
  "status": "provisioned",
  "writeProtected": true,
  "provisionedAt": "<server timestamp>",
  "provisionedBy": "writer-station-01"
}
```

The writer signals success:

```text
SUCCESS: provisioned 0b452473-1a29-bcb4-491e-cf2e50ee3513
Remove tag.
```

### 7. Operator Removes the Tag

The writer waits until the tag is removed. Once removed, it returns to:

```text
waiting for tag...
```

## Failure Handling

Provisioning must assume partial failure can happen.

Examples:

- backend document created, but tag write failed;
- payload written, but write protection failed;
- write protection applied, but verification failed;
- backend completion call failed after the tag was successfully written;
- operator removes the tag too early.

Recommended behavior:

- Use backend statuses so incomplete documents are visible.
- Include `readerId`, `batchId`, UID, and failure reason in every failure report.
- Keep an optional local SQLite event log so the writer can recover from network or process crashes.
- Make success and failure signals unambiguous.
- Do not reuse failed Firestore documents unless the backend explicitly supports retry semantics.

## Local SQLite Role

Firestore remains the source of truth. SQLite is optional and should only be used for local resilience.

Useful local records:

```text
timestamp
readerId
uid
nfcId
payload
state
lastError
backendSynced
```

This helps recover if the writer loses network connectivity after writing a tag but before reporting completion.

## Key Management Plan

Development:

- Use test keys only.
- Store them outside git.
- Prefer OS keychain or an encrypted local config file.
- Keep a separate test Firebase project or test batch IDs.

Production:

- Do not store master keys in plain JSON.
- Prefer SAM AV3, KMS, HSM, or OS keychain-backed storage.
- Use per-tag key diversification rather than one shared key for every tag.
- Log key version metadata, but never log raw keys.
- Plan recovery and rotation before writing production tags.

## Security Scope

In scope for the first phase:

- prevent unauthorized overwrite/clear of the original NTAG424 DNA tag;
- keep the tag phone-readable;
- preserve backend ownership enforcement through Firebase;
- automate high-throughput writing.

Out of scope for the first phase:

- anti-cloning;
- dynamic SUN/SDM backend verification;
- tamper-loop handling for NTAG424 DNA TagTamper;
- multi-reader production orchestration.

Future progression:

- Add SUN/SDM so the scanned URL includes dynamic authentication parameters.
- Verify CMAC/counter data server-side.
- Detect copied static URLs.
- Add multi-station batch dashboards.
- Move key operations into SAM AV3 or another hardware-backed key system.

## Initial Build Milestones

1. Build a non-secure automated writer loop using ACR1552U, `pyscard`, and backend API calls.
2. Add robust tag classification and backend status handling.
3. Add NTAG424 DNA secure provisioning on test tags.
4. Validate that ordinary NFC writer apps cannot overwrite provisioned test tags.
5. Add recovery behavior for partial failures.
6. Move keys out of local development storage.
7. Run a small pilot batch and inspect Firestore records, scan behavior, and failure logs.

