# NFC Reader/Writer Tools

Python command-line tools for reading, writing, testing, and diagnosing NFC tags with an ACR122U USB NFC reader/writer.

The scripts are interactive: run one, place a tag on the reader when prompted, and choose an operation from the menu.

## Repository Files

### `README.md`
This document. It explains the purpose of the repository, what each file does, how to set up the Python environment, and the security notes for locally stored NFC keys.

### `.gitignore`
Keeps local-only and sensitive files out of version control. In particular, it should exclude the virtual environment (`nfc_env/`) and the NTAG424 key store (`ntag424_keys.json`) that can be generated while using the tools.

### `activate_nfc_env.sh`
Convenience launcher for the NFC scripts. If `nfc_env/` does not already exist, it creates a Python virtual environment and installs the required packages:

- `pyscard`
- `pycryptodome`
- `ndef`

Run it with no arguments to print the available tools, or pass a script name to activate the environment and start that script:

```bash
./activate_nfc_env.sh
./activate_nfc_env.sh ntag213_215_readwrite.py
```

### `test_nfc.py`
Hardware smoke test for the ACR122U reader. It lists connected smart-card readers, selects the first reader whose name contains `ACR122`, connects to it, asks for the firmware version, sends a couple of reader control commands, and reports whether the reader is ready.

Use this first when setting up the project or troubleshooting reader connectivity.

### `nfc_diagnose.py`
Diagnostic script for identifying and inspecting a tag. It waits for a card, prints the UID and ATR, tries to infer whether the card is an NTAG or Mifare Classic card, reads configuration/user-memory blocks, and performs a small write test on block/page 4 before restoring the original data.

Use this when you do not know what kind of tag you have, when writes are failing, or when you want to check for authentication or write-protection behavior.

### `ntag213_215_readwrite.py`
Dedicated reader/writer for NTAG21x-style tags, especially NTAG213, NTAG215, and NTAG216. NTAG tags use 4-byte pages, and this script works directly with that page layout.

The menu supports:

- Reading card UID and the first pages of memory
- Reading plain text or simple NDEF content from user memory
- Writing plain text
- Writing NDEF URL records for phone tap-to-open behavior
- Writing NDEF text/JSON records for app use
- Clearing user-memory pages

Use this for NTAG213/215/216 tags when you want simple phone-readable URLs or text data.

### `mifare_classic_readwrite.py`
General-purpose ACR122U reader/writer that handles both Mifare Classic and NTAG/Ultralight-style tags. It tries several common Mifare Classic keys, authenticates before reading or writing Classic blocks, skips sector trailers when writing user data, and uses 4-byte pages for NTAG-style tags.

The menu supports:

- Reading card UID, card type, and initial memory blocks/pages
- Reading text from card memory
- Writing plain text
- Writing NDEF URL records
- Clearing card data
- Testing Mifare Classic authentication on block 4

Use this when you have mixed tag types or need Mifare Classic authentication support. For NTAG-only work, `ntag213_215_readwrite.py` is usually simpler.

### `ntag424_dna_readwrite.py`
Experimental NTAG424 DNA / Type 4 Tag tool. It uses ISO 7816-style APDU commands, selects NDEF-related applications/files, reads and writes NDEF URL/text payloads, can try to initialize missing NDEF structures, and includes AES-related helper code for authentication experiments.

The menu supports:

- Reading card UID and Type 4 Tag information
- Reading NDEF messages, with several fallbacks for cards that behave differently
- Writing NDEF URL records
- Writing NDEF text records
- Clearing the NDEF message by setting `NLEN` to zero
- Generating and storing a local key for a tag UID
- Testing authentication with a stored key
- Attempting NDEF structure initialization

Important: the provisioning path stores a generated key locally, but the script itself notes that full NTAG424 write-protection provisioning requires additional NTAG424-specific commands or vendor tooling. Treat this script as a development/testing tool rather than production-grade NTAG424 security tooling.

## Generated Local Files

These files/directories may appear while using the repository but are not source files:

- `nfc_env/`: Python virtual environment created by `activate_nfc_env.sh`.
- `ntag424_keys.json`: Local UID-to-key store created by `ntag424_dna_readwrite.py` when provisioning/testing NTAG424 keys. This file contains sensitive material and should not be committed.
- `.DS_Store`, `.vscode/`, and similar editor/OS files: local machine metadata.

## Requirements

- ACR122U NFC reader/writer
- Python 3
- NFC tags compatible with the script you plan to use
- Python packages:
  - `pyscard`
  - `pycryptodome`
  - `ndef`

The helper script installs all three packages into `nfc_env/`.

## Quick Start

1. Connect the ACR122U reader.
2. Run the hardware smoke test:

   ```bash
   ./activate_nfc_env.sh test_nfc.py
   ```

3. Diagnose a tag if you are not sure what type it is:

   ```bash
   ./activate_nfc_env.sh nfc_diagnose.py
   ```

4. Run the tool that matches your tag:

   ```bash
   ./activate_nfc_env.sh ntag213_215_readwrite.py
   ./activate_nfc_env.sh mifare_classic_readwrite.py
   ./activate_nfc_env.sh ntag424_dna_readwrite.py
   ```

## Manual Setup

If you prefer not to use the launcher:

```bash
python3 -m venv nfc_env
source nfc_env/bin/activate
pip install pyscard pycryptodome ndef
python ntag213_215_readwrite.py
```

## Choosing a Script

- Use `test_nfc.py` to confirm the reader is connected.
- Use `nfc_diagnose.py` to identify a tag or investigate read/write failures.
- Use `ntag213_215_readwrite.py` for NTAG213/215/216 tags.
- Use `mifare_classic_readwrite.py` for Mifare Classic tags or mixed tag batches.
- Use `ntag424_dna_readwrite.py` for NTAG424 DNA / Type 4 Tag NDEF experiments.

## Security Notes

- `ntag424_keys.json` can contain authentication keys. Keep it local and out of git.
- The NTAG424 key store is plain JSON intended for development and testing, not production deployments.
- Do not commit real tag keys, production secrets, or dumps of sensitive tag data.
- Be careful with clear/write operations. Several scripts write directly to card memory and can overwrite existing data.

For production key handling, consider secure storage such as a hardware security module, a platform keychain, or a dedicated secrets manager.
