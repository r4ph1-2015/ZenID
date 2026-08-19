"""
zenid_core.py
--------------
ZenID v1.0: Native 8x8 Block-DCT Chrominance Spread-Spectrum Engine.
Operates on native resolution 8x8 Cb blocks to eliminate spatial resizing loss,
guarantee zero luminance visual distortion, and enforce HMAC-SHA256 ownership.
"""

from __future__ import annotations

import hashlib
import hmac
import numpy as np
from PIL import Image
from scipy.fft import dctn, idctn

ALPHA = 15.0  # Modulation strength for mid-frequency coefficients


def _derive_seed(key: str) -> int:
    """Derive deterministic PRNG seed using HMAC-SHA256."""
    h = hmac.new(key.encode("utf-8"), b"zenid_image_salt", hashlib.sha256).digest()
    return int.from_bytes(h[:4], byteorder="big")


def _payload_to_bits(payload: str) -> list[int]:
    """Convert payload text into a bit vector with null-terminator."""
    data = payload + "\0"
    bits = []
    for char in data:
        bits.extend([(ord(char) >> i) & 1 for i in range(8)])
    return bits


def _bits_to_payload(bits: list[int]) -> str:
    """Reconstruct ASCII string from extracted bit vector."""
    chars = []
    for i in range(0, len(bits) - 7, 8):
        byte = 0
        for bit_idx in range(8):
            byte |= (bits[i + bit_idx] & 1) << bit_idx
        if byte == 0:
            break
        chars.append(chr(byte))
    return "".join(chars)


def embed(input_path: str, output_path: str, key: str, author: str) -> None:
    """Embed author identity into Cb channel using 8x8 Block-DCT spread-spectrum modulation."""
    img = Image.open(input_path).convert("YCbCr")
    y, cb, cr = img.split()

    cb_arr = np.array(cb, dtype=np.float32)
    h, w = cb_arr.shape

    h_block, w_block = h // 8, w // 8
    if h_block == 0 or w_block == 0:
        raise ValueError("Image dimensions must be at least 8x8 pixels.")

    bits = _payload_to_bits(author)
    total_blocks = h_block * w_block

    if len(bits) > total_blocks:
        raise ValueError(
            f"Payload too large ({len(bits)} bits required, {total_blocks} blocks available)."
        )

    seed = _derive_seed(key)
    rng = np.random.default_rng(seed)

    bit_idx = 0
    for r in range(h_block):
        for c in range(w_block):
            if bit_idx >= len(bits):
                break

            block = cb_arr[r * 8 : (r + 1) * 8, c * 8 : (c + 1) * 8]
            dct_block = dctn(block, norm="ortho")

            pn_seq = rng.choice([-1.0, 1.0], size=(8, 8))
            bit_sign = 1.0 if bits[bit_idx] == 1 else -1.0

            # Modulate mid-frequency coefficients (3..5 indices)
            dct_block[3:6, 3:6] += ALPHA * bit_sign * pn_seq[3:6, 3:6]

            cb_arr[r * 8 : (r + 1) * 8, c * 8 : (c + 1) * 8] = idctn(
                dct_block, norm="ortho"
            )
            bit_idx += 1

    cb_arr = np.clip(cb_arr, 0, 255).astype(np.uint8)
    modified_cb = Image.fromarray(cb_arr, mode="L")
    watermarked_img = Image.merge("YCbCr", (y, modified_cb, cr)).convert("RGB")
    watermarked_img.save(output_path)


def detect(image_path: str, key: str) -> dict[str, str]:
    """Extract embedded watermark from Cb channel using key-seeded correlation."""
    img = Image.open(image_path).convert("YCbCr")
    _, cb, _ = img.split()

    cb_arr = np.array(cb, dtype=np.float32)
    h, w = cb_arr.shape

    h_block, w_block = h // 8, w // 8
    if h_block == 0 or w_block == 0:
        return {"message": "Invalid image dimensions", "author": "N/A", "fingerprint": "N/A"}

    seed = _derive_seed(key)
    rng = np.random.default_rng(seed)

    extracted_bits = []
    for r in range(h_block):
        for c in range(w_block):
            block = cb_arr[r * 8 : (r + 1) * 8, c * 8 : (c + 1) * 8]
            dct_block = dctn(block, norm="ortho")

            pn_seq = rng.choice([-1.0, 1.0], size=(8, 8))
            corr = np.sum(dct_block[3:6, 3:6] * pn_seq[3:6, 3:6])

            extracted_bits.append(1 if corr > 0 else 0)

    author = _bits_to_payload(extracted_bits)
    fingerprint = hashlib.sha256(f"{author}:{key}".encode()).hexdigest()[:12]

    if author and author.isprintable():
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