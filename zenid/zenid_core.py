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

MAGIC_HEADER = b"ZID7"        # 4-byte signature identifier
AUTHOR_LEN = 20               # Fixed buffer size for author string
ALPHA_CB = 14.0               # Chrominance embedding strength per block
DCT_POSITIONS = [(1, 2), (2, 1), (2, 2), (3, 1)]  # Mid-frequency 8x8 DCT slots


def get_author_fingerprint(key: str) -> str:
    """Derives an immutable public identity fingerprint from secret key."""
    raw = hashlib.sha256(f"zenid_identity:{key}".encode("utf-8")).hexdigest()
    return f"ZID-{raw[:8].upper()}-{raw[8:12].upper()}"


def _generate_payload(key: str, author: str) -> tuple[bytes, str]:
    """Builds payload: [MAGIC (4b)] [LEN (1b)] [AUTHOR (20b)] [FP (6b)] [HMAC (8b)]."""
    fingerprint = get_author_fingerprint(key)
    fp_clean = fingerprint.replace("ZID-", "").replace("-", "")
    fp_bytes = bytes.fromhex(fp_clean)

    author_bytes = author.encode("utf-8")[:AUTHOR_LEN]
    actual_len = len(author_bytes)
    author_padded = author_bytes.ljust(AUTHOR_LEN, b"\x00")

    data_to_sign = MAGIC_HEADER + bytes([actual_len]) + author_padded + fp_bytes
    sig = hmac.new(key.encode("utf-8"), data_to_sign, hashlib.sha256).digest()[:8]
    return data_to_sign + sig, fingerprint


def _bytes_to_bits(data: bytes) -> np.ndarray:
    bits = []
    for byte in data:
        for i in range(7, -1, -1):
            bit_val = (byte >> i) & 1
            bits.append(1.0 if bit_val == 1 else -1.0)
    return np.array(bits, dtype=np.float32)


def _bits_to_bytes(bits: np.ndarray) -> bytes:
    byte_list = []
    for i in range(0, len(bits), 8):
        chunk = bits[i:i+8]
        if len(chunk) < 8:
            break
        byte_val = 0
        for b in chunk:
            byte_val = (byte_val << 1) | (1 if b > 0 else 0)
        byte_list.append(byte_val)
    return bytes(byte_list)


def _load_ycbcr_channels(path: str) -> tuple[np.ndarray, np.ndarray, np.ndarray, tuple[int, int]]:
    img = Image.open(path).convert("RGB")
    ycbcr = img.convert("YCbCr")
    y, cb, cr = ycbcr.split()
    return (
        np.asarray(y, dtype=np.float32),
        np.asarray(cb, dtype=np.float32),
        np.asarray(cr, dtype=np.float32),
        img.size,
    )


def embed(input_path: str, output_path: str, key: str, author: str = "Anonymous") -> None:
    y_full, cb_full, cr_full, (orig_w, orig_h) = _load_ycbcr_channels(input_path)

    # 1. Build payload bits
    payload_bytes, _ = _generate_payload(key, author)
    bits = _bytes_to_bits(payload_bytes)
    num_bits = len(bits)

    # 2. Split native Cb channel into 8x8 blocks
    H, W = cb_full.shape
    h_blocks, w_blocks = H // 8, W // 8
    total_blocks = h_blocks * w_blocks

    if total_blocks < num_bits:
        raise ValueError("Image resolution is too small to embed ZenID payload.")

    blocks = cb_full[:h_blocks * 8, :w_blocks * 8].reshape(h_blocks, 8, w_blocks, 8).swapaxes(1, 2)
    blocks_flat = blocks.reshape(total_blocks, 8, 8)

    # 3. 2D Block-DCT on Cb blocks
    coeffs = dctn(blocks_flat, axes=(-2, -1), norm="ortho")

    # 4. PRNG Pseudo-random sign matrix
    seed_val = int(hashlib.sha256(f"zenid_carrier:{key}".encode("utf-8")).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed_val)
    prn_signs = rng.choice([-1.0, 1.0], size=total_blocks).astype(np.float32)

    # 5. Modulate mid-frequency coefficients across blocks
    bit_indices = np.arange(total_blocks) % num_bits
    block_bits = bits[bit_indices]
    modulation = ALPHA_CB * block_bits * prn_signs

    for u, v in DCT_POSITIONS:
        coeffs[:, u, v] += modulation

    # 6. IDCT to reconstruct Cb channel
    blocks_wm = idctn(coeffs, axes=(-2, -1), norm="ortho")
    cb_wm = cb_full.copy()
    cb_wm_blocks = blocks_wm.reshape(h_blocks, w_blocks, 8, 8).swapaxes(1, 2).reshape(h_blocks * 8, w_blocks * 8)
    cb_wm[:h_blocks * 8, :w_blocks * 8] = np.clip(cb_wm_blocks, 0, 255)

    # Recombine (Y channel is 100% untouched)
    y_out = Image.fromarray(y_full.astype(np.uint8))
    cb_out = Image.fromarray(cb_wm.astype(np.uint8))
    cr_out = Image.fromarray(cr_full.astype(np.uint8))

    watermarked = Image.merge("YCbCr", (y_out, cb_out, cr_out)).convert("RGB")
    watermarked.save(output_path, quality=98)


def detect(path: str, key: str) -> dict:
    _, cb_full, _, _ = _load_ycbcr_channels(path)

    H, W = cb_full.shape
    h_blocks, w_blocks = H // 8, W // 8
    total_blocks = h_blocks * w_blocks

    num_bits = 312  # 39 payload bytes * 8 bits
    if total_blocks < num_bits:
        return {
            "present": False,
            "author": "Unknown",
            "fingerprint": "N/A",
            "crypto_verified": False,
            "message": "Image resolution too small.",
        }

    blocks = cb_full[:h_blocks * 8, :w_blocks * 8].reshape(h_blocks, 8, w_blocks, 8).swapaxes(1, 2)
    blocks_flat = blocks.reshape(total_blocks, 8, 8)

    coeffs = dctn(blocks_flat, axes=(-2, -1), norm="ortho")

    seed_val = int(hashlib.sha256(f"zenid_carrier:{key}".encode("utf-8")).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed_val)
    prn_signs = rng.choice([-1.0, 1.0], size=total_blocks).astype(np.float32)

    extracted_signal = np.zeros(total_blocks, dtype=np.float32)
    for u, v in DCT_POSITIONS:
        extracted_signal += coeffs[:, u, v]

    weighted_signal = extracted_signal * prn_signs
    accumulators = np.zeros(num_bits, dtype=np.float32)
    bit_indices = np.arange(total_blocks) % num_bits

    np.add.at(accumulators, bit_indices, weighted_signal)
    extracted_bits = np.where(accumulators > 0, 1.0, -1.0)

    raw_bytes = _bits_to_bytes(extracted_bits)

    if len(raw_bytes) < 39 or raw_bytes[:4] != MAGIC_HEADER:
        return {
            "present": False,
            "author": "Unknown",
            "fingerprint": "N/A",
            "crypto_verified": False,
            "message": "No valid ZenID header found.",
        }

    author_len = raw_bytes[4]
    author_bytes = raw_bytes[5 : 5 + AUTHOR_LEN][:author_len]
    fp_raw = raw_bytes[5 + AUTHOR_LEN : 5 + AUTHOR_LEN + 6]
    extracted_fp = f"ZID-{fp_raw[:4].hex().upper()}-{fp_raw[4:6].hex().upper()}"
    received_hmac = raw_bytes[5 + AUTHOR_LEN + 6 : 39]

    author_padded = raw_bytes[5 : 5 + AUTHOR_LEN]
    signed_data = MAGIC_HEADER + bytes([author_len]) + author_padded + fp_raw

    expected_hmac = hmac.new(key.encode("utf-8"), signed_data, hashlib.sha256).digest()[:8]

    try:
        author_str = author_bytes.decode("utf-8")
    except UnicodeDecodeError:
        author_str = "Corrupted Author Text"

    is_verified = hmac.compare_digest(received_hmac, expected_hmac)

    return {
        "present": is_verified,
        "author": author_str if is_verified else "UNVERIFIED",
        "fingerprint": extracted_fp,
        "crypto_verified": is_verified,
        "message": "HMAC-SHA256 Authenticated!" if is_verified else "Signature Mismatch!",
    }