#!/usr/bin/env python3
"""Test script for ACR122U NFC reader using pyscard"""

from smartcard.System import readers
from smartcard.util import toHexString, toBytes
import sys

def test_reader():
    """Test if ACR122U reader is detected and working"""
    # Get all available readers
    r = readers()
    
    if not r:
        print("No smart card readers found!")
        return False
    
    print(f"Found {len(r)} reader(s):")
    for idx, reader in enumerate(r):
        print(f"  [{idx}] {reader}")
    
    # Look for ACR122U
    acr122u = None
    for reader in r:
        if "ACR122" in str(reader):
            acr122u = reader
            break
    
    if not acr122u:
        print("\nACR122U reader not found in the list!")
        return False
    
    print(f"\nUsing reader: {acr122u}")
    
    try:
        # Connect to the reader
        connection = acr122u.createConnection()
        connection.connect()
        print("Successfully connected to ACR122U!")
        
        # Get reader info
        # This is the APDU command to get firmware version
        GET_FIRMWARE = [0xFF, 0x00, 0x48, 0x00, 0x00]
        data, sw1, sw2 = connection.transmit(GET_FIRMWARE)
        
        if sw1 == 0x90 and sw2 == 0x00:
            firmware = ''.join([chr(x) for x in data])
            print(f"Firmware version: {firmware}")
        
        # Turn off the LED beep
        BEEP_OFF = [0xFF, 0x00, 0x52, 0x00, 0x00]
        connection.transmit(BEEP_OFF)
        
        print("\nReader is ready to use!")
        print("Place an NFC tag on the reader to test...")
        
        # Wait for card
        print("\nWaiting for NFC tag (press Ctrl+C to exit)...")
        
        # Turn on green LED to indicate ready
        LED_GREEN = [0xFF, 0x00, 0x40, 0x0D, 0x04, 0x01, 0x00, 0x01, 0x00]
        connection.transmit(LED_GREEN)
        
        return True
        
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    if test_reader():
        print("\n✅ Your ACR122U is working correctly!")
    else:
        print("\n❌ There was a problem with the ACR122U")
        sys.exit(1)