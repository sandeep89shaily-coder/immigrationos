"""Run ONLY fictional IMM 5476 prefill experiment against a pinned official blank.

Usage:
  pip install -e ".[test]"
  python -m scripts.try_imm5476_poc --input /path/to/imm5476e.pdf \
    --output /path/to/imm5476-fictional-UNVALIDATED.pdf

No user fields, client records, signing or submission are exposed.
"""
import argparse
import json
from pathlib import Path

from app.imm5476_official_poc import generate_fictional_imm5476, IMM5476ExperimentBlocked


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = generate_fictional_imm5476(args.input, args.output)
    except (IMM5476ExperimentBlocked, OSError) as exc:
        print("IMM5476 synthetic demonstration blocked:", str(exc))
        return 1
    print(json.dumps(report, sort_keys=True, indent=2))
    print("OPEN IN ADOBE READER FOR MANUAL VISUAL/BEHAVIOUR CHECK. DO NOT SUBMIT.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
