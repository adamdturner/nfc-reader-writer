#!/bin/bash
# Activate NFC environment and run NFC tools
# Usage: ./activate_nfc_env.sh [script_name]

# Check if virtual environment exists
if [ ! -d "nfc_env" ]; then
    echo "❌ Virtual environment not found!"
    echo "🔧 Creating virtual environment..."
    python3 -m venv nfc_env
    echo "📦 Installing dependencies..."
    source nfc_env/bin/activate
    pip install pyscard pycryptodome ndef
    echo "✅ Setup complete!"
fi

# Activate virtual environment
echo "🚀 Activating NFC environment..."
source nfc_env/bin/activate

# Run the specified script or show menu
if [ $# -eq 0 ]; then
    echo ""
    echo "📋 Available NFC tools (writer_ACR122U/):"
    echo "1. ntag424_dna_readwrite.py - NTAG424 DNA (open write, no protection)"
    echo "2. ntag213_215_readwrite.py - NTAG213/215/216"
    echo "3. mifare_classic_readwrite.py - Mifare Classic"
    echo "4. nfc_diagnose.py - Diagnostic tool"
    echo "5. test_nfc.py - Test ACR122U reader"
    echo ""
    echo "Usage: ./activate_nfc_env.sh <script_name>"
    echo "Example: ./activate_nfc_env.sh ntag213_215_readwrite.py"
else
    SCRIPT="$1"
    # If the script name has no path prefix, look in writer_ACR122U/
    if [ ! -f "$SCRIPT" ] && [ -f "writer_ACR122U/$SCRIPT" ]; then
        SCRIPT="writer_ACR122U/$SCRIPT"
    fi
    echo "🏃 Running $SCRIPT..."
    python "$SCRIPT"
fi
