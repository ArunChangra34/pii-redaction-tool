from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pii_redactor.core import REQUIRED_TYPES
from pii_redactor.pipeline import Redactor


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="redact.py",
        description="Replace personally identifiable information in a .docx with consistent fakes.",
    )
    p.add_argument("input", type=Path, help="source .docx")
    p.add_argument("-o", "--output", type=Path, default=None, help="destination .docx")
    p.add_argument("--mapping", type=Path, default=None, help="write the real->fake mapping here")
    p.add_argument("--audit", type=Path, default=None, help="write a JSONL audit log here")
    p.add_argument("--seed", type=int, default=20250810, help="surrogate seed (default: %(default)s)")
    p.add_argument(
        "--types",
        nargs="+",
        default=None,
        metavar="TYPE",
        help=f"only redact these types (default: all). Required set: {', '.join(REQUIRED_TYPES)}",
    )
    p.add_argument(
        "--no-ner",
        action="store_true",
        help="skip the optional spaCy NER layer even if a model is installed",
    )
    p.add_argument("--ner-model", default="en_core_web_lg", help="spaCy model name")
    p.add_argument("-q", "--quiet", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if not args.input.exists():
        print(f"error: {args.input} not found", file=sys.stderr)
        return 2

    output = args.output or args.input.with_name(args.input.stem + " (redacted).docx")

    redactor = Redactor(
        enabled_types=args.types,
        seed=args.seed,
        use_ner=not args.no_ner,
        ner_model=args.ner_model,
    )
    result = redactor.redact_docx(args.input, output)

    if args.mapping:
        redactor.bank.save_mapping(args.mapping)
    if args.audit:
        redactor.write_audit(result, args.audit)

    if not args.quiet:
        s = result.stats
        print(f"input   : {args.input}")
        print(f"output  : {output}")
        print(f"NER     : {'spaCy model active' if result.ner_used else 'rule layer only'}")
        print(f"scanned : {s.paragraphs_scanned} paragraphs "
              f"({s.paragraphs_changed} modified)")
        print(f"replaced: {s.spans_replaced} PII mentions")
        print("\nby type:")
        for pii_type, count in result.counts_by_type().items():
            print(f"  {pii_type:<15} {count:>6}")
        missing = [t for t in REQUIRED_TYPES if t not in result.counts_by_type()]
        if missing:
            print("\nrequired types with no detections in this document:")
            print("  " + ", ".join(missing))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
