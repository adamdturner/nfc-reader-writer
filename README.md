# NFC Reader/Writer Tools

This repository contains Python scripts for reading and writing to different types of NFC chips using the ACR122U NFC reader/writer.

## Files

### `mifare_classic_readwrite.py`
A comprehensive NFC tool that supports both **Mifare Classic** and **NTAG** cards. This is the main utility that provides:

- **Card Detection**: Automatically detects whether the card is Mifare Classic or NTAG
- **Authentication**: Handles Mifare Classic authentication with multiple default keys
- **Reading**: Reads card data, UID, and text content
- **Writing**: Writes plain text or NDEF URL records to cards
- **NDEF Support**: Creates properly formatted NDEF messages for phone tap-to-open functionality
- **Card Management**: Clears card data and sets up MIFARE Application Directory (MAD) for NDEF compliance

**Best for**: General-purpose NFC operations, especially when you have mixed card types.

### `ntag213_215_readwrite.py`
Specialized tool optimized specifically for **NTAG213/215/216** cards. Features include:

- **NTAG Detection**: Identifies specific NTAG card types and memory sizes
- **NDEF Writing**: Creates NDEF URL and text records optimized for smartphone compatibility
- **Page-based Operations**: Works with NTAG's 4-byte page structure
- **Smart Parsing**: Automatically detects and parses NDEF content when reading
- **Phone Compatibility**: Ensures written NDEF records work with both iPhone and Android

**Best for**: NTAG cards only, especially when you need reliable phone tap-to-open functionality.

### `ntag424_dna_readwrite.py`
Advanced tool for **NTAG424 DNA** cards with full security features:

- **T4T Support**: Uses ISO/IEC 14443 Type 4 Tag protocol for NDEF operations
- **Write Protection**: Implements AES-128 authentication for secure write operations
- **Tag Provisioning**: One-time setup to enable write protection while keeping tags phone-readable
- **Key Management**: Generates and stores AES-128 keys locally for testing
- **Secure Authentication**: AES challenge/response authentication before write operations
- **Universal Readability**: Tags remain readable by all phones while write-protected
- **Advanced NDEF**: Supports both URL and text NDEF records with proper encoding
- **Professional Features**: Uses proper APDU commands for file selection and binary operations

**Best for**: NTAG424 DNA cards requiring write protection, professional applications, secure deployments.

### `nfc_diagnose.py`
Diagnostic tool for troubleshooting NFC issues and identifying card types:

- **Card Analysis**: Detects card type, memory size, and capabilities
- **Authentication Testing**: Checks if cards require authentication
- **Write Protection Detection**: Identifies if cards are write-protected
- **Memory Inspection**: Reads and displays raw card data
- **Troubleshooting**: Provides recommendations based on card type and status

**Best for**: Troubleshooting, card identification, and understanding card capabilities.

### `test_nfc.py`
Simple test script to verify ACR122U reader functionality:

- **Reader Detection**: Checks if ACR122U is connected and recognized
- **Connection Testing**: Verifies communication with the reader
- **Firmware Info**: Displays reader firmware version
- **LED Control**: Tests reader LED indicators
- **Basic Functionality**: Confirms the reader is ready for NFC operations

**Best for**: Initial setup verification and confirming hardware is working.

## Requirements

- **ACR122U NFC Reader/Writer**
- **Python 3.x**
- **pyscard library**: `pip install pyscard`
- **NFC Tags**: Mifare Classic, NTAG213/215/216, NTAG424 DNA, or other compatible cards

### Additional Dependencies for NTAG424 DNA Security
- **pycryptodome library**: `pip install pycryptodome` (for AES encryption)
- **ndef library**: `pip install ndef` (for NDEF message handling)

## Installation & Usage

### Quick Start (Recommended)
1. Connect your ACR122U reader
2. Run the activation script: `./activate_nfc_env.sh`
3. Choose your tool from the menu or run directly:
   ```bash
   ./activate_nfc_env.sh ntag424_dna_readwrite.py
   ```

### Manual Setup
If you prefer to set up manually:
1. Create virtual environment: `python3 -m venv nfc_env`
2. Activate it: `source nfc_env/bin/activate`
3. Install dependencies: `pip install pyscard pycryptodome ndef`
4. Run scripts: `python ntag424_dna_readwrite.py`

### Available Tools
- **`ntag424_dna_readwrite.py`** - NTAG424 DNA with security features
- **`ntag213_215_readwrite.py`** - NTAG213/215/216 operations  
- **`mifare_classic_readwrite.py`** - General NFC operations
- **`nfc_diagnose.py`** - Troubleshooting and card identification
- **`test_nfc.py`** - Verify ACR122U reader functionality

Each script provides an interactive menu to guide you through the available operations.

## Security Notes

⚠️ **Important Security Considerations:**

- **NTAG424 DNA Keys**: The `ntag424_keys.json` file contains sensitive authentication keys and is automatically excluded from git via `.gitignore`
- **Local Testing Only**: Keys are stored in plain text for development - use secure storage for production
- **Virtual Environment**: The `nfc_env/` folder contains installed packages and is excluded from version control
- **Never Commit Keys**: Always ensure authentication keys are never committed to version control

For production deployments, consider using:
- Hardware Security Modules (HSM) for key storage
- Environment variables for key management
- Secure key derivation from master keys
- Proper key rotation procedures
