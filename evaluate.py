from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

from pii_redactor.core import REQUIRED_TYPES
from pii_redactor.pipeline import Redactor

EVAL_DIR = Path(__file__).parent / "eval"
TOKEN_RE = re.compile(r"\w+|[^\w\s]")
OUTSIDE = "O"


def tokenize(text: str) -> List[Tuple[str, int, int]]:
    return [(m.group(0), m.start(), m.end()) for m in TOKEN_RE.finditer(text)]


def label_tokens(
    tokens: Sequence[Tuple[str, int, int]],
    spans: Sequence[Tuple[int, int, str]],
) -> List[str]:
    labels = [OUTSIDE] * len(tokens)
    for i, (_, start, end) in enumerate(tokens):
        for s_start, s_end, s_type in spans:
            if start < s_end and s_start < end:
                labels[i] = s_type
                break
    return labels


def gold_spans(text: str, annotations: Sequence[Sequence[str]]) -> List[Tuple[int, int, str]]:
    spans: List[Tuple[int, int, str]] = []
    for mention, pii_type in annotations:
        start = text.find(mention)
        if start == -1:
            raise ValueError(f"gold mention not found in paragraph: {mention!r}")
        while start != -1:
            spans.append((start, start + len(mention), pii_type))
            start = text.find(mention, start + len(mention))
    return spans


def score(gold: Sequence[str], pred: Sequence[str]) -> Dict:
    types = sorted({t for t in list(gold) + list(pred) if t != OUTSIDE})
    tp, fp, fn = Counter(), Counter(), Counter()

    for g, p in zip(gold, pred):
        if g == p:
            if g != OUTSIDE:
                tp[g] += 1
        else:
            if p != OUTSIDE:
                fp[p] += 1
            if g != OUTSIDE:
                fn[g] += 1

    def prf(t: int, f_p: int, f_n: int) -> Tuple[float, float, float]:
        precision = t / (t + f_p) if t + f_p else 0.0
        recall = t / (t + f_n) if t + f_n else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        return precision, recall, f1

    per_type = {}
    for pii_type in types:
        precision, recall, f1 = prf(tp[pii_type], fp[pii_type], fn[pii_type])
        per_type[pii_type] = {
            "support": tp[pii_type] + fn[pii_type],
            "tp": tp[pii_type],
            "fp": fp[pii_type],
            "fn": fn[pii_type],
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        }

    micro = prf(sum(tp.values()), sum(fp.values()), sum(fn.values()))
    scored = [t for t in types if per_type[t]["support"] > 0]
    macro = tuple(
        sum(per_type[t][k] for t in scored) / len(scored) if scored else 0.0
        for k in ("precision", "recall", "f1")
    )
    correct = sum(1 for g, p in zip(gold, pred) if g == p)

    return {
        "tokens": len(gold),
        "pii_tokens_gold": sum(1 for g in gold if g != OUTSIDE),
        "pii_tokens_pred": sum(1 for p in pred if p != OUTSIDE),
        "accuracy": round(correct / len(gold), 4) if gold else 0.0,
        "micro": {"precision": round(micro[0], 4), "recall": round(micro[1], 4), "f1": round(micro[2], 4)},
        "macro": {"precision": round(macro[0], 4), "recall": round(macro[1], 4), "f1": round(macro[2], 4)},
        "per_type": per_type,
    }


SYNTHETIC_CASES: List[Tuple[str, List[Tuple[str, str]]]] = [
    ("Her SSN is 123-45-6789 and the backup card is 4111 1111 1111 1111.",
     [("123-45-6789", "SSN"), ("4111 1111 1111 1111", "CREDIT_CARD")]),
    ("Date of birth: 14/07/1982. Login from 203.0.113.45 at 09:12.",
     [("14/07/1982", "DATE_OF_BIRTH"), ("203.0.113.45", "IP_ADDRESS")]),
    ("Rashi Patil (born on March 3, 1979) can be reached at rashhi.patil@gmail.com or +91 9876543210.",
     [("March 3, 1979", "DATE_OF_BIRTH"), ("rashhi.patil@gmail.com", "EMAIL"), ("+91 9876543210", "PHONE")]),
    ("Ship it to 1600 Pennsylvania Avenue NW, Washington, DC 20500 by Friday.",
     [("1600 Pennsylvania Avenue NW, Washington, DC 20500", "ADDRESS")]),
    ("Aadhaar 2994 1234 5678 and PAN ABCPD1234E are on file.",
     [("2994 1234 5678", "AADHAAR"), ("ABCPD1234E", "PAN")]),
    ("Order 4111111111111112 shipped on ticket 100200300 for Fiscal 2025.", []),
    ("Refer to page 280 and section 12(1) of the Companies Act, 2013.", []),
    ("The resolution passed on May 6, 2025 was filed with the Registrar of Companies.", []),
]


def run_synthetic(redactor: Redactor) -> Dict:
    gold_labels: List[str] = []
    pred_labels: List[str] = []
    failures: List[Dict] = []

    corpus = "\n".join(text for text, _ in SYNTHETIC_CASES)
    redactor.fit(corpus)

    for text, annotations in SYNTHETIC_CASES:
        tokens = tokenize(text)
        g = label_tokens(tokens, gold_spans(text, annotations))
        p = label_tokens(tokens, [(s.start, s.end, s.pii_type) for s in redactor.detect(text)])
        gold_labels += g
        pred_labels += p
        if g != p:
            failures.append({
                "text": text,
                "expected": sorted({x for x in g if x != OUTSIDE}),
                "detected": sorted({x for x in p if x != OUTSIDE}),
            })

    result = score(gold_labels, pred_labels)
    result["failures"] = failures
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate the PII redactor.")
    parser.add_argument("--sample", type=Path, default=EVAL_DIR / "sample.json")
    parser.add_argument("--gold", type=Path, default=EVAL_DIR / "gold.json")
    parser.add_argument("--out", type=Path, default=EVAL_DIR / "results.json")
    parser.add_argument("--source", type=Path, default=None,
                        help="source .docx used to fit the gazetteers (recommended)")
    parser.add_argument("--no-ner", action="store_true")
    parser.add_argument("--unit-tests", action="store_true", help="also run the synthetic suite")
    args = parser.parse_args()

    paragraphs: List[str] = json.loads(args.sample.read_text(encoding="utf-8"))
    gold_doc = json.loads(args.gold.read_text(encoding="utf-8"))
    annotations = {int(k): v for k, v in gold_doc["annotations"].items()}

    redactor = Redactor(use_ner=not args.no_ner)
    if args.source is not None:
        from docx import Document
        from pii_redactor.docx_io import extract_full_text, harvest_table_person_seeds

        doc = Document(str(args.source))
        redactor.fit(extract_full_text(doc), harvest_table_person_seeds(doc))
    else:
        redactor.fit("\n".join(paragraphs))

    gold_labels: List[str] = []
    pred_labels: List[str] = []
    stratum: Dict[str, List[Tuple[str, str]]] = defaultdict(list)
    errors: List[Dict] = []

    for index, text in enumerate(paragraphs):
        tokens = tokenize(text)
        g = label_tokens(tokens, gold_spans(text, annotations.get(index, [])))
        p = label_tokens(tokens, [(s.start, s.end, s.pii_type) for s in redactor.detect(text)])
        gold_labels += g
        pred_labels += p
        name = "A_pii_dense" if index < 70 else "B_random_prose"
        stratum[name] += list(zip(g, p))

        for (token, _, _), gl, pl in zip(tokens, g, p):
            if gl != pl:
                errors.append({
                    "paragraph": index,
                    "token": token,
                    "gold": gl,
                    "pred": pl,
                    "kind": "FN" if pl == OUTSIDE else ("FP" if gl == OUTSIDE else "TYPE_CONFUSION"),
                })

    results = {
        "overall": score(gold_labels, pred_labels),
        "by_stratum": {
            name: score([g for g, _ in pairs], [p for _, p in pairs])
            for name, pairs in stratum.items()
        },
        "required_types_absent_from_gold_sample": [
            t for t in REQUIRED_TYPES if results_support(gold_labels, t) == 0
        ],
        "errors": errors,
    }

    if args.unit_tests:
        results["synthetic"] = run_synthetic(Redactor(use_ner=not args.no_ner))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, indent=2), encoding="utf-8")

    overall = results["overall"]
    print(f"tokens evaluated : {overall['tokens']}")
    print(f"token accuracy   : {overall['accuracy']:.4f}")
    print(f"micro P/R/F1     : {overall['micro']['precision']:.4f} / "
          f"{overall['micro']['recall']:.4f} / {overall['micro']['f1']:.4f}")
    print(f"macro P/R/F1     : {overall['macro']['precision']:.4f} / "
          f"{overall['macro']['recall']:.4f} / {overall['macro']['f1']:.4f}")
    print("\nper type:")
    print(f"  {'type':<14}{'supp':>6}{'tp':>6}{'fp':>5}{'fn':>5}{'prec':>9}{'rec':>8}{'f1':>8}")
    for pii_type, m in sorted(overall["per_type"].items()):
        print(f"  {pii_type:<14}{m['support']:>6}{m['tp']:>6}{m['fp']:>5}{m['fn']:>5}"
              f"{m['precision']:>9.3f}{m['recall']:>8.3f}{m['f1']:>8.3f}")
    if results.get("synthetic"):
        s = results["synthetic"]
        print(f"\nsynthetic suite  : accuracy {s['accuracy']:.4f}, "
              f"{len(s['failures'])} failing case(s)")
    print(f"\nwrote {args.out}")
    return 0


def results_support(labels: Sequence[str], pii_type: str) -> int:
    return sum(1 for label in labels if label == pii_type)


if __name__ == "__main__":
    raise SystemExit(main())
