#!/usr/bin/env python3
import argparse
import sys
from zenid.zenid_core import detect

def main() -> None:
    parser = argparse.ArgumentParser(description="Detect and verify ZenID cryptographic watermark.")
    parser.add_argument("image", help="Path to image file")
    parser.add_argument("--key", required=True, help="Secret key to verify signature")

    args = parser.parse_args()

    try:
        result = detect(args.image, args.key)
    except Exception as exc:
        print(f"Error checking image: {exc}", file=sys.stderr)
        sys.exit(1)

    print("\n--- ZENID CRYPTOGRAPHIC VERIFICATION RESULT ---")
    if result["present"] and result["crypto_verified"]:
        print("Status             : WATERMARK DETECTED & AUTHENTICATED ✔")
        print(f"Claimed Author     : {result['author']}")
        print(f"Public Fingerprint : {result['fingerprint']}")
        print(f"Cryptographic Lock : HMAC-SHA256 Match")
        sys.exit(0)
    else:
        print("Status             : NO WATERMARK OR TAMPERED SIGNATURE ✖")
        print(f"Details            : {result['message']}")
        sys.exit(2)

if __name__ == "__main__":
    main()