"""
zenid_text.py
-------------
High-Security Text Watermarking Engine using Hybrid Zero-Width Unicode 
and Cryptographic Homoglyph Substitution.
"""

from __future__ import annotations

import hashlib
import hmac
import random

# Zero-width mapping characters
ZW_ZERO = "\u200C"  # Zero-Width Non-Joiner (represents 0)
ZW_ONE = "\u200D"   # Zero-Width Joiner (represents 1)

# Homoglyph substitution map (Latin characters -> Visually identical Cyrillic variants)
HOMOGLYPH_MAP = {
    'a': 'а',  # Cyrillic small letter a
    'e': 'е',  # Cyrillic small letter ie
    'o': 'о',  # Cyrillic small letter o
    'p': 'р',  # Cyrillic small letter er
    'c': 'с',  # Cyrillic small letter es
    'x': 'х',  # Cyrillic small letter ha
}


def _generate_signature(key: str, author: str) -> tuple[bytes, str]:
    """Generates an HMAC-SHA256 signature and a short 12-char fingerprint."""
    fingerprint = hashlib.sha256(f"{author}:{key}".encode()).hexdigest()[:12]
    h = hmac.new(key.encode(), author.encode(), hashlib.sha256).digest()
    return h, fingerprint


def _text_to_bits(text: str, max_bytes: int = 32) -> list[int]:
    """Converts a text string into a fixed-size bit array."""
    data = text.encode("utf-8")[:max_bytes]
    data = data.ljust(max_bytes, b'\x00')
    bits = []
    for byte in data:
        for i in range(7, -1, -1):
            bits.append((byte >> i) & 1)
    return bits


def _bits_to_text(bits: list[int]) -> str:
    """Converts a bit array back into a text string."""
    bytes_list = []
    for i in range(0, len(bits), 8):
        byte = 0
        for b in bits[i:i+8]:
            byte = (byte << 1) | b
        bytes_list.append(byte)
    return bytes(bytes_list).rstrip(b'\x00').decode("utf-8", errors="ignore")


def embed_text(input_text_or_path: str, key: str, author: str) -> str:
    """
    Embeds a watermark into text using zero-width characters and 
    key-seeded homoglyph substitution. Accepts a raw string or file path.
    """
    # Check if input is a file path or raw text
    try:
        with open(input_text_or_path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        text = input_text_or_path

    _, fingerprint = _generate_signature(key, author)
    payload_str = f"{author}|{fingerprint}"
    raw_bits = _text_to_bits(payload_str, max_bytes=32)

    # 1. Embed via Zero-Width Stream at the start of the text
    watermark_prefix = "".join([ZW_ONE if b == 1 else ZW_ZERO for b in raw_bits])
    
    # 2. Embed via Key-Seeded Homoglyph Substitution across the text body
    seed_int = int(hashlib.sha256(key.encode()).hexdigest(), 16) % (2**32)
    rng = random.Random(seed_int)

    watermarked_chars = []
    for char in text:
        if char in HOMOGLYPH_MAP and rng.random() > 0.5:
            # Substitute with homoglyph based on key pseudo-random choice
            watermarked_chars.append(HOMOGLYPH_MAP[char])
        else:
            watermarked_chars.append(char)

    body_text = "".join(watermarked_chars)
    return watermark_prefix + body_text


def detect_text(input_text_or_path: str, key: str) -> dict:
    """
    Extracts and verifies the watermark from a text string or file path.
    """
    try:
        with open(input_text_or_path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        text = input_text_or_path

    # Extract zero-width prefix bits if present
    extracted_bits = []
    for char in text:
        if char == ZW_ONE:
            extracted_bits.append(1)
        elif char == ZW_ZERO:
            extracted_bits.append(0)
        
        # Stop once we have gathered 256 bits (32 bytes)
        if len(extracted_bits) >= 256:
            break

    if len(extracted_bits) < 256:
        return {"message": "Watermark Not Found or Stripped", "verified": False}

    decoded_text = _bits_to_text(extracted_bits)

    if "|" not in decoded_text:
        return {"message": "Watermark Corrupted", "verified": False}

    parts = decoded_text.split("|", 1)
    author = parts[0]
    stored_fingerprint = parts[1] if len(parts) > 1 else ""

    _, expected_fingerprint = _generate_signature(key, author)

    if stored_fingerprint == expected_fingerprint:
        return {
            "message": "Watermark Verified Successfully",
            "verified": True,
            "author": author,
            "fingerprint": stored_fingerprint
        }
    else:
        return {
            "message": "Watermark Invalid: Key Mismatch",
            "verified": False
        }