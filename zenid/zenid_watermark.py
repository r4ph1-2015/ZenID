#!/usr/bin/env python3
import argparse
import sys
from zenid.zenid_core import embed, get_author_fingerprint

def main() -> None:
    parser = argparse.ArgumentParser(description="Embed a cryptographic ZenID watermark.")
    parser.add_argument("input", help="Path to input image")
    parser.add_argument("output", help="Path to output watermarked image")
    parser.add_argument("--key", required=True, help="Secret key used to sign watermark")
    parser.add_argument("--author", default="Pixeldaguy", help="Author identity string")

    args = parser.parse_args()

    try:
        embed(args.input, args.output, args.key, args.author)
        fp = get_author_fingerprint(args.key)
        print(f"✔ ZenID Watermark Embedded Successfully!")
        print(f"  Author Identity   : {args.author}")
        print(f"  Public Fingerprint: {fp}")
        print(f"  Saved Image To    : {args.output}")
    except Exception as exc:
        print(f"Error while watermarking: {exc}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()