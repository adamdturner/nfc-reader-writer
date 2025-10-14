#!/usr/bin/env python3
"""
NFC Read/Write Tool for ACR122U
Supports reading and writing to NTAG213/215/216 and Mifare Classic tags
"""

from smartcard.System import readers
from smartcard.util import toHexString, toBytes
from smartcard.CardMonitoring import CardMonitor, CardObserver
import time
import sys

class NFCCardObserver(CardObserver):
    """Observer that detects when cards are inserted/removed"""
    
    def __init__(self):
        self.cards = []
        
    def update(self, observable, actions):
        (addedcards, removedcards) = actions
        for card in addedcards:
            print(f"\n🏷️  NFC tag detected: {toHexString(card.atr)}")
            self.cards.append(card)
        for card in removedcards:
            print("\n🏷️  NFC tag removed")
            if card in self.cards:
                self.cards.remove(card)

class ACR122U:
    """ACR122U NFC Reader/Writer"""
    
    # Default Mifare Classic keys
    DEFAULT_KEYS = [
        [0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF],  # Default key
        [0xA0, 0xA1, 0xA2, 0xA3, 0xA4, 0xA5],  # MAD key
        [0xD3, 0xF7, 0xD3, 0xF7, 0xD3, 0xF7],  # NDEF key
        [0x00, 0x00, 0x00, 0x00, 0x00, 0x00],   # Null key
        [0x12, 0x34, 0x56, 0x78, 0x9A, 0xBC],  # Common key
        [0xAB, 0xCD, 0xEF, 0x12, 0x34, 0x56],  # Another common key
    ]
    
    def __init__(self):
        self.reader = None
        self.connection = None
        self.is_mifare_classic = False
        self._find_reader()
        
    def _find_reader(self):
        """Find ACR122U reader"""
        r = readers()
        for reader in r:
            if "ACR122" in str(reader):
                self.reader = reader
                print(f"✅ Found reader: {reader}")
                return
        raise Exception("ACR122U reader not found!")
    
    def connect(self):
        """Connect to the reader (without card)"""
        try:
            self.connection = self.reader.createConnection()
            # Direct connection to reader
            self.connection.connect()
            return True
        except:
            # This is normal - reader is there but no card
            return False
            
    def wait_for_card(self):
        """Wait for an NFC card to be placed on reader"""
        print("\n⏳ Place an NFC tag on the reader...")
        while True:
            try:
                self.connection = self.reader.createConnection()
                self.connection.connect()
                # If we get here, a card is present
                print("✅ Card detected!")
                return True
            except Exception as e:
                time.sleep(0.1)
                continue
                
    def get_uid(self):
        """Get the UID of the current card"""
        # Get UID command
        GET_UID = [0xFF, 0xCA, 0x00, 0x00, 0x00]
        data, sw1, sw2 = self.connection.transmit(GET_UID)
        if sw1 == 0x90 and sw2 == 0x00:
            uid = toHexString(data)
            return uid
        return None
    
    def detect_card_type(self):
        """Detect if card is Mifare Classic or NTAG"""
        # Try Mifare Classic auth with default key on block 0
        for key in self.DEFAULT_KEYS:
            if self.auth_mifare_classic(0, key):
                self.is_mifare_classic = True
                print("🔐 Mifare Classic card detected")
                return "Mifare Classic"
        
        # If auth failed, likely NTAG
        self.is_mifare_classic = False
        print("📱 NTAG/Ultralight card detected")
        return "NTAG/Ultralight"
    
    def auth_mifare_classic(self, block, key):
        """Authenticate to Mifare Classic block"""
        # Load key into reader
        LOAD_KEY = [0xFF, 0x82, 0x00, 0x00, 0x06] + key
        try:
            data, sw1, sw2 = self.connection.transmit(LOAD_KEY)
            if sw1 != 0x90 or sw2 != 0x00:
                print(f"Load key failed: SW1={sw1:02X}, SW2={sw2:02X}")
                return False
            
            # Authenticate
            sector = block // 4
            AUTH_CMD = [0xFF, 0x86, 0x00, 0x00, 0x05, 0x01, 0x00, block, 0x60, 0x00]
            data, sw1, sw2 = self.connection.transmit(AUTH_CMD)
            if sw1 != 0x90 or sw2 != 0x00:
                print(f"Auth failed for block {block}: SW1={sw1:02X}, SW2={sw2:02X}")
            return sw1 == 0x90 and sw2 == 0x00
        except Exception as e:
            print(f"Auth exception for block {block}: {e}")
            return False
    
    def find_working_key(self, block):
        """Try to find a working key for the given block"""
        print(f"🔍 Searching for working key for block {block}...")
        for i, key in enumerate(self.DEFAULT_KEYS):
            key_str = ' '.join(f'{b:02X}' for b in key)
            print(f"  Trying key {i+1}: {key_str}")
            if self.auth_mifare_classic(block, key):
                print(f"✅ Found working key: {key_str}")
                return key
        print("❌ No working key found")
        return None
        
    def read_block(self, block):
        """Read a block from the card"""
        # For Mifare Classic, ensure we're authenticated
        if self.is_mifare_classic:
            sector = block // 4
            first_block = sector * 4
            # Try to authenticate if needed
            authenticated = False
            for key in self.DEFAULT_KEYS:
                if self.auth_mifare_classic(first_block, key):
                    authenticated = True
                    break
            if not authenticated:
                print(f"❌ Cannot authenticate to sector {sector}")
                return None
        
        # Read command
        if self.is_mifare_classic:
            READ_CMD = [0xFF, 0xB0, 0x00, block, 0x10]  # Read 16 bytes
        else:
            READ_CMD = [0xFF, 0xB0, 0x00, block, 0x04]  # Read 4 bytes for NTAG
        
        try:
            data, sw1, sw2 = self.connection.transmit(READ_CMD)
            if sw1 == 0x90 and sw2 == 0x00:
                return data
        except:
            pass
        return None
        
    def write_block(self, block, data):
        """Write data to a block"""
        if self.is_mifare_classic:
            # Mifare Classic uses 16-byte blocks
            if len(data) == 4:
                # Pad to 16 bytes for Mifare Classic
                data = data + [0x00] * 12
            elif len(data) != 16:
                raise ValueError("Data must be 4 or 16 bytes")
        else:
            # NTAG uses 4-byte pages
            if len(data) != 4:
                raise ValueError("Data must be exactly 4 bytes")
        
        # For Mifare Classic, authenticate first
        if self.is_mifare_classic:
            sector = block // 4
            first_block = sector * 4
            authenticated = False
            for key in self.DEFAULT_KEYS:
                if self.auth_mifare_classic(first_block, key):
                    authenticated = True
                    break
            if not authenticated:
                print(f"❌ Cannot authenticate to sector {sector}")
                return False
        
        # Write command
        if self.is_mifare_classic:
            WRITE_CMD = [0xFF, 0xD6, 0x00, block, 0x10] + data[:16]
        else:
            WRITE_CMD = [0xFF, 0xD6, 0x00, block, 0x04] + data[:4]
        
        try:
            response, sw1, sw2 = self.connection.transmit(WRITE_CMD)
            if sw1 == 0x90 and sw2 == 0x00:
                return True
            else:
                print(f"Write failed: SW1={sw1:02X}, SW2={sw2:02X}")
        except Exception as e:
            print(f"Write error: {e}")
        return False
        
    def create_ndef_url_record(self, url):
        """Create an NDEF URL record"""
        # URL identifier codes for common prefixes
        url_prefixes = {
            'http://www.': 0x01,
            'https://www.': 0x02,
            'http://': 0x03,
            'https://': 0x04,
        }
        
        # Find matching prefix
        url_code = 0x00  # No prefix
        url_suffix = url
        for prefix, code in url_prefixes.items():
            if url.startswith(prefix):
                url_code = code
                url_suffix = url[len(prefix):]
                break
        
        # Build payload (URL code + URL suffix)
        payload = [url_code] + list(url_suffix.encode('utf-8'))
        payload_length = len(payload)
        
        # Build NDEF record with proper flags
        ndef_record = [
            0xD1,  # NDEF record header: MB=1, ME=1, CF=0, SR=1, IL=0, TNF=1
            0x01,  # Type Length = 1 ("U")
            payload_length,  # Payload Length
            0x55,  # Type = "U" (URI)
        ]
        
        # Add payload
        ndef_record.extend(payload)
        
        return ndef_record
    
    def create_ndef_message(self, url):
        """Create a complete NDEF message for Mifare Classic"""
        # Create the URL record
        url_record = self.create_ndef_url_record(url)
        
        # Build complete NDEF message with proper TLV structure
        message_length = len(url_record)
        
        # NDEF message structure for Mifare Classic
        # TLV: Tag=03 (NDEF Message), Length=message_length, Value=url_record
        ndef_message = [
            0x03,  # NDEF Message TLV Tag
            message_length,  # Length (single byte for short messages)
        ] + url_record
        
        # Add Terminator TLV
        ndef_message.append(0xFE)  # Terminator TLV
        
        return ndef_message
    
    def parse_ndef_url(self, data):
        """Parse NDEF URL record from raw data"""
        if len(data) < 5:
            return None
            
        # Skip message length (first 2 bytes)
        ndef_data = data[2:]
        
        # Check NDEF record header
        if ndef_data[0] != 0xD1:  # NDEF record header
            return None
            
        type_length = ndef_data[1]
        payload_length = ndef_data[2]
        
        if len(ndef_data) < 4 + payload_length:
            return None
            
        # Check if it's a URI record
        if ndef_data[3] != 0x55:  # URI type
            return None
            
        # Get URL code and suffix
        url_code = ndef_data[4]
        url_suffix = ndef_data[5:5+payload_length-1].decode('utf-8', errors='ignore')
        
        # Map URL codes to prefixes
        url_prefixes = {
            0x01: 'http://www.',
            0x02: 'https://www.',
            0x03: 'http://',
            0x04: 'https://',
        }
        
        prefix = url_prefixes.get(url_code, '')
        return prefix + url_suffix
    
    def write_text(self, text, start_block=4):
        """Write text to the card starting from specified block"""
        # Convert text to bytes
        text_bytes = text.encode('utf-8')
        
        if self.is_mifare_classic:
            # For Mifare Classic, avoid sector trailers (blocks 3, 7, 11, etc.)
            # and write in 16-byte chunks
            bytes_written = 0
            block = start_block
            
            while bytes_written < len(text_bytes):
                # Skip sector trailers
                if (block + 1) % 4 == 0:
                    block += 1
                
                # Get up to 16 bytes
                chunk = text_bytes[bytes_written:bytes_written+16]
                # Pad to 16 bytes
                chunk = chunk + b'\x00' * (16 - len(chunk))
                
                if not self.write_block(block, list(chunk)):
                    print(f"Failed to write block {block}")
                    return False
                
                bytes_written += 16
                block += 1
        else:
            # For NTAG, write in 4-byte chunks
            # Pad to multiple of 4 bytes
            while len(text_bytes) % 4 != 0:
                text_bytes += b'\x00'
                
            for i in range(0, len(text_bytes), 4):
                block = start_block + (i // 4)
                data = list(text_bytes[i:i+4])
                if not self.write_block(block, data):
                    print(f"Failed to write block {block}")
                    return False
                
        print(f"✅ Written {len(text_bytes)} bytes to card")
        return True
    
    def setup_mad(self):
        """Setup MIFARE Application Directory (MAD) for NDEF compliance"""
        print("🔧 Setting up MIFARE Application Directory...")
        
        # MAD sector (sector 0) - block 1 contains MAD data
        # MAD indicates that sector 1 contains NDEF data
        mad_data = [
            0x14, 0x01, 0x03, 0xE1, 0x03, 0xE1, 0x03, 0xE1, 0x03, 0xE1, 0x03, 0xE1, 0x03, 0xE1, 0x03, 0xE1
        ]
        
        # Write MAD to block 1
        if not self.write_block(1, mad_data):
            print("Failed to write MAD to block 1")
            return False
        
        # Setup NDEF sector (sector 1) - block 4 contains NDEF capability container
        ndef_capability = [
            0xE1, 0x10, 0x06, 0x00, 0x03, 0x00, 0xFE, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00
        ]
        
        # Write NDEF capability container to block 4
        if not self.write_block(4, ndef_capability):
            print("Failed to write NDEF capability container to block 4")
            return False
        
        print("✅ MAD setup complete")
        return True
    
    def write_ndef_url(self, url, start_block=5):
        """Write an NDEF URL record to the card"""
        if self.is_mifare_classic:
            # Setup MAD first
            if not self.setup_mad():
                return False
        
        # Create complete NDEF message
        ndef_message = self.create_ndef_message(url)
        
        print(f"NDEF message length: {len(ndef_message)} bytes")
        print(f"NDEF message (hex): {' '.join(f'{b:02X}' for b in ndef_message)}")
        
        if self.is_mifare_classic:
            # For Mifare Classic, write in 16-byte chunks starting from block 5
            bytes_written = 0
            block = start_block
            
            while bytes_written < len(ndef_message):
                # Skip sector trailers
                if (block + 1) % 4 == 0:
                    block += 1
                
                # Get up to 16 bytes
                chunk = ndef_message[bytes_written:bytes_written+16]
                # Pad to 16 bytes
                while len(chunk) < 16:
                    chunk.append(0x00)
                
                print(f"Writing block {block}: {' '.join(f'{b:02X}' for b in chunk)}")
                
                if not self.write_block(block, chunk):
                    print(f"Failed to write NDEF block {block}")
                    return False
                
                bytes_written += 16
                block += 1
        else:
            # For NTAG, write in 4-byte chunks
            # Pad to multiple of 4 bytes
            while len(ndef_message) % 4 != 0:
                ndef_message.append(0x00)
                
            for i in range(0, len(ndef_message), 4):
                block = start_block + (i // 4)
                data = ndef_message[i:i+4]
                if not self.write_block(block, data):
                    print(f"Failed to write NDEF block {block}")
                    return False
                
        print(f"✅ Written NDEF URL record: {url}")
        return True
    
    def clear_card(self, start_block=4, num_blocks=8):
        """Clear card data by writing zeros"""
        print("🧹 Clearing card data...")
        
        if self.is_mifare_classic:
            # Clear Mifare Classic blocks
            block = start_block
            blocks_cleared = 0
            
            while blocks_cleared < num_blocks:
                # Skip sector trailers
                if (block + 1) % 4 == 0:
                    block += 1
                    continue
                
                # Try to find a working key for this block
                working_key = self.find_working_key(block)
                if working_key:
                    # Try to write with the working key
                    if not self.write_block(block, [0x00] * 16):
                        print(f"Failed to clear block {block} even with working key")
                        return False
                else:
                    print(f"Cannot authenticate to block {block}, skipping...")
                    # Try to continue with other blocks
                
                block += 1
                blocks_cleared += 1
        else:
            # Clear NTAG blocks
            for i in range(num_blocks):
                block = start_block + i
                if not self.write_block(block, [0x00] * 4):
                    print(f"Failed to clear block {block}")
                    return False
        
        print("✅ Card cleared successfully")
        return True
        
    def read_text(self, start_block=5, num_blocks=8):
        """Read text from card"""
        text = b''
        
        if self.is_mifare_classic:
            # Read from Mifare Classic, skipping sector trailers
            block = start_block
            blocks_read = 0
            
            while blocks_read < num_blocks:
                # Skip sector trailers
                if (block + 1) % 4 == 0:
                    block += 1
                    continue
                
                data = self.read_block(block)
                if data is None:
                    print(f"Warning: Could not read block {block}")
                    break
                elif isinstance(data, list):
                    text += bytes(data[:16])  # Mifare Classic has 16-byte blocks
                else:
                    print(f"Warning: Unexpected data type from block {block}: {type(data)}")
                    break
                
                block += 1
                blocks_read += 1
        else:
            # Read from NTAG
            for i in range(num_blocks):
                data = self.read_block(start_block + i)
                if data is None:
                    print(f"Warning: Could not read block {start_block + i}")
                    break
                elif isinstance(data, list):
                    text += bytes(data[:4])  # NTAG has 4-byte pages
                else:
                    print(f"Warning: Unexpected data type from block {start_block + i}: {type(data)}")
                    break
                
        # Remove null padding
        text = text.rstrip(b'\x00')
        
        # Check if this looks like NDEF data (with TLV structure)
        if len(text) >= 3 and text[0] == 0x03 and text[1] == 0x1A and text[2] == 0xD1:
            url = self.parse_ndef_url(text)
            if url:
                return f"NDEF URL: {url} (tap card to phone to open)"
            else:
                return "NDEF record detected (use phone to read)"
        
        try:
            return text.decode('utf-8')
        except:
            return toHexString(text)

def main():
    print("🔵 ACR122U NFC Reader/Writer Tool")
    print("-" * 40)
    
    try:
        # Initialize reader
        nfc = ACR122U()
        
        while True:
            print("\n📋 Menu:")
            print("1. Read card info")
            print("2. Read text from card") 
            print("3. Write text to card")
            print("4. Write NDEF URL (for phone tap-to-open)")
            print("5. Clear card data")
            print("6. Test authentication")
            print("7. Exit")
            
            choice = input("\nSelect option (1-7): ").strip()
            
            if choice == '7':
                break
                
            if choice in ['1', '2', '3', '4', '5', '6']:
                # Wait for card
                nfc.wait_for_card()
                
                # Get card UID
                uid = nfc.get_uid()
                print(f"Card UID: {uid}")
                
                # Detect card type on first interaction
                if choice == '1':
                    card_type = nfc.detect_card_type()
                
                if choice == '1':
                    # Read first few blocks
                    print("\n📖 Reading card data:")
                    for block in range(0, 16):
                        # Skip sector trailers for Mifare Classic
                        if nfc.is_mifare_classic and (block + 1) % 4 == 0:
                            continue
                        data = nfc.read_block(block)
                        if data:
                            if nfc.is_mifare_classic:
                                print(f"Block {block:02d}: {toHexString(data[:16])}")
                            else:
                                print(f"Block {block:02d}: {toHexString(data[:4])}")
                            
                elif choice == '2':
                    # Read text
                    text = nfc.read_text()
                    print(f"\n📖 Text on card: '{text}'")
                    
                elif choice == '3':
                    # Write text
                    text = input("Enter text to write: ")
                    if nfc.write_text(text):
                        print("✅ Text written successfully!")
                        # Verify by reading back
                        verify = nfc.read_text()
                        print(f"Verified: '{verify}'")
                    else:
                        print("❌ Failed to write text")
                        
                elif choice == '4':
                    # Write NDEF URL
                    url = input("Enter URL to write (e.g., https://example.com): ")
                    if not url.startswith(('http://', 'https://')):
                        url = 'https://' + url
                        print(f"Added https:// prefix: {url}")
                    
                    if nfc.write_ndef_url(url):
                        print("✅ NDEF URL written successfully!")
                        print("📱 Now tap this card to your phone to open the URL!")
                    else:
                        print("❌ Failed to write NDEF URL")
                        
                elif choice == '5':
                    # Clear card data
                    confirm = input("Are you sure you want to clear the card? (y/N): ").strip().lower()
                    if confirm == 'y':
                        if nfc.clear_card():
                            print("✅ Card cleared successfully!")
                        else:
                            print("❌ Failed to clear card")
                    else:
                        print("Clear cancelled")
                        
                elif choice == '6':
                    # Test authentication
                    print("🔍 Testing authentication on block 4...")
                    working_key = nfc.find_working_key(4)
                    if working_key:
                        print("✅ Authentication successful!")
                    else:
                        print("❌ Authentication failed - card may be locked or use unknown keys")
                        
                input("\n↩️  Press Enter to continue...")
                
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()