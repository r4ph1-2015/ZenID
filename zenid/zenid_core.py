"""
zenid_core.py
--------------
ZenID v1.2: Native 8x8 Block-DCT Luminance Differential Engine.
Embeds a fixed 256-bit frame into the Y (Luminance) channel for maximum 
color-space stability, featuring magic header validation and HMAC verification.
"""

from __future__ import annotations

import hashlib
import hmac
import numpy as np
from PIL import Image
from scipy.fft import dctn, idctn

# Differential modulation margin (survives RGB/JPEG quantization)
GAP_MARGIN = 30.0

# Mid-frequency DCT coefficient candidate pairs
MID_FREQ_COORDS = [
    (3, 3), (3, 4), (4, 3), (4, 4),
    (2, 4), (4, 2), (3, 5), (5, 3)
]

FRAME_BITS = 256  # Fixed 32-byte frame
MAGIC = b"ZEN1"   # 4-byte header


def _derive_seed(key: str) -> int:
    """Derive deterministic PRNG seed using HMAC-SHA256."""
    h = hmac.new(key.encode("utf-8"), b"zenid_image_salt", hashlib.sha256).digest()
    return int.from_bytes(h[:4], byteorder="big")


def _payload_to_frame(author: str, key: str) -> list[int]:
    """Convert author string into a fixed 256-bit frame with magic header and HMAC."""
    author_bytes = author.encode("utf-8")[:20]  # Max 20 bytes for author name
    length = len(author_bytes)

    raw = bytearray(32)
    raw[0:4] = MAGIC
    raw[4] = length
    raw[5 : 5 + length] = author_bytes

    # Generate HMAC checksum for the header + author
    mac = hmac.new(key.encode("utf-8"), raw[: 5 + length], hashlib.sha256).digest()
    raw[5 + length :] = mac[: 27 - length]

    bits = []
    for byte in raw:
        for i in range(8):
            bits.append((byte >> i) & 1)
    return bits


def _frame_to_payload(bits: list[int], key: str) -> tuple[str | None, str | None]:
    """Reconstruct and cryptographically verify author payload from extracted bits."""
    if len(bits) < FRAME_BITS:
        return None, None

    raw = bytearray(32)
    for byte_idx in range(32):
        val = 0
        for bit_idx in range(8):
            val |= (bits[byte_idx * 8 + bit_idx] & 1) << bit_idx
        raw[byte_idx] = val

    # Check magic header
    if raw[0:4] != MAGIC:
        return None, None

    length = raw[4]
    if length == 0 or length > 20:
        return None, None

    try:
        author = raw[5 : 5 + length].decode("utf-8")
    except UnicodeDecodeError:
        return None, None

    # Cryptographic integrity check
    expected_mac = hmac.new(key.encode("utf-8"), raw[: 5 + length], hashlib.sha256).digest()
    actual_mac = raw[5 + length :]
    if actual_mac != expected_mac[: len(actual_mac)]:
        return None, None  # Invalid key or corrupted payload

    fingerprint = hashlib.sha256(f"{author}:{key}".encode()).hexdigest()[:12]
    return author, fingerprint


def embed(input_path: str, output_path: str, key: str, author: str) -> None:
    """Embed author identity into the Y (Luminance) channel using Differential DCT."""
    img = Image.open(input_path).convert("YCbCr")
    y, cb, cr = img.split()

    y_arr = np.array(y, dtype=np.float32)
    h, w = y_arr.shape

    h_block, w_block = h // 8, w // 8
    total_blocks = h_block * w_block
    if total_blocks < FRAME_BITS:
        raise ValueError("Image too small. Minimum resolution: 128x128 pixels.")

    bits = _payload_to_frame(author, key)
    repetitions = total_blocks // FRAME_BITS

    seed = _derive_seed(key)
    rng = np.random.default_rng(seed)

    block_idx = 0
    for rep in range(repetitions):
        for bit_i in range(FRAME_BITS):
            r = block_idx // w_block
            c = block_idx % w_block

            p1_idx, p2_idx = rng.choice(len(MID_FREQ_COORDS), size=2, replace=False)
            p1 = MID_FREQ_COORDS[p1_idx]
            p2 = MID_FREQ_COORDS[p2_idx]

            block = y_arr[r * 8 : (r + 1) * 8, c * 8 : (c + 1) * 8]
            dct_block = dctn(block, norm="ortho")

            v1 = dct_block[p1]
            v2 = dct_block[p2]
            avg = (v1 + v2) / 2.0
            target_bit = bits[bit_i]

            if target_bit == 1:
                if v1 - v2 < GAP_MARGIN:
                    dct_block[p1] = avg + (GAP_MARGIN / 2.0)
                    dct_block[p2] = avg - (GAP_MARGIN / 2.0)
            else:
                if v2 - v1 < GAP_MARGIN:
                    dct_block[p1] = avg - (GAP_MARGIN / 2.0)
                    dct_block[p2] = avg + (GAP_MARGIN / 2.0)

            y_arr[r * 8 : (r + 1) * 8, c * 8 : (c + 1) * 8] = idctn(
                dct_block, norm="ortho"
            )
            block_idx += 1

    y_arr = np.clip(y_arr, 0, 255).astype(np.uint8)
    modified_y = Image.fromarray(y_arr, mode="L")
    watermarked_img = Image.merge("YCbCr", (modified_y, cb, cr)).convert("RGB")
    watermarked_img.save(output_path)


def detect(image_path: str, key: str) -> dict[str, str]:
    """Extract embedded watermark using majority voting and HMAC verification."""
    img = Image.open(image_path).convert("YCbCr")
    y, _, _ = img.split()

    y_arr = np.array(y, dtype=np.float32)
    h, w = y_arr.shape

    h_block, w_block = h // 8, w // 8
    total_blocks = h_block * w_block
    if total_blocks < FRAME_BITS:
        return {"message": "Image too small (min 128x128 required)", "author": "N/A", "fingerprint": "N/A"}

    repetitions = total_blocks // FRAME_BITS
    if repetitions == 0:
        return {"message": "Insufficient image capacity", "author": "N/A", "fingerprint": "N/A"}

    seed = _derive_seed(key)
    rng = np.random.default_rng(seed)

    bit_votes = [0] * FRAME_BITS

    block_idx = 0
    for rep in range(repetitions):
        for bit_i in range(FRAME_BITS):
            r = block_idx // w_block
            c = block_idx % w_block

            p1_idx, p2_idx = rng.choice(len(MID_FREQ_COORDS), size=2, replace=False)
            p1 = MID_FREQ_COORDS[p1_idx]
            p2 = MID_FREQ_COORDS[p2_idx]

            block = y_arr[r * 8 : (r + 1) * 8, c * 8 : (c + 1) * 8]
            dct_block = dctn(block, norm="ortho")

            bit_val = 1 if dct_block[p1] > dct_block[p2] else 0
            if bit_val == 1:
                bit_votes[bit_i] += 1
            block_idx += 1

    extracted_bits = [1 if votes > (repetitions / 2.0) else 0 for votes in bit_votes]

    author, fingerprint = _frame_to_payload(extracted_bits, key)

    if author:
        return {
            "message": "Watermark Verified Successfully",
            "author": author,
            "fingerprint": fingerprint,
        }

    return {
        "message": "No valid watermark detected (or key invalid)",
        "author": "N/A",
        "fingerprint": "N/A",
    }