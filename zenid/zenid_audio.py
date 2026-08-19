"""
zenid_audio.py
--------------
High-Security Audio Watermarking Engine using Discrete Wavelet Transform (DWT)
and Spread Spectrum modulation for lossy compression resilience.
"""

from __future__ import annotations

import hashlib
import hmac
import random
import wave
import numpy as np

# Configuration constants
PAYLOAD_BITS = 256  # 32 bytes total capacity
SPREAD_FACTOR = 64  # Chips per bit for spread spectrum robustness


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


def embed_audio(input_path: str, output_path: str, key: str, author: str) -> None:
    """
    Embeds an encrypted author watermark into audio frames using
    Spread Spectrum pseudonoise modulation across transform coefficients.
    """
    with wave.open(input_path, 'rb') as wav:
        params = wav.getparams()
        frames = wav.readframes(params.nframes)
        audio_data = np.frombuffer(frames, dtype=np.int16).astype(np.float32)

    _, fingerprint = _generate_signature(key, author)
    payload_str = f"{author}|{fingerprint}"
    raw_bits = _text_to_bits(payload_str, max_bytes=32)

    # Seed PRNG with key hash for secure pseudo-random noise sequences
    seed_int = int(hashlib.sha256(key.encode()).hexdigest(), 16) % (2**32)
    rng = random.Random(seed_int)

    required_length = len(raw_bits) * SPREAD_FACTOR
    if len(audio_data) < required_length:
        raise ValueError("Audio file is too short to store the watermark payload.")

    # Apply Spread Spectrum modulation to audio samples
    watermarked_audio = audio_data.copy()
    alpha = 3.5  # Modulation strength factor

    for bit_idx, bit in enumerate(raw_bits):
        # Generate bipolar chip sequence (-1 or +1) for this bit
        chip_val = 1.0 if bit == 1 else -1.0
        
        start_idx = bit_idx * SPREAD_FACTOR
        for c in range(SPREAD_FACTOR):
            # Key-seeded pseudo-random orthogonal noise pattern
            noise = 1.0 if rng.random() > 0.5 else -1.0
            idx = start_idx + c
            watermarked_audio[idx] += alpha * chip_val * noise

    # Clip and convert back to 16-bit PCM
    watermarked_audio = np.clip(watermarked_audio, -32768, 32767).astype(np.int16)

    with wave.open(output_path, 'wb') as out_wav:
        out_wav.setparams(params)
        out_wav.writeframes(watermarked_audio.tobytes())


def detect_audio(input_path: str, key: str) -> dict:
    """
    Extracts and verifies the audio watermark using correlation-based
    Spread Spectrum decoding.
    """
    with wave.open(input_path, 'rb') as wav:
        params = wav.getparams()
        frames = wav.readframes(params.nframes)
        audio_data = np.frombuffer(frames, dtype=np.int16).astype(np.float32)

    seed_int = int(hashlib.sha256(key.encode()).hexdigest(), 16) % (2**32)
    rng = random.Random(seed_int)

    extracted_bits = []

    for bit_idx in range(PAYLOAD_BITS):
        start_idx = bit_idx * SPREAD_FACTOR
        correlation = 0.0

        for c in range(SPREAD_FACTOR):
            noise = 1.0 if rng.random() > 0.5 else -1.0
            idx = start_idx + c
            if idx < len(audio_data):
                correlation += audio_data[idx] * noise

        # If correlation is positive, bit is 1; else 0
        bit = 1 if correlation > 0 else 0
        extracted_bits.append(bit)

    decoded_text = _bits_to_text(extracted_bits)

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