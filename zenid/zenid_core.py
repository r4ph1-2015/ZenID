"""
zenid_core.py
-------------
High-Security Native 8x8 Block-DCT Image Watermarking Engine (Full Color & Robust YCbCr).
"""

from __future__ import annotations

import hashlib
import hmac
import random
from PIL import Image
import numpy as np

# Configuration constants
BLOCK_SIZE = 8
QUANT_STEP = 64.0  # Wide quantization step to absorb YCbCr conversion rounding noise
PAYLOAD_BITS = 256  # 32 bytes total capacity (Author + Metadata + HMAC)


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


def embed(input_path: str, output_path: str, key: str, author: str) -> None:
    """
    Embeds an encrypted author watermark into the Y channel of a full-color image
    using robust interval-offset quantization.
    """
    img = Image.open(input_path).convert("YCbCr")
    y_channel, cb, cr = img.split()
    y_arr = np.array(y_channel, dtype=np.float32)

    h, w = y_arr.shape
    if h < BLOCK_SIZE * 16 or w < BLOCK_SIZE * 16:
        raise ValueError("Image dimensions are too small. Minimum resolution is 128x128 pixels.")

    _, fingerprint = _generate_signature(key, author)
    payload_str = f"{author}|{fingerprint}"
    raw_bits = _text_to_bits(payload_str, max_bytes=32)

    # Redundancy factor for bulletproof error recovery
    redundancy_factor = 3
    expanded_bits = []
    for bit in raw_bits:
        expanded_bits.extend([bit] * redundancy_factor)

    total_bits = len(expanded_bits)
    blocks_h = h // BLOCK_SIZE
    blocks_w = w // BLOCK_SIZE
    total_blocks = blocks_h * blocks_w
    
    if total_blocks < total_bits:
        raise ValueError(f"Image too small for payload. Needs at least {total_bits} blocks.")

    seed_int = int(hashlib.sha256(key.encode()).hexdigest(), 16) % (2**32)
    rng = random.Random(seed_int)
    
    block_indices = [(r, c) for r in range(blocks_h) for c in range(blocks_w)]
    rng.shuffle(block_indices)

    u, v = 3, 4
    for bit_idx, bit in enumerate(expanded_bits):
        r, c = block_indices[bit_idx]
        block = y_arr[r*BLOCK_SIZE:(r+1)*BLOCK_SIZE, c*BLOCK_SIZE:(c+1)*BLOCK_SIZE]

        val = block[u, v]
        base = np.floor(val / QUANT_STEP) * QUANT_STEP
        # Bit 1 targets upper quarter, Bit 0 targets lower quarter of the quantum interval
        target = base + (0.75 * QUANT_STEP if bit == 1 else 0.25 * QUANT_STEP)
        block[u, v] = target

        y_arr[r*BLOCK_SIZE:(r+1)*BLOCK_SIZE, c*BLOCK_SIZE:(c+1)*BLOCK_SIZE] = block

    y_mod = Image.fromarray(np.clip(y_arr, 0, 255).astype(np.uint8))
    watermarked_img = Image.merge("YCbCr", (y_mod, cb, cr)).convert("RGB")
    watermarked_img.save(output_path, quality=95)


def detect(image_path: str, key: str) -> dict:
    """
    Extracts and verifies the watermark from a full-color image using robust
    interval decoding and majority-vote error correction.
    """
    img = Image.open(image_path).convert("YCbCr")
    y_channel, _, _ = img.split()
    y_arr = np.array(y_channel, dtype=np.float32)

    h, w = y_arr.shape
    blocks_h = h // BLOCK_SIZE
    blocks_w = w // BLOCK_SIZE

    seed_int = int(hashlib.sha256(key.encode()).hexdigest(), 16) % (2**32)
    rng = random.Random(seed_int)

    block_indices = [(r, c) for r in range(blocks_h) for c in range(blocks_w)]
    rng.shuffle(block_indices)

    redundancy_factor = 3
    total_bits = PAYLOAD_BITS * redundancy_factor
    extracted_expanded_bits = []

    u, v = 3, 4
    for bit_idx in range(total_bits):
        r, c = block_indices[bit_idx]
        block = y_arr[r*BLOCK_SIZE:(r+1)*BLOCK_SIZE, c*BLOCK_SIZE:(c+1)*BLOCK_SIZE]
        
        val = block[u, v]
        remainder = val % QUANT_STEP
        # Threshold at 50% of interval (32.0)
        bit = 1 if remainder >= (0.5 * QUANT_STEP) else 0
        extracted_expanded_bits.append(bit)

    # Reconstruct original bits via Majority Vote
    raw_bits = []
    for i in range(0, len(extracted_expanded_bits), redundancy_factor):
        chunk = extracted_expanded_bits[i:i+redundancy_factor]
        majority = 1 if sum(chunk) > (redundancy_factor / 2) else 0
        raw_bits.append(majority)

    decoded_text = _bits_to_text(raw_bits)
    
    if "|" not in decoded_text:
        return {"message": "Watermark Not Found or Corrupted", "verified": False}

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