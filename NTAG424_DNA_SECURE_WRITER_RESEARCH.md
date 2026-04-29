# NTAG424 DNA Secure Writer Research

Research date: 2026-04-29

## Summary

Buying a different reader/writer is not enough by itself. NTAG424 DNA write protection is enforced by the tag's AES-backed access-control configuration. The reader only needs to be capable of sending the required ISO 14443-4 / ISO-DEP APDUs reliably. The secure behavior comes from provisioning the tag so that:

- normal phones can still read the public NDEF content;
- writes, clears, key changes, and file-configuration changes require AES authentication;
- the writer software holds the required key material and performs the NTAG424 secure-messaging flow.

A simple string token is not the right security boundary. The equivalent secure design is an AES key, preferably diversified per tag from a master secret. If the same static token/key is used on every tag and it leaks, every tag can be overwritten.

## What NTAG424 DNA Provides

NXP describes NTAG424 DNA as an NFC Forum Type 4 Tag with an ISO/IEC 7816-4 file system, AES-128 authentication/secure messaging, SUN authentication, protected communication, and crypto-secure access permissions. It has a 256-byte NDEF file and a protected data file. NXP also lists 3-pass mutual authentication and encrypted data transfer for protected data.

Sources:

- NXP NTAG424 DNA product page: https://www.nxp.com/products/rfid-nfc/nfc-hf/ntag-for-tags-and-labels/ntag-424-dna-424-dna-tagtamper-advanced-security-and-privacy-for-trusted-iot-applications%3ANTAG424DNA
- NXP NTAG424 DNA documentation listing, including AN12196 "features and hints": https://www.nxp.com/products/rfid-nfc/nfc-hf/ntag-for-tags-and-labels/ntag-424-dna-424-dna-tagtamper-advanced-security-and-privacy-for-trusted-iot-applications%3ANTAG424DNA?tab=Documentation_Tab
- NXP launch/security overview: https://www.nxp.com/company/about-nxp/newsroom/NW-NTAG-424-DNA

## Security Model Needed

For the use case "anyone can tap/read, only I can clear or overwrite":

1. Write the intended NDEF payload.
2. Change the NDEF file access rights so read access remains free, but write/read-write/change access requires a chosen application key.
3. Replace default keys with non-default AES keys.
4. Store keys securely in the writer system.
5. For future edits, authenticate with the correct AES key, use secure messaging as required, update the NDEF file, and keep the protected access rights in place.

This is materially different from normal NDEF writing. A normal NFC writer app can update the NDEF file only while write access is open. Once the file is protected correctly, generic writers should fail to overwrite it.

Important limits:

- This prevents unauthorized logical overwrite. It does not prevent someone from physically destroying the tag or replacing the entire tag with another tag.
- To detect replacement/cloning, use NTAG424 SUN/CMAC validation on the backend, not just a static URL.
- For physical-open detection, evaluate NTAG424 DNA TagTamper variants.
- Do not rely on a human-readable passcode/string written onto the tag. The secret must not be readable from the tag.

## Reader/Writer Requirements

A suitable reader should support:

- 13.56 MHz NFC.
- ISO/IEC 14443 Type A.
- ISO/IEC 14443-4 / ISO-DEP / T=CL communication.
- PC/SC and CCID on desktop, or equivalent APDU access on mobile.
- Raw APDU exchange with the tag.
- Stable driver support on the target OS.
- Optional but useful: extended APDU support, 848 kbps support, and a SAM slot for hardware-backed key operations.

The writer software must support:

- NTAG424 application/file selection.
- AES mutual authentication.
- Session-key derivation and secure messaging.
- file access-right configuration.
- key changes from factory defaults.
- per-tag key diversification and secure key storage.

## Hardware Options

### Best Practical Desktop Choice: ACS ACR1552U

The ACR1552U is a current ACS USB NFC reader. ACS lists PC/SC and CCID support, ISO 14443 Type A/B, ISO 14443-4 compliant cards using T=CL, read/write speed up to 848 kbps, extended APDU support up to 64 KB, and a SAM slot.

Why it fits:

- Good match for Python/PCSC development.
- Better forward-looking choice than the ACR122U.
- Extended APDU support and 848 kbps are useful for secure Type 4 Tag work.
- SAM slot gives a path to stronger key custody later.

Risk:

- It will not automatically make writes secure. The application still has to implement NTAG424 provisioning and secure messaging.

Source: https://www.acs.com.hk/en/products/575/acr1552u-/

### Strong Desktop Alternative: SpringCard Prox'N'Roll PC/SC HSP

SpringCard lists PC/SC support across Windows, Linux, Unix, and macOS, ISO 14443-4 T=CL support for Type A and Type B, ISO-DEP in firmware, and 106/212/424/848 kbps RF bitrates.

Why it fits:

- Good standards coverage for Type 4 Tag APDU work.
- Strong PC/SC integration story.
- Suitable for production-style desktop tools if the software stack is implemented correctly.

Risk:

- Check procurement cost and availability.
- Confirm APDU behavior with NTAG424 tags before committing to volume.

Source: https://www.springcard.com/en/products/proxnroll-pcsc-hsp

### Good Security-Oriented Option: GMMC Pocket NFC Reader Writer

GMMC's Pocket NFC is listed by NXP as a partner hardware option for NTAG424 DNA. GMMC describes it as a USB stick-sized multi-standard, multi-protocol NFC reader-writer with USB-CCID and a Micro SIM connector for SAM support.

Why it fits:

- NXP partner hardware listing for the NTAG424 DNA ecosystem.
- SAM support is relevant if key operations should move out of the host computer.
- Compact form factor.

Risk:

- Less common than ACS readers in open-source Python examples.
- Confirm SDK/API details, OS support, and APDU examples before purchase.

Sources:

- GMMC Pocket NFC: https://www.gmmc-biz.com/nfc-reader-writer.html
- NXP NTAG424 DNA design resources listing Pocket NFC: https://www.nxp.com/products/rfid-nfc/nfc-hf/ntag-for-tags-and-labels/ntag-424-dna-424-dna-tagtamper-advanced-security-and-privacy-for-trusted-iot-applications%3ANTAG424DNA?tab=Buy_Parametric_Tab

### NXP Development/Evaluation Choice: PEGODA MFEV710-EVK

NXP describes the PEGODA MFEV710-EVK as a reference design and evaluation reader for secure applications based on MIFARE and NTAG products.

Why it fits:

- Best aligned with NXP evaluation workflows.
- Useful for validating NXP examples and tag behavior.

Risk:

- More of an evaluation/development kit than a simple desktop writer.
- May be less convenient for a small production encoding station than a USB PC/SC reader.

Source: https://www.nxp.com/design/design-center/development-boards-and-designs/MFEV710-EVK

### Usable but Not Preferred for New Work: ACS ACR1252U

The ACR1252U is NFC Forum certified, PC/SC and CCID compliant, supports ISO 14443 Type A/B, MIFARE, FeliCa, NFC reader/writer mode, and includes a SAM slot.

Why it fits:

- Similar development model to the current ACR122U family.
- SAM slot is useful.

Risk:

- ACS lists read/write speed up to 424 kbps, while newer readers such as ACR1552U list 848 kbps and extended APDU support.
- I would choose ACR1552U first for new NTAG424 work.

Source: https://www.acr1252.com/

### Current Reader Context: ACS ACR122U

The ACR122U supports ISO 14443 Type A/B, NFC tags, PC/SC, and CCID. ACS currently notes that the ACR122U has reached end-of-life and recommends the ACR1552U for new deployments. ACS also warns about counterfeit/non-genuine ACR122U units.

Implication:

- Your existing ACR122U can write NTAG424 DNA as an open Type 4 Tag, which matches what you are seeing.
- It may be possible to use it for secure NTAG424 commands, but it is not the hardware I would standardize on now.
- The bigger missing piece is not basic writing; it is correct NTAG424 authentication, key change, secure messaging, and access-right provisioning.

Source: https://www.acr122.com/

### Other PC/SC Readers

Identiv uTrust 3700 F and HID OMNIKEY readers may be usable if they expose ISO 14443-4 cards through PC/SC and allow raw APDUs. Identiv's support page confirms current driver availability for the uTrust 3700 F, and HID markets OMNIKEY devices as CCID/NFC smart-card readers. I would treat these as secondary candidates unless there is a specific procurement reason to use them.

Sources:

- Identiv uTrust 3700 F support: https://support.identiv.com/3700f/
- HID OMNIKEY 5022: https://www.hidglobal.com/products/omnikey-5022-reader

## Software Options

### NXP TapLinx

NXP's TapLinx SDK supports NXP MIFARE, NTAG, ICODE, and UCODE products and provides APIs for NFC-enabled devices. NXP's current TapLinx downloads include Android, Java, and iOS SDK material.

Use TapLinx when:

- you are willing to build an Android/Java/iOS writer;
- you want vendor-supported primitives instead of implementing every NTAG424 command by hand;
- account-required NXP downloads are acceptable.

Source: https://www.nxp.com/design/design-center/software/rfid-developer-resources/taplinx-software-development-kit-sdk%3ATAPLINX

### Python + PC/SC

This repository is already Python + `pyscard`, so the pragmatic path is:

- keep using PC/SC readers;
- upgrade hardware to ACR1552U or another strong PC/SC reader;
- implement real NTAG424 secure provisioning in Python.

This requires work beyond normal `UPDATE BINARY` writes. The current `ntag424_dna_readwrite.py` has useful APDU scaffolding, but its provisioning path explicitly does not complete full NTAG424 write-protection provisioning.

### Key Storage

For development, a local JSON key file is acceptable only as a temporary test mechanism. For serious anti-tamper use:

- derive a unique AES key per tag from a master key and the tag UID or another stable identifier;
- store the master key outside the repo;
- consider an HSM, OS keychain, cloud KMS, or SAM-based design;
- log each issued tag UID and key version;
- plan key rotation and recovery before writing production tags.

## Recommendation

Recommended near-term path:

1. Buy an ACS ACR1552U for desktop development and production writing.
2. Keep the ACR122U only as a compatibility/test reader.
3. Implement or integrate NTAG424 provisioning that changes default keys and sets write/change access rights on the NDEF file.
4. Use diversified AES keys, not a shared string token.
5. Validate the result by writing a tag, then attempting to overwrite it with a generic NFC writer. The overwrite should fail while normal phone reads still work.

Recommended stronger path:

1. Use ACR1552U, SpringCard Prox'N'Roll, or GMMC Pocket NFC with SAM support.
2. Move master-key or per-tag-key operations into a SAM/HSM/keychain-backed design.
3. Use SUN/CMAC URL validation server-side so cloned or replaced tags can be detected.
4. Use NTAG424 DNA TagTamper if physical opening/removal status matters.

## Decision Matrix

| Option | Fit for NTAG424 secure writing | Main reason | Caveat |
| --- | --- | --- | --- |
| ACS ACR1552U | High | Current PC/SC reader, ISO 14443-4/T=CL, extended APDU, SAM slot | Software must implement NTAG424 security |
| SpringCard Prox'N'Roll PC/SC HSP | High | Strong PC/SC and ISO-DEP/T=CL support | Validate cost/availability |
| GMMC Pocket NFC | High | NXP partner listing, CCID, SAM support | Less common in Python examples |
| NXP PEGODA MFEV710-EVK | High for evaluation | NXP reference/evaluation reader for MIFARE/NTAG secure apps | Less convenient as a simple writer station |
| ACS ACR1252U | Medium-high | PC/SC/CCID, NFC Forum certified, SAM slot | Older capability profile than ACR1552U |
| ACS ACR122U | Medium | Already works for open writing and supports PC/SC/CCID | End-of-life; not preferred for new secure deployment |
| Generic phone writer apps | Low | Can write ordinary NDEF | Usually cannot provision NTAG424 access rights |
| Custom Android app with TapLinx | High | Vendor SDK path for NXP NFC products | Requires mobile app development and NXP SDK integration |

## Open Questions Before Implementation

- Which exact tag SKU is being used: NTAG424 DNA, NTAG424 DNA TT, or another "DNA" family tag?
- Should phones read a static URL, a SUN-authenticated dynamic URL, or app-specific text/JSON?
- Is replacement/cloning detection required, or only overwrite prevention?
- What OS should the writer station run: macOS, Windows, Linux, Android, or iOS?
- Is a hardware key module/SAM acceptable, or should key custody start with OS keychain/cloud KMS?

