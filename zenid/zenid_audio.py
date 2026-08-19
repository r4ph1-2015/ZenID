"""
zenid_audio.py
--------------
ZenID LSB Spectrum Audio Watermarking Engine.
Modulates least-significant bits of PCM 16-bit audio samples to embed HMAC signatures without audible noise.
"""

import wave
import hashlib
import hmac
import numpy as np

MAGIC_HEADER = b"ZIDA"

def embed_audio(input_wav: str, output_wav: str, key: str, author: str) -> None:
    with wave.open(input_wav, 'rb') as wav_in:
        params = wav_in.getparams()
        frames = wav_in.readframes(wav_in.getnframes())
        
    samples = np.frombuffer(frames, dtype=np.int16).copy()
    
    sig = hmac.new(key.encode(), f"{author}".encode(), hashlib.sha256).digest()[:4]
    payload = MAGIC_HEADER + len(author).to_bytes(1, 'big') + author.encode()[:20].ljust(20, b'\x00') + sig
    
    # Convert payload bytes to bits
    bits = []
    for b in payload:
        for i in range(7, -1, -1):
            bits.append((b >> i) & 1)
            
    if len(bits) > len(samples):
        raise ValueError("Audio clip is too short to hold the watermark payload.")
        
    # Inject into least significant bit of audio samples
    for i, bit in enumerate(bits):
        samples[i] = (samples[i] & ~1) | bit
        
    with wave.open(output_wav, 'wb') as wav_out:
        wav_out.setparams(params)
        wav_out.writeframes(samples.tobytes())

def detect_audio(wav_path: str, key: str) -> dict:
    with wave.open(wav_path, 'rb') as wav_in:
        frames = wav_in.readframes(wav_in.getnframes())
        
    samples = np.frombuffer(frames, dtype=np.int16)
    
    payload_bit_len = (4 + 1 + 20 + 4) * 8
    if len(samples) < payload_bit_len:
        return {"present": False, "message": "Audio file too short."}
        
    bits = [samples[i] & 1 for i in range(payload_bit_len)]
    
    # Reconstruct bytes
    byte_list = []
    for i in range(0, len(bits), 8):
        byte_val = 0
        for b in bits[i:i+8]:
            byte_val = (byte_val << 1) | b
        byte_list.append(byte_val)
        
    raw = bytes(byte_list)
    if raw[:4] != MAGIC_HEADER:
        return {"present": False, "message": "No ZenID audio signature detected."}
        
    author_len = raw[4]
    author = raw[5:25][:author_len].decode('utf-8', errors='ignore')
    received_sig = raw[25:29]
    
    expected_sig = hmac.new(key.encode(), f"{author}".encode(), hashlib.sha256).digest()[:4]
    verified = hmac.compare_digest(received_sig, expected_sig)
    
    return {
        "present": verified,
        "author": author if verified else "UNVERIFIED",
        "crypto_verified": verified,
        "message": "HMAC-SHA256 Audio Signature Authenticated!" if verified else "Invalid Key or Tampered Audio."
    }