# writer_ACR122U

Scripts for reading and writing NFC tags using the ACS ACR122U USB NFC reader.

These scripts write tags in the open/unprotected mode. Any NFC writer app or phone with write access can overwrite tags produced here. Use them for development, diagnostics, and plain NDEF payloads where write protection is not required.

## Scripts

### `test_nfc.py`
Hardware smoke test. Lists connected smart-card readers, selects the first ACR122U, checks the firmware version, and reports whether the reader is ready. Run this first when setting up or troubleshooting reader connectivity.

### `nfc_diagnose.py`
Diagnostic script for identifying an unknown tag. Reads the UID and ATR, infers tag type, reads configuration and user-memory blocks, and performs a small write test before restoring the original data.

### `ntag213_215_readwrite.py`
Reader/writer for NTAG213, NTAG215, and NTAG216 tags. Supports reading UID and memory, writing plain text, writing NDEF URL and text/JSON records, and clearing user memory.

### `mifare_classic_readwrite.py`
General-purpose reader/writer for Mifare Classic and NTAG/Ultralight tags. Tries common Mifare Classic keys, authenticates before reading or writing, and supports plain text, NDEF URL records, and card clearing. Use this when working with mixed tag types or when Mifare Classic authentication is needed.

### `ntag424_dna_readwrite.py`
Experimental NTAG424 DNA / Type 4 Tag tool. Reads and writes NDEF URL and text payloads using ISO 7816-style APDUs. Includes AES helper code and a local key store for authentication experiments, but does not perform full NTAG424 write-protection provisioning. Treat it as a development and testing tool.

## Usage

Run scripts from the repo root using the launcher:

```bash
./activate_nfc_env.sh test_nfc.py
./activate_nfc_env.sh nfc_diagnose.py
./activate_nfc_env.sh ntag213_215_readwrite.py
./activate_nfc_env.sh mifare_classic_readwrite.py
./activate_nfc_env.sh ntag424_dna_readwrite.py
```

Or activate the environment manually and run from this directory:

```bash
source ../nfc_env/bin/activate
python test_nfc.py
```

## Limitations

- Tags written here have no write protection. Any NFC app can overwrite them.
- The NTAG424 script cannot set NTAG424 access rights or perform secure messaging. See `writer_dna_ACR1552U/` for the plan to implement that.
- The ACR122U is end-of-life. ACS recommends the ACR1552U for new work.
