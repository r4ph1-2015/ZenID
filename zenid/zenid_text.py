"""
zenid_text.py
--------------
ZenID Invisible Zero-Width Unicode Text Watermarking Engine.
Uses non-whitespace zero-width characters (\u200C and \u200D) to survive string stripping,
with full file read/write support to prevent terminal paste buffer corruption.
"""

import os
import hashlib
import hmac

ZW_ZERO = "\u200C"  # Zero-width non-joiner (0)
ZW_ONE = "\u200D"   # Zero-width joiner (1)
MAGIC_HEADER = "ZIDT"


def _str_to_bits(s: str) -> str:
    return "".join(format(ord(c), "08b") for c in s)


def _bits_to_str(b: str) -> str:
    chars = [b[i : i + 8] for i in range(0, len(b), 8)]
    return "".join(chr(int(c, 2)) for c in chars if len(c) == 8)


def embed_text(content: str, key: str, author: str) -> str:
    # If content is a valid file path, read from file
    if os.path.isfile(content):
        with open(content, "r", encoding="utf-8") as f:
            content = f.read()

    sig = hmac.new(
        key.encode("utf-8"),
        f"{author}:{MAGIC_HEADER}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:8]

    payload = f"{MAGIC_HEADER}|{author}|{sig}"
    bit_stream = _str_to_bits(payload)

    zw_payload = "".join(ZW_ONE if bit == "1" else ZW_ZERO for bit in bit_stream)
    return content + zw_payload


def detect_text(content: str, key: str) -> dict:
    # If content is a valid file path, read from file
    if os.path.isfile(content):
        with open(content, "r", encoding="utf-8") as f:
            content = f.read()

    extracted_bits = []
    for char in content:
        if char == ZW_ZERO:
            extracted_bits.append("0")
        elif char == ZW_ONE:
            extracted_bits.append("1")

    if not extracted_bits:
        return {"present": False, "message": "No invisible text watermark detected."}

    decoded_str = _bits_to_str("".join(extracted_bits))
    parts = decoded_str.split("|")

    if len(parts) < 3 or parts[0] != MAGIC_HEADER:
        return {
            "present": False,
            "message": "Corrupted or missing ZenID text signature.",
        }

    author, received_sig = parts[1], parts[2]
    expected_sig = hmac.new(
        key.encode("utf-8"),
        f"{author}:{MAGIC_HEADER}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()[:8]

    verified = hmac.compare_digest(received_sig, expected_sig)
    return {
        "present": verified,
        "author": author if verified else "UNVERIFIED",
        "crypto_verified": verified,
        "message": (
            "HMAC-SHA256 Text Signature Authenticated!"
            if verified
            else "Invalid Key or Tampered Signature."
        ),
    }