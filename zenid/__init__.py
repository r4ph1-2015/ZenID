"""
ZenID: High-Security Multi-Modal Watermarking Suite
---------------------------------------------------
Professional-grade steganographic engine supporting images, text, and audio
with cryptographic HMAC-SHA256 integrity checks and zero-residue extraction.
"""

from __future__ import annotations

from .zenid_core import embed as embed_image, detect as detect_image
from .zenid_text import embed_text, detect_text
from .zenid_audio import embed_audio, detect_audio

__version__ = "1.3"
__author__ = "Pixeldaguy"

__all__ = [
    "embed_image",
    "detect_image",
    "embed_text",
    "detect_text",
    "embed_audio",
    "detect_audio",
]