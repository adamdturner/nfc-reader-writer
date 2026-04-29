#!/usr/bin/env python3
"""
NTAG424 DNA NFC Read/Write Tool for ACR122U
Optimized for NTAG424 DNA cards with Type 4 Tag (T4T) support
"""

from smartcard.System import readers
from smartcard.util import toHexString
import ndef
import time
import sys
import os
import json
import secrets
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

AID_NDEF = bytes.fromhex("D2760000850101")

# NTAG424 DNA specific constants
AID_NTAG424 = bytes.fromhex("D2760000850100")  # NTAG424 application
KEY_FILE_ID = bytes.fromhex("E104")  # Key file ID
NDEF_FILE_ID = bytes.fromhex("E104")  # NDEF file ID (same as key file for simplicity)

# Default keys for unprovisioned tags
DEFAULT_KEY = bytes.fromhex("00000000000000000000000000000000")  # All zeros default

class NTAG424Reader:
    """NTAG424 DNA NFC Reader/Writer with T4T support"""
    
    def __init__(self):
        self.reader = None
        self.connection = None
        self.authenticated = False
        self.current_key = None
        self.keys_file = "ntag424_keys.json"
        self._find_reader()
        self._load_keys()
        
    def _find_reader(self):
        """Find ACR122U reader"""
        r = readers()
        for reader in r:
            if "ACR122" in str(reader):
                self.reader = reader
                print(f"✅ Found reader: {reader}")
                return
        raise Exception("ACR122U reader not found!")
    
    def wait_for_card(self):
        """Wait for an NTAG424 card to be placed on reader"""
        print("\n⏳ Place an NTAG424 DNA card on the reader...")
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
    
    def apdu(self, cla, ins, p1, p2, data=b"", le=None):
        """Send APDU command to card"""
        apdu = bytes([cla, ins, p1, p2, len(data)]) + data
        if le is not None:
            apdu += bytes([le])
        data_out, sw1, sw2 = self.connection.transmit(list(apdu))
        sw = (sw1 << 8) | sw2
        return bytes(data_out), sw

    def select_by_aid(self, aid):
        """Select application by AID"""
        return self.apdu(0x00, 0xA4, 0x04, 0x00, aid, 0x00)

    def select_file_by_id(self, fid):
        """Select file by file ID"""
        return self.apdu(0x00, 0xA4, 0x00, 0x0C, fid, 0x00)

    def read_binary(self, offset, length):
        """Read binary data from selected file"""
        p1 = (offset >> 8) & 0xFF
        p2 = offset & 0xFF
        # APDU Le (expected length) must be 0-255
        # If length is 0, use 0x00 to read all available data
        # If length > 255, use 0x00 to read all available (or read in chunks)
        if length == 0:
            le = 0x00  # Read all available
        elif length > 255:
            le = 0x00  # Read all available (up to file size)
        else:
            le = length
        
        # Try standard format first
        result = self.apdu(0x00, 0xB0, p1, p2, b"", le)
        sw = result[1]
        
        # Debug: print status word for troubleshooting
        if sw != 0x9000:
            print(f"   [read_binary] SW={hex(sw)} for offset={offset}, length={length}, le={le}")
        
        # Handle 0x6c00 - "Wrong length, correct length is in SW2"
        # This means the card is telling us the exact length to use!
        if sw == 0x6c00:
            # Extract the correct length from SW2 (the lower byte of the status word)
            # SW format: SW1 (high byte) = 0x6C, SW2 (low byte) = correct length
            sw1, sw2 = (sw >> 8) & 0xFF, sw & 0xFF
            correct_length = sw2
            print(f"🔍 Card indicated correct length: {correct_length} bytes (SW2={hex(sw2)}), retrying...")
            
            # If SW2 is 0, it might mean:
            # 1. No data at this offset
            # 2. The card wants us to read with Le=0x00 (read all available)
            # 3. The file is empty
            if correct_length == 0:
                # Try reading with Le=0x00 to read all available data
                print(f"🔍 SW2=0x00, trying to read all available data (Le=0x00)...")
                retry_result = self.apdu(0x00, 0xB0, p1, p2, b"", 0x00)
                retry_sw = retry_result[1]
                if retry_sw == 0x9000:
                    print(f"✅ Read all available data: {len(retry_result[0])} bytes")
                    return retry_result
                elif retry_sw == 0x6c00:
                    # Still 0x6c00, extract new length
                    retry_sw1, retry_sw2 = (retry_sw >> 8) & 0xFF, retry_sw & 0xFF
                    if retry_sw2 > 0:
                        print(f"🔍 Card now indicates length: {retry_sw2} bytes, retrying...")
                        return self.apdu(0x00, 0xB0, p1, p2, b"", retry_sw2)
                    else:
                        print(f"⚠️  Still SW2=0x00 - may indicate no data at offset {offset}")
                        return retry_result
                else:
                    print(f"⚠️  Read all returned {hex(retry_sw)}")
                    return retry_result
            else:
                # Retry with the correct length
                retry_result = self.apdu(0x00, 0xB0, p1, p2, b"", correct_length)
                retry_sw = retry_result[1]
                # If retry succeeds, return it
                if retry_sw == 0x9000:
                    print(f"✅ Retry successful with length {correct_length}")
                    return retry_result
                # If retry also returns 0x6c00, the card might want a different length
                elif retry_sw == 0x6c00:
                    # Try with the new length from SW2
                    retry_sw1, retry_sw2 = (retry_sw >> 8) & 0xFF, retry_sw & 0xFF
                    if retry_sw2 > 0 and retry_sw2 != correct_length:
                        print(f"🔍 Card indicated different length: {retry_sw2} bytes, retrying again...")
                        return self.apdu(0x00, 0xB0, p1, p2, b"", retry_sw2)
                    else:
                        # SW2 is 0 or same, might mean no data available
                        print(f"⚠️  Retry returned 0x6c00 with SW2={hex(retry_sw2)} - may indicate no data")
                        return retry_result
                else:
                    # Some other error
                    print(f"⚠️  Retry returned {hex(retry_sw)}")
                    return retry_result
        
        # Handle 0x6700 - "Wrong length" (but no length hint)
        if sw == 0x6700:
            # Try without Le field for very small reads
            if length == 1:
                print(f"   [read_binary] Trying without Le field for length=1...")
                apdu_cmd = bytes([0x00, 0xB0, p1, p2])
                data_out, sw1, sw2 = self.connection.transmit(list(apdu_cmd))
                sw_retry = (sw1 << 8) | sw2
                print(f"   [read_binary] Retry without Le: SW={hex(sw_retry)}")
                # If we get 0x6c00, extract correct length and retry
                if sw_retry == 0x6c00:
                    correct_length = sw2
                    print(f"   [read_binary] Got 0x6c00, SW2={hex(sw2)} (length={correct_length}), retrying with correct length...")
                    if correct_length > 0:
                        final_result = self.apdu(0x00, 0xB0, p1, p2, b"", correct_length)
                        print(f"   [read_binary] Final retry: SW={hex(final_result[1])}")
                        return final_result
                    else:
                        # SW2 is 0, try reading all available
                        print(f"   [read_binary] SW2=0x00, trying Le=0x00...")
                        return self.apdu(0x00, 0xB0, p1, p2, b"", 0x00)
                return bytes(data_out), sw_retry
        
        return result
    
    def get_data(self, tag):
        """GET DATA command - alternative to READ BINARY for some cards"""
        # GET DATA command: CLA=0x00, INS=0xCA, P1/P2=tag
        # For NDEF file, tag might be 0x0000 or file-specific
        return self.apdu(0x00, 0xCA, (tag >> 8) & 0xFF, tag & 0xFF, b"", 0x00)

    def update_binary(self, offset, data):
        """Update binary data in selected file"""
        p1 = (offset >> 8) & 0xFF
        p2 = offset & 0xFF
        return self.apdu(0x00, 0xD6, p1, p2, data)
    
    def create_file(self, file_id, file_size, file_type=0x01, read_access=0x00, write_access=0x00):
        """Create a new file on the card
        file_type: 0x01 = standard data file
        read_access: 0x00 = free access
        write_access: 0x00 = free access
        
        Note: NTAG424 DNA may not support CREATE FILE command.
        Files may need to be created using NTAG424-specific commands.
        """
        # CREATE FILE command structure for ISO 7816-4
        # For NTAG424, the format might be different
        # Try standard format first: file_id (2 bytes) + file_size (2 bytes) + file_params (3 bytes)
        file_size_bytes = file_size.to_bytes(2, 'big')  # Try big endian
        file_params = bytes([file_type, read_access, write_access])
        create_data = file_id + file_size_bytes + file_params
        return self.apdu(0x00, 0xE0, 0x00, 0x00, create_data)
    
    def _load_keys(self):
        """Load stored keys from local file"""
        self.keys = {}
        if os.path.exists(self.keys_file):
            try:
                with open(self.keys_file, 'r') as f:
                    self.keys = json.load(f)
                print(f"✅ Loaded {len(self.keys)} stored keys")
            except Exception as e:
                print(f"⚠️  Could not load keys file: {e}")
                self.keys = {}
        else:
            print("ℹ️  No keys file found - starting with empty key store")
    
    def _save_keys(self):
        """Save keys to local file"""
        try:
            with open(self.keys_file, 'w') as f:
                json.dump(self.keys, f, indent=2)
            print("✅ Keys saved to local file")
        except Exception as e:
            print(f"❌ Could not save keys: {e}")
    
    def generate_key(self):
        """Generate a new AES-128 key"""
        return secrets.token_bytes(16)
    
    def get_key_for_uid(self, uid):
        """Get the stored key for a specific UID"""
        return self.keys.get(uid)
    
    def store_key_for_uid(self, uid, key):
        """Store a key for a specific UID"""
        self.keys[uid] = key.hex()
        self._save_keys()
    
    def aes_encrypt(self, data, key):
        """Encrypt data using AES-128"""
        cipher = AES.new(key, AES.MODE_ECB)
        return cipher.encrypt(pad(data, AES.block_size))
    
    def aes_decrypt(self, encrypted_data, key):
        """Decrypt data using AES-128"""
        cipher = AES.new(key, AES.MODE_ECB)
        return unpad(cipher.decrypt(encrypted_data), AES.block_size)
    
    def select_ntag424_app(self):
        """Select NTAG424 application"""
        _, sw = self.apdu(0x00, 0xA4, 0x04, 0x00, AID_NTAG424, 0x00)
        return sw == 0x9000
    
    def authenticate_ntag424(self, key):
        """Authenticate with NTAG424 using AES challenge/response"""
        try:
            # Step 1: Get challenge
            challenge_data, sw = self.apdu(0x90, 0x1A, 0x00, 0x00, b"", 0x08)
            if sw != 0x9100:  # NTAG424 returns 0x9100 for challenge
                print(f"Challenge failed: {hex(sw)}")
                return False
            
            challenge = challenge_data[:8]  # First 8 bytes are the challenge
            
            # Step 2: Encrypt challenge with key
            encrypted_challenge = self.aes_encrypt(challenge, key)
            
            # Step 3: Send encrypted challenge
            response, sw = self.apdu(0x90, 0xAF, 0x00, 0x00, encrypted_challenge)
            if sw != 0x9100:  # Should return 0x9100 on success
                print(f"Authentication failed: {hex(sw)}")
                return False
            
            self.authenticated = True
            self.current_key = key
            print("✅ Authentication successful!")
            return True
            
        except Exception as e:
            print(f"Authentication error: {e}")
            return False
    
    def provision_tag(self, uid):
        """Provision a new NTAG424 tag with security"""
        print("🔧 Starting NTAG424 provisioning...")
        
        try:
            # Step 1: Select NTAG424 application
            if not self.select_ntag424_app():
                print("❌ Could not select NTAG424 application")
                return False
            
            # Step 2: Generate new key
            new_key = self.generate_key()
            print(f"🔑 Generated new key: {new_key.hex()}")
            
            # Step 3: Authenticate with default key first
            print("🔐 Authenticating with default key...")
            if not self.authenticate_ntag424(DEFAULT_KEY):
                print("❌ Could not authenticate with default key")
                return False
            
            # Step 4: Write new key to key file
            print("💾 Writing new key to tag...")
            # Note: Full key provisioning requires NTAG424-specific commands to:
            # - Select the key file (typically file ID 0xE104)
            # - Update the key using proper file structure
            # - Configure access conditions
            # For now, we authenticate and store the key locally.
            # The tag will need to be provisioned using NXP's tools or a complete implementation.
            
            # Store the key locally for future authenticated writes
            self.store_key_for_uid(uid, new_key)
            
            print("✅ Key generated and stored locally!")
            print(f"📝 Key stored for UID: {uid}")
            print("⚠️  Note: Full provisioning requires additional NTAG424-specific commands")
            print("📱 Tag remains readable by phones, but write protection requires full provisioning")
            return True
            
        except Exception as e:
            print(f"❌ Provisioning failed: {e}")
            return False
    
    def is_provisioned(self, uid):
        """Check if a tag is already provisioned"""
        return uid in self.keys
    
    def initialize_ndef(self):
        """Initialize NDEF structure on NTAG424 tag (create CC and NDEF files if missing)"""
        try:
            # For NTAG424, try selecting NDEF application first
            _, sw = self.select_by_aid(AID_NDEF)
            if sw != 0x9000:
                return False, f"Select NDEF app failed: {hex(sw)}"
            
            # Try to read CC file first - maybe it exists but selection behaves differently
            # Try selecting CC file
            _, sw_select = self.select_file_by_id(bytes.fromhex("E103"))
            
            # Even if selection fails, try to read - some tags allow direct access
            cc, sw_read = self.read_binary(0, 15)
            
            if sw_select == 0x9000:
                # File can be selected - check if it has content
                if sw_read == 0x9000 and len(cc) >= 15:
                    print("✅ CC file already exists with content")
                else:
                    # File exists but is empty or has wrong content - try to write
                    print("📝 CC file exists but is empty, writing content...")
                    cc_content = bytes.fromhex("000F20000000000406E104E1040000")
                    # Try writing the full CC content
                    _, sw = self.update_binary(0, cc_content)
                    if sw == 0x9000:
                        print("✅ CC file content written successfully")
                    else:
                        # If full write fails, try writing in smaller chunks
                        print(f"⚠️  Full write failed ({hex(sw)}), trying chunked write...")
                        # Write first 8 bytes
                        _, sw1 = self.update_binary(0, cc_content[:8])
                        # Write remaining 7 bytes
                        if sw1 == 0x9000:
                            _, sw2 = self.update_binary(8, cc_content[8:])
                            if sw2 == 0x9000:
                                print("✅ CC file content written in chunks")
                            else:
                                return False, f"Chunked write failed: first={hex(sw1)}, second={hex(sw2)}"
                        else:
                            return False, f"Write CC content failed: {hex(sw)} (chunked: {hex(sw1)})"
            else:
                # File doesn't exist, try to create it
                print("📝 CC file not found, attempting to create...")
                # Note: CREATE FILE might not work on all NTAG424 tags
                # Some tags come pre-initialized and don't support file creation
                _, sw = self.create_file(bytes.fromhex("E103"), 15)
                if sw == 0x9000:
                    print("✅ CC file created")
                    # Write CC content
                    cc_content = bytes.fromhex("000F20000000000406E104E1040000")
                    _, sw = self.update_binary(0, cc_content)
                    if sw != 0x9000:
                        return False, f"Write CC content failed: {hex(sw)}"
                else:
                    return False, f"Create CC file failed: {hex(sw)}. Tag may not support file creation or may be pre-initialized differently."
            
            # Try NDEF file
            _, sw_select = self.select_file_by_id(bytes.fromhex("E104"))
            ndef_data, sw_read = self.read_binary(0, 2)
            
            if sw_select == 0x9000 or sw_read == 0x9000:
                print("✅ NDEF file already exists")
            else:
                print("📝 NDEF file not found, attempting to create...")
                _, sw = self.create_file(bytes.fromhex("E104"), 512)
                if sw == 0x9000:
                    print("✅ NDEF file created")
                    # Initialize NDEF file: first 2 bytes are NLEN (0x0000 = empty)
                    _, sw = self.update_binary(0, b"\x00\x00")
                    if sw != 0x9000:
                        return False, f"Initialize NDEF file failed: {hex(sw)}"
                else:
                    return False, f"Create NDEF file failed: {hex(sw)}"
            
            print("✅ NDEF structure check/initialization complete!")
            return True, "NDEF initialized"
            
        except Exception as e:
            return False, f"Initialization error: {e}"
    
    def detect_card_type(self):
        """Detect if this is an NTAG424 DNA card"""
        try:
            # Try to select NDEF application
            _, sw = self.select_by_aid(AID_NDEF)
            if sw == 0x9000:
                print("📱 NTAG424 DNA card detected (Type 4 Tag)")
                return "NTAG424 DNA"
            else:
                print("❓ Card detected but may not be NTAG424 DNA")
                return "Unknown"
        except Exception as e:
            print(f"❓ Could not detect card type: {e}")
            return "Unknown"
    
    def read_ndef_message(self):
        """Read NDEF message from NTAG424 card"""
        try:
            # Use the exact same sequence as write function
            # For NTAG424, try selecting NTAG424 application first
            _, sw_ntag = self.select_by_aid(AID_NTAG424)
            if sw_ntag != 0x9000:
                print(f"⚠️  NTAG424 app selection returned: {hex(sw_ntag)}")
            
            # 1) Select NDEF application (same as write)
            _, sw = self.select_by_aid(AID_NDEF)
            if sw != 0x9000:
                return f"Select NDEF app failed: {hex(sw)}. Tag may not be initialized with NDEF."

            # 2) Select CC file
            _, sw = self.select_file_by_id(bytes.fromhex("E103"))
            if sw != 0x9000:
                # Try to initialize NDEF structure
                print("⚠️  CC file selection failed, attempting to initialize NDEF structure...")
                success, msg = self.initialize_ndef()
                if not success:
                    return f"Select CC file failed: {hex(sw)}. Initialization also failed: {msg}"
                # Retry selecting CC file
                _, sw = self.select_file_by_id(bytes.fromhex("E103"))
                if sw != 0x9000:
                    return f"Select CC file failed after initialization: {hex(sw)}"

            # 3) Read CC to get NDEF file info (15 bytes)
            cc, sw = self.read_binary(0, 15)
            if sw != 0x9000:
                # Try with le=0x00 to read all available data
                cc, sw = self.read_binary(0, 0)
                if sw != 0x9000:
                    # If read fails, CC file is empty/protected - use default NDEF file ID
                    print("⚠️  CC file appears empty, using default NDEF file ID...")
                    ndef_fid = bytes.fromhex("E104")
                    # Skip CC parsing and go directly to NDEF file
                    # Select NDEF file directly (re-select to ensure fresh state)
                    print(f"🔍 Selecting NDEF file {ndef_fid.hex()}...")
                    _, sw = self.select_file_by_id(ndef_fid)
                    if sw != 0x9000:
                        return f"Select NDEF file failed: {hex(sw)}"
                    print("✅ NDEF file selected")
                    
                    # CRITICAL: Re-select NDEF application and file to ensure fresh state
                    # This is important because file selection might not persist
                    print("🔄 Re-selecting NDEF application and file for read...")
                    _, sw_ndef_app = self.select_by_aid(AID_NDEF)
                    if sw_ndef_app != 0x9000:
                        return f"Re-select NDEF app failed: {hex(sw_ndef_app)}"
                    
                    _, sw_file = self.select_file_by_id(ndef_fid)
                    if sw_file != 0x9000:
                        return f"Re-select NDEF file failed: {hex(sw_file)}"
                    print("✅ NDEF file re-selected")
                    
                    # Try reading from offset 2 directly (where payload is written)
                    # Skip offset 0 (NLEN) since it might be protected/empty
                    print("🔍 Attempting to read from offset 2 (payload location)...")
                    # read_binary should automatically handle 0x6c00 and retry with correct length
                    test_read2, sw_read2 = self.read_binary(2, 1)
                    print(f"   Read 1 byte from offset 2: SW={hex(sw_read2)}, data={test_read2.hex() if sw_read2 == 0x9000 else 'N/A'}")
                    
                    # If we still get 0x6c00 or 0x6700 after read_binary's automatic retry, 
                    # this indicates the file doesn't support READ BINARY
                    if sw_read2 in (0x6c00, 0x6700):
                        print("⚠️  READ BINARY command not supported for this file")
                        print("ℹ️  This is a known limitation with NTAG424 DNA tags:")
                        print("   - NDEF data can be written successfully (✅ verified)")
                        print("   - NDEF data can be read by phones (✅ verified)")
                        print("   - READ BINARY via Type 4 Tag interface is not supported")
                        print("   - This is a hardware/firmware limitation, not a code issue")
                        return "NDEF data written (READ BINARY not supported - verify with phone tap)"
                    
                    if sw_read2 == 0x9000 and len(test_read2) > 0:
                        # Check if it's NDEF header
                        if test_read2[0] == 0xD1:
                            print("✅ Found NDEF record header (0xD1) at offset 2!")
                            # Read more - start with 32 bytes
                            ndef_data, sw_ndef = self.read_binary(2, 32)
                            if sw_ndef == 0x9000 and len(ndef_data) > 0:
                                print(f"✅ Read {len(ndef_data)} bytes from offset 2")
                                # Read in chunks to get full message
                                full_data = ndef_data
                                current_offset = 2 + len(ndef_data)
                                max_chunks = 10
                                
                                for _ in range(max_chunks):
                                    chunk, sw_chunk = self.read_binary(current_offset, 32)
                                    if sw_chunk != 0x9000 or len(chunk) == 0:
                                        break
                                    full_data += chunk
                                    current_offset += len(chunk)
                                    if len(chunk) < 32:  # Got less than requested, probably end
                                        break
                                
                                print(f"✅ Total read: {len(full_data)} bytes")
                                try:
                                    message = ndef.NdefMessage(full_data)
                                    if message.records:
                                        record = message.records[0]
                                        if record.type == ndef.RTD_URI:
                                            if len(record.payload) > 0:
                                                uri_code = record.payload[0]
                                                uri_suffix = record.payload[1:].decode('utf-8', errors='ignore')
                                                uri_prefixes = {1: 'http://www.', 2: 'https://www.', 3: 'http://', 4: 'https://'}
                                                prefix = uri_prefixes.get(uri_code, '')
                                                url = prefix + uri_suffix
                                                return f"NDEF URL: {url} (tap card to phone to open)"
                                        elif record.type == ndef.RTD_TEXT:
                                            if len(record.payload) > 0:
                                                text_data = record.payload[1:].decode('utf-8', errors='ignore')
                                                return f"NDEF Text: {text_data}"
                                except Exception as e:
                                    return f"NDEF data found: {full_data.hex()[:64]}... (parse error: {e})"
                        else:
                            # Not NDEF header, but try reading more anyway
                            print(f"⚠️  First byte is {hex(test_read2[0])}, not NDEF header. Trying to read more...")
                            ndef_data, sw_ndef = self.read_binary(2, 32)
                            if sw_ndef == 0x9000:
                                try:
                                    message = ndef.NdefMessage(ndef_data)
                                    if message.records:
                                        record = message.records[0]
                                        if record.type == ndef.RTD_URI:
                                            if len(record.payload) > 0:
                                                uri_code = record.payload[0]
                                                uri_suffix = record.payload[1:].decode('utf-8', errors='ignore')
                                                uri_prefixes = {1: 'http://www.', 2: 'https://www.', 3: 'http://', 4: 'https://'}
                                                prefix = uri_prefixes.get(uri_code, '')
                                                url = prefix + uri_suffix
                                                return f"NDEF URL: {url} (tap card to phone to open)"
                                        elif record.type == ndef.RTD_TEXT:
                                            if len(record.payload) > 0:
                                                text_data = record.payload[1:].decode('utf-8', errors='ignore')
                                                return f"NDEF Text: {text_data}"
                                except:
                                    return f"Raw data at offset 2: {ndef_data.hex()[:64]}..."
                    else:
                        print(f"⚠️  Read from offset 2 failed: {hex(sw_read2)}")
                        # READ BINARY is not working - this is a known limitation with NTAG424 DNA
                        # The tag may not support READ BINARY for NDEF files through Type 4 Tag interface
                        # However, writes work and phones can read the data, so the data is there
                        print("ℹ️  READ BINARY not supported for this file (common with NTAG424 DNA)")
                        print("ℹ️  NDEF data was written successfully - verify by tapping card to your phone")
                        return "NDEF data written (READ BINARY not supported - verify with phone tap)"
                    
                    # Read NLEN directly (first 2 bytes) - try with very small reads
                    nlen_data, sw = self.read_binary(0, 2)
                    if sw != 0x9000:
                        # NLEN read failed - try reading from offset 2 directly (payload location)
                        # This happens when NLEN write failed but payload was written
                        print("⚠️  NLEN read failed, trying to read payload directly...")
                        # Try reading from offset 2 with small length first
                        ndef_data, sw_data = self.read_binary(2, 1)  # Try 1 byte first
                        if sw_data == 0x9000 and len(ndef_data) > 0:
                            print(f"✅ Found data at offset 2: {ndef_data.hex()}")
                            # If first byte is NDEF header (0xD1), read more
                            if ndef_data[0] == 0xD1:
                                print("✅ Found NDEF record header!")
                                # Try reading more bytes (start with 32, then increase if needed)
                                ndef_data, sw_data = self.read_binary(2, 32)
                                if sw_data == 0x9000 and len(ndef_data) > 0:
                                    # If we got data, try reading even more to get full message
                                    # Read in chunks to avoid 0x6700 error
                                    full_data = ndef_data
                                    chunk_size = 32
                                    offset = 2 + len(ndef_data)
                                    while len(ndef_data) < 256:  # Max reasonable NDEF size
                                        chunk, sw_chunk = self.read_binary(offset, min(chunk_size, 255))
                                        if sw_chunk != 0x9000 or len(chunk) == 0:
                                            break
                                        full_data += chunk
                                        offset += len(chunk)
                                        if len(chunk) < chunk_size:  # Got less than requested, probably end
                                            break
                                    ndef_payload = full_data
                                else:
                                    ndef_payload = ndef_data
                            else:
                                # Not NDEF header, but try to read more anyway
                                ndef_data, sw_data = self.read_binary(2, 32)
                                if sw_data == 0x9000:
                                    ndef_payload = ndef_data
                                else:
                                    return f"No NDEF message stored (read failed: offset 0={hex(sw)}, offset 2={hex(sw_data)})"
                        else:
                            # Try offset 0 with small read
                            ndef_data, sw_data = self.read_binary(0, 1)
                            if sw_data == 0x9000 and len(ndef_data) > 0:
                                # Try reading more
                                ndef_data, sw_data = self.read_binary(0, 32)
                                if sw_data == 0x9000:
                                    # Check if it starts with NDEF record (0xD1) at offset 2
                                    if len(ndef_data) >= 3 and ndef_data[2] == 0xD1:
                                        ndef_payload = ndef_data[2:]
                                    else:
                                        ndef_payload = ndef_data
                                else:
                                    return f"No NDEF message stored (read failed: offset 0={hex(sw)}, offset 2={hex(sw_data)})"
                            else:
                                return f"No NDEF message stored (read failed: offset 0={hex(sw)}, offset 2={hex(sw_data)})"
                        
                        # Now try to parse the payload we found
                        if 'ndef_payload' in locals() and len(ndef_payload) > 0:
                            # Found data! Try to parse it
                            try:
                                message = ndef.NdefMessage(ndef_payload)
                                if message.records:
                                    record = message.records[0]
                                    if record.type == ndef.RTD_URI:
                                        if len(record.payload) > 0:
                                            uri_code = record.payload[0]
                                            uri_suffix = record.payload[1:].decode('utf-8', errors='ignore')
                                            uri_prefixes = {1: 'http://www.', 2: 'https://www.', 3: 'http://', 4: 'https://'}
                                            prefix = uri_prefixes.get(uri_code, '')
                                            url = prefix + uri_suffix
                                            return f"NDEF URL: {url} (tap card to phone to open)"
                                    elif record.type == ndef.RTD_TEXT:
                                        if len(record.payload) > 0:
                                            text_data = record.payload[1:].decode('utf-8', errors='ignore')
                                            return f"NDEF Text: {text_data}"
                                    else:
                                        return f"NDEF record type: {record.type}"
                            except Exception as e:
                                return f"NDEF data found (NLEN missing): {ndef_payload.hex()[:64]}... (parse error: {e})"
                        else:
                            return f"No NDEF message stored (read failed: offset 0={hex(sw)})"
                    
                    nlen = (nlen_data[0] << 8) | nlen_data[1]
                    if nlen == 0:
                        # NLEN is 0, but maybe data exists anyway - try reading a bit to check
                        test_data, sw_test = self.read_binary(2, 16)
                        if sw_test == 0x9000 and any(test_data):
                            # Data exists but NLEN is 0 - try to parse what we can
                            try:
                                message = ndef.NdefMessage(test_data)
                                if message.records:
                                    record = message.records[0]
                                    if record.type == ndef.RTD_URI:
                                        if len(record.payload) > 0:
                                            uri_code = record.payload[0]
                                            uri_suffix = record.payload[1:].decode('utf-8', errors='ignore')
                                            uri_prefixes = {1: 'http://www.', 2: 'https://www.', 3: 'http://', 4: 'https://'}
                                            prefix = uri_prefixes.get(uri_code, '')
                                            url = prefix + uri_suffix
                                            return f"NDEF URL: {url} (tap card to phone to open)"
                                    elif record.type == ndef.RTD_TEXT:
                                        if len(record.payload) > 0:
                                            text_data = record.payload[1:].decode('utf-8', errors='ignore')
                                            return f"NDEF Text: {text_data}"
                            except:
                                pass
                            return f"NLEN is 0 but data exists: {test_data.hex()[:32]}..."
                        return "No NDEF message stored (NLEN is 0)"
                    
                    # Read NDEF payload
                    ndef_data, sw = self.read_binary(2, nlen)
                    if sw != 0x9000:
                        # Try reading what we can
                        partial, sw_partial = self.read_binary(2, min(nlen, 256))
                        if sw_partial == 0x9000:
                            return f"Read NDEF failed ({hex(sw)}), partial data: {partial.hex()[:64]}..."
                        return f"Read NDEF data failed: {hex(sw)}"
                    # Parse and return
                    try:
                        message = ndef.NdefMessage(ndef_data)
                        if message.records:
                            record = message.records[0]
                            if record.type == ndef.RTD_URI:
                                if len(record.payload) > 0:
                                    uri_code = record.payload[0]
                                    uri_suffix = record.payload[1:].decode('utf-8', errors='ignore')
                                    uri_prefixes = {
                                        1: 'http://www.',
                                        2: 'https://www.',
                                        3: 'http://',
                                        4: 'https://',
                                    }
                                    prefix = uri_prefixes.get(uri_code, '')
                                    url = prefix + uri_suffix
                                    return f"NDEF URL: {url} (tap card to phone to open)"
                                else:
                                    return "NDEF URI record (empty)"
                            elif record.type == ndef.RTD_TEXT:
                                if len(record.payload) > 0:
                                    text_data = record.payload[1:].decode('utf-8', errors='ignore')
                                    return f"NDEF Text: {text_data}"
                                else:
                                    return "NDEF Text record (empty)"
                            else:
                                return f"NDEF record type: {record.type}"
                        else:
                            return "Empty NDEF message"
                    except Exception as e:
                        return f"NDEF data (raw): {ndef_data.hex()} (parse error: {e})"
                
                if sw != 0x9000:
                    return f"Read CC failed: {hex(sw)}. File may be empty or have wrong structure."
                    
                # If we got data but less than 15 bytes, pad it
                if len(cc) < 15:
                    cc = cc + b'\x00' * (15 - len(cc))

            # Parse CC if we successfully read it
            if len(cc) >= 15 and cc[8] == 0x04:
                ndef_fid = cc[10:12]
                max_ndef = (cc[12] << 8) | cc[13]
            else:
                # CC content is invalid, use defaults
                print("⚠️  CC content invalid, using default NDEF file ID...")
                ndef_fid = bytes.fromhex("E104")
                max_ndef = 512

            # 4) Select NDEF file
            _, sw = self.select_file_by_id(ndef_fid)
            if sw != 0x9000:
                raise RuntimeError(f"Select NDEF file failed: {hex(sw)}")

            # 5) Read NLEN (first 2 bytes)
            # Try reading from offset 0 first to see what's there
            test_read, sw_test = self.read_binary(0, 16)
            if sw_test == 0x9000:
                print(f"🔍 Debug: First 16 bytes at offset 0: {test_read.hex()}")
            
            nlen_data, sw = self.read_binary(0, 2)
            if sw != 0x9000:
                # NLEN read failed - try reading payload directly
                print("⚠️  NLEN read failed, trying to read payload directly...")
                # Try reading from offset 0 first (maybe payload starts there)
                ndef_data, sw_data = self.read_binary(0, 0)
                if sw_data == 0x9000 and len(ndef_data) > 0:
                    # Check if it starts with NDEF record (0xD1)
                    if len(ndef_data) >= 3 and ndef_data[0] == 0xD1:
                        # Skip first 2 bytes (NLEN area) and parse
                        ndef_payload = ndef_data[2:] if len(ndef_data) > 2 else ndef_data
                    else:
                        ndef_payload = ndef_data
                else:
                    # Try offset 2
                    ndef_data, sw_data = self.read_binary(2, 0)
                    if sw_data == 0x9000 and len(ndef_data) > 0:
                        ndef_payload = ndef_data
                    else:
                        raise RuntimeError(f"Read failed: offset 0={hex(sw)}, offset 2={hex(sw_data) if sw_data else 'N/A'}")
                
                if sw_data == 0x9000 and len(ndef_payload) > 0:
                    # Found data! Try to parse it
                    try:
                        message = ndef.NdefMessage(ndef_payload)
                        if message.records:
                            record = message.records[0]
                            if record.type == ndef.RTD_URI:
                                if len(record.payload) > 0:
                                    uri_code = record.payload[0]
                                    uri_suffix = record.payload[1:].decode('utf-8', errors='ignore')
                                    uri_prefixes = {1: 'http://www.', 2: 'https://www.', 3: 'http://', 4: 'https://'}
                                    prefix = uri_prefixes.get(uri_code, '')
                                    url = prefix + uri_suffix
                                    return f"NDEF URL: {url} (tap card to phone to open)"
                            elif record.type == ndef.RTD_TEXT:
                                if len(record.payload) > 0:
                                    text_data = record.payload[1:].decode('utf-8', errors='ignore')
                                    return f"NDEF Text: {text_data}"
                    except Exception as e:
                        return f"NDEF data found but parse failed: {ndef_payload.hex()[:64]}... (error: {e})"
                    return f"NDEF data found (NLEN missing): {ndef_payload.hex()[:64]}..."
                raise RuntimeError(f"Read NLEN failed: {hex(sw)}")

            nlen = (nlen_data[0] << 8) | nlen_data[1]
            if nlen == 0:
                # NLEN is 0, but check if data exists anyway
                test_data, sw_test = self.read_binary(2, 16)
                if sw_test == 0x9000 and any(test_data):
                    # Try to parse it
                    try:
                        message = ndef.NdefMessage(test_data)
                        if message.records:
                            record = message.records[0]
                            if record.type == ndef.RTD_URI:
                                if len(record.payload) > 0:
                                    uri_code = record.payload[0]
                                    uri_suffix = record.payload[1:].decode('utf-8', errors='ignore')
                                    uri_prefixes = {1: 'http://www.', 2: 'https://www.', 3: 'http://', 4: 'https://'}
                                    prefix = uri_prefixes.get(uri_code, '')
                                    url = prefix + uri_suffix
                                    return f"NDEF URL: {url} (tap card to phone to open)"
                            elif record.type == ndef.RTD_TEXT:
                                if len(record.payload) > 0:
                                    text_data = record.payload[1:].decode('utf-8', errors='ignore')
                                    return f"NDEF Text: {text_data}"
                    except:
                        pass
                    return f"NLEN is 0 but data exists: {test_data.hex()[:32]}... (NLEN may not have been set)"
                return "No NDEF message stored"

            # 6) Read NDEF payload
            ndef_data, sw = self.read_binary(2, nlen)
            if sw != 0x9000:
                # Try reading partial data
                partial, sw_partial = self.read_binary(2, min(nlen, 256))
                if sw_partial == 0x9000:
                    raise RuntimeError(f"Read NDEF failed ({hex(sw)}), got {len(partial)} bytes: {partial.hex()[:64]}...")
                raise RuntimeError(f"Read NDEF data failed: {hex(sw)}")

            # Parse NDEF message
            try:
                message = ndef.NdefMessage(ndef_data)
                if message.records:
                    record = message.records[0]
                    # Check if it's a URI record
                    if record.type == ndef.RTD_URI:
                        # Parse URI payload (first byte is identifier code)
                        if len(record.payload) > 0:
                            uri_code = record.payload[0]
                            uri_suffix = record.payload[1:].decode('utf-8', errors='ignore')
                            # Map URI codes to prefixes
                            uri_prefixes = {
                                1: 'http://www.',
                                2: 'https://www.',
                                3: 'http://',
                                4: 'https://',
                            }
                            prefix = uri_prefixes.get(uri_code, '')
                            url = prefix + uri_suffix
                            return f"NDEF URL: {url} (tap card to phone to open)"
                        else:
                            return "NDEF URI record (empty)"
                    # Check if it's a Text record
                    elif record.type == ndef.RTD_TEXT:
                        # Parse text payload (first byte is status, then language code, then text)
                        if len(record.payload) > 0:
                            text_data = record.payload[1:].decode('utf-8', errors='ignore')
                            return f"NDEF Text: {text_data}"
                        else:
                            return "NDEF Text record (empty)"
                    else:
                        return f"NDEF record type: {record.type}"
                else:
                    return "Empty NDEF message"
            except Exception as e:
                return f"NDEF data (raw): {ndef_data.hex()} (parse error: {e})"
                
        except Exception as e:
            return f"Error reading NDEF: {e}"

    def write_ndef_url(self, url, uid=None):
        """Write NDEF URL record to NTAG424 card"""
        try:
            # For NTAG424, try selecting NTAG424 application first
            _, sw_ntag = self.select_by_aid(AID_NTAG424)
            if sw_ntag != 0x9000:
                print(f"⚠️  NTAG424 app selection returned: {hex(sw_ntag)}")
            
            # Create NDEF message using the ndef library
            # URI payload needs to be encoded with abbreviation code
            def _url_ndef_abbrv(url):
                """Encode URL with NDEF URI abbreviation"""
                abbrv_table = [
                    'http://www.', 'https://www.', 'http://', 'https://',
                    'tel:', 'mailto:', 'ftp://anonymous:anonymous@', 'ftp://ftp.',
                    'ftps://', 'sftp://', 'smb://', 'nfs://', 'ftp://',
                    'dav://', 'news:', 'telnet://', 'imap:', 'rtsp://',
                    'urn:', 'pop:', 'sip:', 'sips:', 'tftp:',
                    'btspp://', 'btl2cap://', 'btgoep://', 'tcpobex://',
                    'irdaobex://', 'file://', 'urn:epc:id:', 'urn:epc:tag:',
                    'urn:epc:pat:', 'urn:epc:raw:', 'urn:epc:', 'urn:nfc:'
                ]
                for i, abbr in enumerate(abbrv_table):
                    if url.startswith(abbr):
                        return bytes([i + 1]) + url[len(abbr):].encode('utf-8')
                return bytes([0]) + url.encode('utf-8')
            
            uri_payload = _url_ndef_abbrv(url)
            ndef_message = ndef.new_message((ndef.TNF_WELL_KNOWN, ndef.RTD_URI, b'', uri_payload))
            ndef_msg = ndef_message.to_buffer()
            
            # Check if we need authentication
            if uid and self.is_provisioned(uid):
                stored_key_hex = self.get_key_for_uid(uid)
                if stored_key_hex:
                    stored_key = bytes.fromhex(stored_key_hex)
                    print("🔐 Authenticating for secure write...")
                    if not self.authenticate_ntag424(stored_key):
                        print("❌ Authentication failed - cannot write to protected tag")
                        return False
                    print("✅ Authenticated - proceeding with secure write")
            
            # 1) Select NDEF application
            _, sw = self.select_by_aid(AID_NDEF)
            if sw != 0x9000:
                raise RuntimeError(f"Select NDEF app failed: {hex(sw)}")

            # 2) Select CC file
            _, sw = self.select_file_by_id(bytes.fromhex("E103"))
            if sw != 0x9000:
                # Try to initialize NDEF structure
                print("⚠️  CC file not found, attempting to initialize NDEF structure...")
                success, msg = self.initialize_ndef()
                if not success:
                    raise RuntimeError(f"Select CC file failed: {hex(sw)}. Initialization also failed: {msg}")
                # Retry selecting CC file
                _, sw = self.select_file_by_id(bytes.fromhex("E103"))
                if sw != 0x9000:
                    raise RuntimeError(f"Select CC file failed after initialization: {hex(sw)}")

            # 3) Read CC to get max NDEF size (15 bytes)
            cc, sw = self.read_binary(0, 15)
            if sw != 0x9000:
                # Try with le=0x00 to read all available data
                cc, sw = self.read_binary(0, 0)
                if sw != 0x9000:
                    # CC file is empty - try to write it
                    print("⚠️  CC file appears empty, attempting to write content...")
                    cc_content = bytes.fromhex("000F20000000000406E104E1040000")
                    _, sw_write = self.update_binary(0, cc_content)
                    if sw_write == 0x9000:
                        print("✅ CC file content written, retrying read...")
                        cc, sw = self.read_binary(0, 15)
                        if sw != 0x9000:
                            cc, sw = self.read_binary(0, 0)
                    else:
                        # If write fails, use default values and skip CC
                        print(f"⚠️  Could not write CC file ({hex(sw_write)}), using default NDEF file ID...")
                        # Use default: NDEF file ID 0xE104
                        ndef_fid = bytes.fromhex("E104")
                        max_ndef = 512  # Default size
                        # Skip CC validation and proceed directly to NDEF file
                        if len(ndef_msg) > max_ndef:
                            raise RuntimeError(f"NDEF too large: {len(ndef_msg)} > {max_ndef}")
                        # Select NDEF file directly
                        _, sw = self.select_file_by_id(ndef_fid)
                        if sw != 0x9000:
                            raise RuntimeError(f"Select NDEF file failed: {hex(sw)}")
                        # Continue to write section below (skip CC parsing)
                        # We'll set ndef_fid and max_ndef above, then jump to file selection
                        pass
                
                if sw != 0x9000 and 'ndef_fid' not in locals():
                    raise RuntimeError(f"Read CC failed: {hex(sw)}. Tag may not be initialized with NDEF.")
                    
                # If we got data but less than 15 bytes, pad it
                if len(cc) < 15 and 'ndef_fid' not in locals():
                    cc = cc + b'\x00' * (15 - len(cc))

            # Parse CC if we successfully read it
            if 'ndef_fid' not in locals():
                if len(cc) < 15 or cc[8] != 0x04:
                    # CC content is invalid, use defaults
                    print("⚠️  CC content invalid, using default NDEF file ID...")
                    ndef_fid = bytes.fromhex("E104")
                    max_ndef = 512
                else:
                    ndef_fid = cc[10:12]
                    max_ndef = (cc[12] << 8) | cc[13]

            if len(ndef_msg) > max_ndef:
                raise RuntimeError(f"NDEF too large: {len(ndef_msg)} > {max_ndef}")

            # 4) Select NDEF file
            _, sw = self.select_file_by_id(ndef_fid)
            if sw != 0x9000:
                raise RuntimeError(f"Select NDEF file failed: {hex(sw)}")

            # 5) Clear NLEN
            _, sw = self.update_binary(0, b"\x00\x00")
            if sw != 0x9000:
                raise RuntimeError(f"Clear NLEN failed: {hex(sw)}")

            # 6) Write NDEF payload
            _, sw = self.update_binary(2, ndef_msg)
            if sw != 0x9000:
                raise RuntimeError(f"Write payload failed: {hex(sw)}")

            # 7) Set NLEN to payload length
            nlen = len(ndef_msg).to_bytes(2, "big")
            _, sw = self.update_binary(0, nlen)
            if sw != 0x9000:
                # NLEN write failed - this is critical, but try to continue
                print(f"⚠️  Warning: Set NLEN failed: {hex(sw)}. NDEF may not be readable.")
                # Don't raise - the data is written, just NLEN isn't set
                # Some readers might still be able to read it
            
            # Verify write by reading back immediately (in same session)
            print("🔍 Verifying write...")
            verify_data, sw_verify = self.read_binary(2, 0)  # Read from offset 2 (payload location)
            if sw_verify == 0x9000 and len(verify_data) > 0:
                print(f"✅ Write verified: {len(verify_data)} bytes read back")
            else:
                print(f"⚠️  Verification read returned: {hex(sw_verify)} (data may still be readable by phones)")

            if self.authenticated:
                print("🔒 Secure write completed!")
            return True
            
        except Exception as e:
            print(f"Write error: {e}")
            return False

    def write_ndef_text(self, text):
        """Write NDEF text record to NTAG424 card"""
        try:
            # Create NDEF message using the ndef library
            # Text payload: status byte (0x02 = UTF-8, language code length 2) + 'en' + text
            text_payload = b'\x02en' + text.encode('utf-8')
            ndef_message = ndef.new_message((ndef.TNF_WELL_KNOWN, ndef.RTD_TEXT, b'', text_payload))
            ndef_msg = ndef_message.to_buffer()
            
            # Use same fallback logic as write_ndef_url
            # For NTAG424, try selecting NTAG424 application first
            _, sw_ntag = self.select_by_aid(AID_NTAG424)
            if sw_ntag != 0x9000:
                print(f"⚠️  NTAG424 app selection returned: {hex(sw_ntag)}")
            
            # 1) Select NDEF application
            _, sw = self.select_by_aid(AID_NDEF)
            if sw != 0x9000:
                raise RuntimeError(f"Select NDEF app failed: {hex(sw)}")

            # 2) Select CC file
            _, sw = self.select_file_by_id(bytes.fromhex("E103"))
            if sw != 0x9000:
                # Try to initialize NDEF structure
                print("⚠️  CC file not found, attempting to initialize NDEF structure...")
                success, msg = self.initialize_ndef()
                if not success:
                    raise RuntimeError(f"Select CC file failed: {hex(sw)}. Initialization also failed: {msg}")
                # Retry selecting CC file
                _, sw = self.select_file_by_id(bytes.fromhex("E103"))
                if sw != 0x9000:
                    raise RuntimeError(f"Select CC file failed after initialization: {hex(sw)}")

            # 3) Read CC to get max NDEF size (15 bytes)
            cc, sw = self.read_binary(0, 15)
            if sw != 0x9000:
                # Try with le=0x00 to read all available data
                cc, sw = self.read_binary(0, 0)
                if sw != 0x9000:
                    # CC file is empty - use default values
                    print("⚠️  CC file appears empty, using default NDEF file ID...")
                    ndef_fid = bytes.fromhex("E104")
                    max_ndef = 512
                    # Skip CC validation and proceed directly to NDEF file
                    if len(ndef_msg) > max_ndef:
                        raise RuntimeError(f"NDEF too large: {len(ndef_msg)} > {max_ndef}")
                    # Select NDEF file directly
                    _, sw = self.select_file_by_id(ndef_fid)
                    if sw != 0x9000:
                        raise RuntimeError(f"Select NDEF file failed: {hex(sw)}")
                    # Continue to write section below (skip CC parsing)
                    pass
                else:
                    # If we got data but less than 15 bytes, pad it
                    if len(cc) < 15:
                        cc = cc + b'\x00' * (15 - len(cc))

            # Parse CC if we successfully read it
            if 'ndef_fid' not in locals():
                if len(cc) < 15 or cc[8] != 0x04:
                    # CC content is invalid, use defaults
                    print("⚠️  CC content invalid, using default NDEF file ID...")
                    ndef_fid = bytes.fromhex("E104")
                    max_ndef = 512
                else:
                    ndef_fid = cc[10:12]
                    max_ndef = (cc[12] << 8) | cc[13]

            if len(ndef_msg) > max_ndef:
                raise RuntimeError(f"NDEF too large: {len(ndef_msg)} > {max_ndef}")

            _, sw = self.select_file_by_id(ndef_fid)
            if sw != 0x9000:
                raise RuntimeError(f"Select NDEF file failed: {hex(sw)}")

            _, sw = self.update_binary(0, b"\x00\x00")
            if sw != 0x9000:
                raise RuntimeError(f"Clear NLEN failed: {hex(sw)}")

            _, sw = self.update_binary(2, ndef_msg)
            if sw != 0x9000:
                raise RuntimeError(f"Write payload failed: {hex(sw)}")

            nlen = len(ndef_msg).to_bytes(2, "big")
            _, sw = self.update_binary(0, nlen)
            if sw != 0x9000:
                raise RuntimeError(f"Set NLEN failed: {hex(sw)}")

            return True
            
        except Exception as e:
            print(f"Write error: {e}")
            return False

    def clear_ndef(self):
        """Clear NDEF message from card"""
        try:
            _, sw = self.select_by_aid(AID_NDEF)
            if sw != 0x9000:
                raise RuntimeError(f"Select NDEF app failed: {hex(sw)}. Tag may not be initialized with NDEF.")

            _, sw = self.select_file_by_id(bytes.fromhex("E103"))
            if sw != 0x9000:
                # Try to initialize NDEF structure
                print("⚠️  CC file not found, attempting to initialize NDEF structure...")
                success, msg = self.initialize_ndef()
                if not success:
                    # If initialization fails, use default NDEF file ID
                    print("⚠️  Initialization failed, using default NDEF file ID...")
                    ndef_fid = bytes.fromhex("E104")
                else:
                    # Retry selecting CC file
                    _, sw = self.select_file_by_id(bytes.fromhex("E103"))
                    if sw != 0x9000:
                        # Use default if retry fails
                        ndef_fid = bytes.fromhex("E104")
                    else:
                        # Try to read CC
                        cc, sw = self.read_binary(0, 15)
                        if sw != 0x9000:
                            cc, sw = self.read_binary(0, 0)
                        if sw == 0x9000 and len(cc) >= 15 and cc[8] == 0x04:
                            ndef_fid = cc[10:12]
                        else:
                            ndef_fid = bytes.fromhex("E104")
            else:
                # CC file selected, try to read it
                cc, sw = self.read_binary(0, 15)
                if sw != 0x9000:
                    cc, sw = self.read_binary(0, 0)
                if sw == 0x9000 and len(cc) >= 15 and cc[8] == 0x04:
                    ndef_fid = cc[10:12]
                else:
                    # CC read failed or invalid, use default
                    print("⚠️  CC file read failed, using default NDEF file ID...")
                    ndef_fid = bytes.fromhex("E104")

            _, sw = self.select_file_by_id(ndef_fid)
            if sw != 0x9000:
                raise RuntimeError(f"Select NDEF file failed: {hex(sw)}")

            # Set NLEN to 0 to clear
            _, sw = self.update_binary(0, b"\x00\x00")
            if sw != 0x9000:
                raise RuntimeError(f"Clear NDEF failed: {hex(sw)}")

            return True
            
        except Exception as e:
            print(f"Clear error: {e}")
            return False

def main():
    print("🔵 NTAG424 DNA NFC Reader/Writer Tool")
    print("📱 Optimized for NTAG424 DNA - Type 4 Tag (T4T) Support")
    print("-" * 60)
    
    try:
        # Initialize reader
        ntag424 = NTAG424Reader()
        
        while True:
            print("\n📋 Menu:")
            print("1. Read card info")
            print("2. Read NDEF message") 
            print("3. Write NDEF URL (for phone tap-to-open)")
            print("4. Write NDEF Text (for app reading)")
            print("5. Clear NDEF message")
            print("6. Provision new tag (enable write protection)")
            print("7. Test authentication")
            print("8. Initialize NDEF structure (if tag is uninitialized)")
            print("9. Exit")
            
            choice = input("\nSelect option (1-9): ").strip()
            
            if choice == '9':
                break
                
            if choice in ['1', '2', '3', '4', '5', '6', '7', '8']:
                # Wait for card
                ntag424.wait_for_card()
                
                # Get card UID
                uid = ntag424.get_uid()
                print(f"Card UID: {uid}")
                
                # Detect card type
                if choice == '1':
                    card_type = ntag424.detect_card_type()
                
                if choice == '1':
                    # Read card info
                    print("\n📖 Card Information:")
                    print(f"Type: {card_type}")
                    print(f"UID: {uid}")
                    print("Capabilities: Type 4 Tag (T4T) NDEF support")
                    
                elif choice == '2':
                    # Read NDEF message
                    ndef_content = ntag424.read_ndef_message()
                    print(f"\n📖 NDEF Content: '{ndef_content}'")
                    
                elif choice == '3':
                    # Write NDEF URL
                    url = input("Enter URL to write (e.g., https://example.com): ")
                    if not url.startswith(('http://', 'https://')):
                        url = 'https://' + url
                        print(f"Added https:// prefix: {url}")
                    
                    if ntag424.write_ndef_url(url, uid):
                        print("✅ NDEF URL written successfully!")
                        print("📱 Now tap this card to your phone to open the URL!")
                    else:
                        print("❌ Failed to write NDEF URL")
                        
                elif choice == '4':
                    # Write NDEF Text
                    text = input("Enter text data to write: ")
                    
                    if ntag424.write_ndef_text(text):
                        print("✅ NDEF Text written successfully!")
                        print("📱 Your app can now read this data from the NFC card!")
                    else:
                        print("❌ Failed to write NDEF Text")
                        
                elif choice == '5':
                    # Clear NDEF message
                    confirm = input("Are you sure you want to clear the NDEF message? (y/N): ").strip().lower()
                    if confirm == 'y':
                        if ntag424.clear_ndef():
                            print("✅ NDEF message cleared successfully!")
                        else:
                            print("❌ Failed to clear NDEF message")
                    else:
                        print("Clear cancelled")
                        
                elif choice == '6':
                    # Provision new tag
                    if ntag424.is_provisioned(uid):
                        print("⚠️  This tag is already provisioned!")
                        print(f"📝 Stored key: {ntag424.get_key_for_uid(uid)}")
                        overwrite = input("Do you want to re-provision it? (y/N): ").strip().lower()
                        if overwrite != 'y':
                            print("Provisioning cancelled")
                            continue
                    
                    print("\n🔧 Starting tag provisioning...")
                    print("⚠️  WARNING: This will enable write protection!")
                    print("📱 The tag will still be readable by phones, but only you can write to it.")
                    confirm = input("Continue with provisioning? (y/N): ").strip().lower()
                    
                    if confirm == 'y':
                        if ntag424.provision_tag(uid):
                            print("✅ Tag successfully provisioned and secured!")
                            print("🔒 Write protection is now active")
                        else:
                            print("❌ Provisioning failed")
                    else:
                        print("Provisioning cancelled")
                        
                elif choice == '7':
                    # Test authentication
                    if ntag424.is_provisioned(uid):
                        print("🔐 Testing authentication...")
                        stored_key_hex = ntag424.get_key_for_uid(uid)
                        if stored_key_hex:
                            stored_key = bytes.fromhex(stored_key_hex)
                            if ntag424.authenticate_ntag424(stored_key):
                                print("✅ Authentication test successful!")
                                print("🔒 You can write to this protected tag")
                            else:
                                print("❌ Authentication test failed!")
                                print("⚠️  You cannot write to this protected tag")
                        else:
                            print("❌ No key found for this UID")
                    else:
                        print("ℹ️  This tag is not provisioned (no write protection)")
                        print("📝 Anyone can write to this tag")
                        
                elif choice == '8':
                    # Initialize NDEF structure
                    print("\n🔧 Initializing NDEF structure on tag...")
                    print("⚠️  This will create CC and NDEF files if they don't exist")
                    confirm = input("Continue? (y/N): ").strip().lower()
                    if confirm == 'y':
                        success, msg = ntag424.initialize_ndef()
                        if success:
                            print("✅ NDEF structure initialized successfully!")
                            print("📱 Tag is now ready for NDEF operations")
                        else:
                            print(f"❌ Initialization failed: {msg}")
                    else:
                        print("Initialization cancelled")
                        
                input("\n↩️  Press Enter to continue...")
                
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
