# NFC Reader/Writer Tools

Python command-line tools for reading, writing, testing, and diagnosing NFC tags.

The scripts are interactive: run one, place a tag on the reader when prompted, and choose an operation from the menu.

## Repository Structure

```
nfc-reader-writer/
├── activate_nfc_env.sh       # Shared launcher and environment setup
├── writer_ACR122U/           # Non-secure writing scripts for the ACR122U reader
└── writer_dna_ACR1552U/      # Research and plan for secure NTAG424 DNA writing (ACR1552U)
```

### `activate_nfc_env.sh`
Shared launcher for the NFC scripts. If `nfc_env/` does not already exist, it creates a Python virtual environment and installs the required packages (`pyscard`, `pycryptodome`, `ndef`).

Run it with no arguments to print available tools, or pass a script name to activate the environment and run that script:

```bash
./activate_nfc_env.sh
./activate_nfc_env.sh ntag213_215_readwrite.py
```

You can pass just the script name — the launcher looks for it in `writer_ACR122U/` automatically.

### `writer_ACR122U/`
Scripts for the ACS ACR122U reader. These write tags in the open/unprotected mode — any NFC writer app or phone can overwrite the tags they produce.

See [writer_ACR122U/README.md](writer_ACR122U/README.md) for details on each script.

### `writer_dna_ACR1552U/`
Research and implementation plan for AES-backed NTAG424 DNA secure provisioning using the ACS ACR1552U. Tags written by this future station will be phone-readable but cannot be overwritten without AES authentication.

Hardware not yet acquired. No implementation scripts exist yet.

See [writer_dna_ACR1552U/README.md](writer_dna_ACR1552U/README.md) for details.

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
python writer_ACR122U/ntag213_215_readwrite.py
```

## Requirements

- ACS ACR122U NFC reader/writer
- Python 3
- NFC tags compatible with the script you plan to use
- Python packages: `pyscard`, `pycryptodome`, `ndef`

## Generated Local Files

These may appear while using the repository but are not source files:

- `nfc_env/`: Python virtual environment created by `activate_nfc_env.sh`.
- `writer_ACR122U/ntag424_keys.json`: Local UID-to-key store created by `ntag424_dna_readwrite.py`. Contains sensitive material — do not commit.
- `.DS_Store`, `.vscode/`, and similar editor/OS files.

## Security Notes

- `ntag424_keys.json` can contain authentication keys. Keep it local and out of git.
- The scripts in `writer_ACR122U/` do not apply NTAG424 write protection. Tags they produce can be overwritten by any NFC writer.
- For write-protected tags, see the plan in `writer_dna_ACR1552U/`.
- Do not commit real tag keys, production secrets, or dumps of sensitive tag data.
