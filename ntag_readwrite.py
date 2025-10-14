#!/usr/bin/env python3
"""
NTAG NFC Read/Write Tool for ACR122U
Optimized for NTAG213/215/216 cards - works with both iPhone and Android
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

class NTAGReader:
    """NTAG NFC Reader/Writer"""
    
    def __init__(self):
        self.reader = None
        self.connection = None
        self.card_type = None
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
            self.connection.connect()
            return True
        except:
            return False
            
    def wait_for_card(self):
        """Wait for an NFC card to be placed on reader"""
        print("\n⏳ Place an NTAG card on the reader...")
        while True:
            try:
                self.connection = self.reader.createConnection()
                self.connection.connect()
                print("✅ Card detected!")
                return True
            except Exception as e:
                time.sleep(0.1)
                continue
                
    def get_uid(self):
        """Get the UID of the current card"""
        GET_UID = [0xFF, 0xCA, 0x00, 0x00, 0x00]
        data, sw1, sw2 = self.connection.transmit(GET_UID)
        if sw1 == 0x90 and sw2 == 0x00:
            uid = toHexString(data)
            return uid
        return None
    
    def detect_card_type(self):
        """Detect NTAG card type"""
        # Read page 0 to get card info
        data = self.read_page(0)
        if data:
            # NTAG cards have specific patterns
            if len(data) >= 4:
                # Check for NTAG signature
                if data[0] == 0x04:  # NTAG signature
                    if len(data) >= 16:
                        # Check capacity
                        capacity = data[15]
                        if capacity == 0x12:
                            self.card_type = "NTAG213"
                            print("📱 NTAG213 card detected (180 bytes)")
                        elif capacity == 0x3E:
                            self.card_type = "NTAG215"
                            print("📱 NTAG215 card detected (504 bytes)")
                        elif capacity == 0x6D:
                            self.card_type = "NTAG216"
                            print("📱 NTAG216 card detected (924 bytes)")
                        else:
                            self.card_type = "NTAG"
                            print("📱 NTAG card detected")
                    else:
                        self.card_type = "NTAG"
                        print("📱 NTAG card detected")
                else:
                    self.card_type = "Unknown"
                    print("❓ Unknown card type")
            else:
                self.card_type = "Unknown"
                print("❓ Unknown card type")
        else:
            self.card_type = "Unknown"
            print("❓ Could not detect card type")
        
        return self.card_type
        
    def read_page(self, page):
        """Read a page from NTAG card"""
        READ_CMD = [0xFF, 0xB0, 0x00, page, 0x04]  # Read 4 bytes
        try:
            data, sw1, sw2 = self.connection.transmit(READ_CMD)
            if sw1 == 0x90 and sw2 == 0x00:
                return data
        except:
            pass
        return None
        
    def write_page(self, page, data):
        """Write data to a page"""
        if len(data) != 4:
            raise ValueError("Data must be exactly 4 bytes")
        
        WRITE_CMD = [0xFF, 0xD6, 0x00, page, 0x04] + data
        
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
        """Create an NDEF URL record for NTAG"""
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
        
        # Build NDEF record
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
        """Create a complete NDEF message for NTAG"""
        # Create the URL record
        url_record = self.create_ndef_url_record(url)
        
        # Build complete NDEF message with proper TLV structure
        message_length = len(url_record)
        
        # NDEF message structure for NTAG
        # TLV: Tag=03 (NDEF Message), Length=message_length, Value=url_record
        ndef_message = [0x03]  # NDEF Message TLV Tag
        
        # Handle length encoding (short form vs long form)
        if message_length <= 0xFE:  # Short form (1 byte)
            ndef_message.append(message_length)
        else:  # Long form (3 bytes: 0xFF + 2-byte length)
            ndef_message.extend([0xFF, (message_length >> 8) & 0xFF, message_length & 0xFF])
        
        # Add the URL record
        ndef_message.extend(url_record)
        
        # Add Terminator TLV
        ndef_message.append(0xFE)  # Terminator TLV
        
        return ndef_message
    
    def create_ndef_text_record(self, text):
        """Create an NDEF text record for NTAG"""
        # Convert text to UTF-8 bytes
        text_bytes = text.encode('utf-8')
        
        # Build payload (status byte + text)
        # Status byte: 0x00 = no language code, UTF-8 encoding
        payload = [0x00] + list(text_bytes)
        payload_length = len(payload)
        
        # Build NDEF record
        ndef_record = [
            0xD1,  # NDEF record header: MB=1, ME=1, CF=0, SR=1, IL=0, TNF=1
            0x01,  # Type Length = 1 ("T")
            payload_length,  # Payload Length
            0x54,  # Type = "T" (Text)
        ]
        
        # Add payload
        ndef_record.extend(payload)
        
        return ndef_record
    
    def create_ndef_text_message(self, text):
        """Create a complete NDEF text message for NTAG"""
        # Create the text record
        text_record = self.create_ndef_text_record(text)
        
        # Build complete NDEF message with proper TLV structure
        message_length = len(text_record)
        
        # NDEF message structure for NTAG
        # TLV: Tag=03 (NDEF Message), Length=message_length, Value=text_record
        ndef_message = [0x03]  # NDEF Message TLV Tag
        
        # Handle length encoding (short form vs long form)
        if message_length <= 0xFE:  # Short form (1 byte)
            ndef_message.append(message_length)
        else:  # Long form (3 bytes: 0xFF + 2-byte length)
            ndef_message.extend([0xFF, (message_length >> 8) & 0xFF, message_length & 0xFF])
        
        # Add the text record
        ndef_message.extend(text_record)
        
        # Add Terminator TLV
        ndef_message.append(0xFE)  # Terminator TLV
        
        return ndef_message
    
    def write_ndef_text(self, text, start_page=4):
        """Write an NDEF text record to NTAG card"""
        # Create complete NDEF message
        ndef_message = self.create_ndef_text_message(text)
        
        print(f"NDEF message length: {len(ndef_message)} bytes")
        print(f"NDEF message (hex): {' '.join(f'{b:02X}' for b in ndef_message)}")
        
        # Write in 4-byte chunks (NTAG pages are 4 bytes)
        # Pad to multiple of 4 bytes
        while len(ndef_message) % 4 != 0:
            ndef_message.append(0x00)
            
        for i in range(0, len(ndef_message), 4):
            page = start_page + (i // 4)
            data = ndef_message[i:i+4]
            print(f"Writing page {page}: {' '.join(f'{b:02X}' for b in data)}")
            
            if not self.write_page(page, data):
                print(f"Failed to write NDEF page {page}")
                return False
                
        print(f"✅ Written NDEF text record: {text}")
        return True
    
    def write_ndef_url(self, url, start_page=4):
        """Write an NDEF URL record to NTAG card"""
        # Create complete NDEF message
        ndef_message = self.create_ndef_message(url)
        
        print(f"NDEF message length: {len(ndef_message)} bytes")
        print(f"NDEF message (hex): {' '.join(f'{b:02X}' for b in ndef_message)}")
        
        # Write in 4-byte chunks (NTAG pages are 4 bytes)
        # Pad to multiple of 4 bytes
        while len(ndef_message) % 4 != 0:
            ndef_message.append(0x00)
            
        for i in range(0, len(ndef_message), 4):
            page = start_page + (i // 4)
            data = ndef_message[i:i+4]
            print(f"Writing page {page}: {' '.join(f'{b:02X}' for b in data)}")
            
            if not self.write_page(page, data):
                print(f"Failed to write NDEF page {page}")
                return False
                
        print(f"✅ Written NDEF URL record: {url}")
        return True
    
    def clear_card(self, start_page=4, num_pages=8):
        """Clear NTAG card data by writing zeros"""
        print("🧹 Clearing NTAG card data...")
        
        for i in range(num_pages):
            page = start_page + i
            if not self.write_page(page, [0x00] * 4):
                print(f"Failed to clear page {page}")
                return False
        
        print("✅ NTAG card cleared successfully")
        return True
    
    def read_text(self, start_page=4, num_pages=25):
        """Read text from NTAG card"""
        text = b''
        
        for i in range(num_pages):
            data = self.read_page(start_page + i)
            if data is None:
                print(f"Warning: Could not read page {start_page + i}")
                break
            elif isinstance(data, list):
                text += bytes(data[:4])  # NTAG has 4-byte pages
            else:
                print(f"Warning: Unexpected data type from page {start_page + i}: {type(data)}")
                break
                
        # Remove null padding
        text = text.rstrip(b'\x00')
        
        # Check if this looks like NDEF data (with TLV structure)
        if len(text) >= 3 and text[0] == 0x03:  # NDEF Message TLV Tag
            # Parse NDEF message length (can be 1 or 3 bytes)
            if text[1] <= 0xFE:  # Short form (1 byte length)
                ndef_length = text[1]
                ndef_data_start = 2
            else:  # Long form (3 bytes: 0xFF + 2-byte length)
                if len(text) >= 4:
                    ndef_length = (text[2] << 8) | text[3]
                    ndef_data_start = 4
                else:
                    return "Invalid NDEF format"
            
            if len(text) >= ndef_data_start + ndef_length:
                ndef_data = text[ndef_data_start:ndef_data_start + ndef_length]
                
                # Check if it's a URI record
                if len(ndef_data) >= 4 and ndef_data[0] == 0xD1 and ndef_data[3] == 0x55:
                    url = self.parse_ndef_url(text)
                    if url:
                        return f"NDEF URL: {url} (tap card to phone to open)"
                
                # Check if it's a text record
                if len(ndef_data) >= 4 and ndef_data[0] == 0xD1 and ndef_data[3] == 0x54:
                    json_data = self.parse_ndef_text(ndef_data)
                    if json_data:
                        return f"NDEF Text/JSON: {json_data}"
                
                return "NDEF record detected (use phone to read)"
            else:
                return "Incomplete NDEF data"
        
        try:
            return text.decode('utf-8')
        except:
            return toHexString(text)
    
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
    
    def parse_ndef_text(self, ndef_data):
        """Parse NDEF text record from raw NDEF data"""
        if len(ndef_data) < 6:
            return None
            
        # NDEF text record structure:
        # Byte 0: Flags (0xD1 = MB=1, ME=1, CF=0, SR=1, IL=0, TNF=1)
        # Byte 1: Type Length (1 for "T")
        # Byte 2: Payload Length
        # Byte 3: Type ("T" = 0x54)
        # Byte 4: Status byte (language code length + encoding)
        # Byte 5+: Language code (if any)
        # Rest: Text payload
        
        if ndef_data[0] != 0xD1 or ndef_data[3] != 0x54:
            return None
            
        type_length = ndef_data[1]
        payload_length = ndef_data[2]
        
        if len(ndef_data) < 4 + payload_length:
            return None
            
        # Skip type and status byte, get text payload
        text_start = 5  # Skip flags, type_len, payload_len, type, status
        text_data = ndef_data[text_start:text_start + payload_length - 1]
        
        try:
            return text_data.decode('utf-8')
        except:
            return None

def main():
    print("🔵 NTAG NFC Reader/Writer Tool")
    print("📱 Optimized for NTAG213/215/216 - Works with iPhone & Android")
    print("-" * 60)
    
    try:
        # Initialize reader
        ntag = NTAGReader()
        
        while True:
            print("\n📋 Menu:")
            print("1. Read card info")
            print("2. Read text from card") 
            print("3. Write text to card")
            print("4. Write NDEF URL (for phone tap-to-open)")
            print("5. Write NDEF JSON/Text (for app reading)")
            print("6. Clear card data")
            print("7. Exit")
            
            choice = input("\nSelect option (1-7): ").strip()
            
            if choice == '7':
                break
                
            if choice in ['1', '2', '3', '4', '5', '6']:
                # Wait for card
                ntag.wait_for_card()
                
                # Get card UID
                uid = ntag.get_uid()
                print(f"Card UID: {uid}")
                
                # Detect card type
                if choice == '1':
                    card_type = ntag.detect_card_type()
                
                if choice == '1':
                    # Read first few pages
                    print("\n📖 Reading card data:")
                    for page in range(0, 16):
                        data = ntag.read_page(page)
                        if data:
                            print(f"Page {page:02d}: {toHexString(data[:4])}")
                            
                elif choice == '2':
                    # Read text
                    text = ntag.read_text()
                    print(f"\n📖 Text on card: '{text}'")
                    
                elif choice == '3':
                    # Write text
                    text = input("Enter text to write: ")
                    # Convert text to bytes and write in 4-byte chunks
                    text_bytes = text.encode('utf-8')
                    while len(text_bytes) % 4 != 0:
                        text_bytes += b'\x00'
                    
                    success = True
                    for i in range(0, len(text_bytes), 4):
                        page = 4 + (i // 4)
                        data = list(text_bytes[i:i+4])
                        if not ntag.write_page(page, data):
                            print(f"Failed to write page {page}")
                            success = False
                            break
                    
                    if success:
                        print("✅ Text written successfully!")
                        # Verify by reading back
                        verify = ntag.read_text()
                        print(f"Verified: '{verify}'")
                    else:
                        print("❌ Failed to write text")
                        
                elif choice == '4':
                    # Write NDEF URL
                    url = input("Enter URL to write (e.g., https://example.com): ")
                    if not url.startswith(('http://', 'https://')):
                        url = 'https://' + url
                        print(f"Added https:// prefix: {url}")
                    
                    if ntag.write_ndef_url(url):
                        print("✅ NDEF URL written successfully!")
                        print("📱 Now tap this card to your phone to open the URL!")
                    else:
                        print("❌ Failed to write NDEF URL")
                        
                elif choice == '5':
                    # Write NDEF JSON/Text
                    json_text = input("Enter JSON/text data to write: ")
                    
                    if ntag.write_ndef_text(json_text):
                        print("✅ NDEF JSON/Text written successfully!")
                        print("📱 Your app can now read this data from the NFC card!")
                    else:
                        print("❌ Failed to write NDEF JSON/Text")
                        
                elif choice == '6':
                    # Clear card data
                    confirm = input("Are you sure you want to clear the card? (y/N): ").strip().lower()
                    if confirm == 'y':
                        if ntag.clear_card():
                            print("✅ Card cleared successfully!")
                        else:
                            print("❌ Failed to clear card")
                    else:
                        print("Clear cancelled")
                        
                input("\n↩️  Press Enter to continue...")
                
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
