#!/usr/bin/env python3
"""
NFC Tag Diagnostic Tool
Identifies tag type and checks for write protection
"""

from smartcard.System import readers
from smartcard.util import toHexString, toBytes
import sys

class NFCDiagnostic:
    def __init__(self):
        self.reader = None
        self.connection = None
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
    
    def wait_for_card(self):
        """Wait for an NFC card"""
        print("\n⏳ Place an NFC tag on the reader...")
        while True:
            try:
                self.connection = self.reader.createConnection()
                self.connection.connect()
                print("✅ Card detected!")
                return True
            except:
                continue
    
    def send_command(self, command):
        """Send command and return response"""
        try:
            data, sw1, sw2 = self.connection.transmit(command)
            return data, sw1, sw2
        except Exception as e:
            return None, None, None
    
    def get_uid(self):
        """Get UID"""
        data, sw1, sw2 = self.send_command([0xFF, 0xCA, 0x00, 0x00, 0x00])
        if sw1 == 0x90 and sw2 == 0x00:
            return toHexString(data)
        return None
    
    def get_atr(self):
        """Get ATR"""
        try:
            return toHexString(self.connection.getATR())
        except:
            return None
    
    def diagnose_tag(self):
        """Diagnose the tag type and capabilities"""
        print("\n🔍 Diagnosing NFC Tag...")
        print("-" * 40)
        
        # Get basic info
        uid = self.get_uid()
        atr = self.get_atr()
        print(f"UID: {uid}")
        print(f"ATR: {atr}")
        
        # Try to read version info (NTAG only)
        print("\n📊 Checking tag type...")
        version_cmd = [0xFF, 0xB0, 0x00, 0x60, 0x08]  # GET_VERSION command
        data, sw1, sw2 = self.send_command(version_cmd)
        
        tag_type = "Unknown"
        memory_size = "Unknown"
        
        if sw1 == 0x90 and sw2 == 0x00 and len(data) >= 8:
            # NTAG chip
            if data[2] == 0x04:  # Vendor ID for NXP
                if data[6] == 0x12:
                    tag_type = "NTAG213"
                    memory_size = "180 bytes"
                elif data[6] == 0x3E:
                    tag_type = "NTAG215"
                    memory_size = "540 bytes"
                elif data[6] == 0x6D:
                    tag_type = "NTAG216"
                    memory_size = "924 bytes"
        
        # Check if it's Mifare Classic by trying auth
        print("\n🔐 Checking authentication requirements...")
        
        # Try Mifare Classic auth with default key
        auth_cmd = [0xFF, 0x86, 0x00, 0x00, 0x05, 0x01, 0x00, 0x04, 0x60, 0x00]
        data, sw1, sw2 = self.send_command(auth_cmd)
        
        if sw1 == 0x90 and sw2 == 0x00:
            tag_type = "Mifare Classic"
            print("✅ Mifare Classic detected (requires authentication)")
        else:
            print("ℹ️  No authentication required (likely NTAG)")
        
        print(f"\n📱 Tag Type: {tag_type}")
        print(f"💾 Memory Size: {memory_size}")
        
        # Check write protection
        print("\n🔒 Checking write protection...")
        
        # Try to read configuration pages (for NTAG)
        for page in range(0x29, 0x2D):  # Config pages for NTAG
            read_cmd = [0xFF, 0xB0, 0x00, page, 0x04]
            data, sw1, sw2 = self.send_command(read_cmd)
            if sw1 == 0x90 and sw2 == 0x00:
                print(f"Config page {page:02X}: {toHexString(data[:4])}")
        
        # Try to read blocks
        print("\n📖 Reading first 16 blocks:")
        for block in range(16):
            read_cmd = [0xFF, 0xB0, 0x00, block, 0x04]
            data, sw1, sw2 = self.send_command(read_cmd)
            if sw1 == 0x90 and sw2 == 0x00:
                print(f"Block {block:02d}: {toHexString(data[:4])}")
            else:
                print(f"Block {block:02d}: Read failed (protected or invalid)")
        
        # Test write capability
        print("\n✍️  Testing write capability on block 4...")
        test_data = [0x00, 0x00, 0x00, 0x00]
        
        # First read original data
        read_cmd = [0xFF, 0xB0, 0x00, 0x04, 0x04]
        orig_data, sw1, sw2 = self.send_command(read_cmd)
        
        if sw1 == 0x90 and sw2 == 0x00:
            print(f"Original data: {toHexString(orig_data[:4])}")
            
            # Try to write
            write_cmd = [0xFF, 0xD6, 0x00, 0x04, 0x04] + test_data
            data, sw1, sw2 = self.send_command(write_cmd)
            
            if sw1 == 0x90 and sw2 == 0x00:
                print("✅ Write test successful!")
                # Restore original data
                write_cmd = [0xFF, 0xD6, 0x00, 0x04, 0x04] + list(orig_data[:4])
                self.send_command(write_cmd)
            else:
                print(f"❌ Write failed! SW1={sw1:02X}, SW2={sw2:02X}")
                if sw1 == 0x63 and sw2 == 0x00:
                    print("   → Authentication required")
                elif sw1 == 0x6A and sw2 == 0x81:
                    print("   → Function not supported")
                elif sw1 == 0x6A and sw2 == 0x82:
                    print("   → Application not found")
        
        return tag_type

def main():
    print("🔍 NFC Tag Diagnostic Tool")
    print("=" * 40)
    
    try:
        diag = NFCDiagnostic()
        diag.wait_for_card()
        tag_type = diag.diagnose_tag()
        
        print("\n💡 Recommendations:")
        if "Mifare Classic" in tag_type:
            print("- This card requires authentication before writing")
            print("- Use default keys or known keys for your card")
        elif "NTAG" in tag_type:
            print("- This tag should support direct writing to user memory")
            print("- Check if write protection is enabled on block 4")
        else:
            print("- Unknown tag type, may need special handling")
            
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()