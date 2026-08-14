from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from docx import Document

from .core import Span, build_detectors, resolve_overlaps, apply_spans
from .detectors import optional_ner_layer
from .docx_io import (
    RedactionStats,
    extract_full_text,
    harvest_table_person_seeds,
    iter_all_paragraphs,
    paragraph_text,
    rewrite_field_codes,
    rewrite_hyperlink_targets,
    rewrite_paragraph,
)
from .surrogates import SurrogateBank


@dataclass
class RedactionResult:
    stats: RedactionStats
    spans: List[Span] = field(default_factory=list)
    bank: Optional[SurrogateBank] = None
    ner_used: bool = False

    def counts_by_type(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for span in self.spans:
            out[span.pii_type] = out.get(span.pii_type, 0) + 1
        return dict(sorted(out.items(), key=lambda kv: -kv[1]))


class Redactor:

    def __init__(
        self,
        enabled_types: Optional[Sequence[str]] = None,
        seed: int = 20250810,
        use_ner: bool = True,
        ner_model: str = "en_core_web_lg",
    ) -> None:
        self.detectors = build_detectors(enabled_types)
        self.bank = SurrogateBank(seed=seed)
        self.use_ner = use_ner
        self.ner_model = ner_model
        self.context: dict = {}
        self.ner_used = False

    def fit(self, full_text: str, extra_person_seeds: Optional[set] = None) -> None:
        self.context = {"person_seeds": set(extra_person_seeds or set())}

        if self.use_ner:
            ner = optional_ner_layer(full_text, self.ner_model)
            self.ner_used = bool(ner["ner_persons"] or ner["ner_orgs"])
            self.context.update(ner)

        order = {"PERSON": 0, "ORG": 1, "ADDRESS": 2}
        for detector in sorted(self.detectors, key=lambda d: order.get(d.pii_type, 9)):
            if detector.needs_fit:
                detector.fit(full_text, self.context)

        real_tokens = set(self.context.get("person_tokens", set()))
        for group in ("person_names", "org_names", "address_components"):
            for value in self.context.get(group, []):
                real_tokens.update(t.strip(".,'-") for t in value.split())
        self.bank.forbid(real_tokens)

        self.bank.register_people(self.context.get("person_names", []))
        self.bank.register_orgs(self.context.get("org_names", []))

    def detect(self, text: str) -> List[Span]:
        spans: List[Span] = []
        for detector in self.detectors:
            spans.extend(detector.detect(text, self.context))
        return resolve_overlaps(spans)

    def _replace(self, span: Span) -> str:
        return self.bank.surrogate_for(span.pii_type, span.text)

    def redact_text(self, text: str) -> str:
        return apply_spans(text, self.detect(text), self._replace)

    def redact_docx(self, in_path: Path, out_path: Path) -> RedactionResult:
        doc = Document(str(in_path))
        full_text = extract_full_text(doc)
        self.fit(full_text, extra_person_seeds=harvest_table_person_seeds(doc))

        stats = RedactionStats()
        all_spans: List[Span] = []

        for para in iter_all_paragraphs(doc):
            text = paragraph_text(para)
            stats.paragraphs_scanned += 1
            if not text.strip():
                continue
            spans = self.detect(text)
            if not spans:
                continue
            all_spans.extend(spans)
            applied = rewrite_paragraph(para, spans, self._replace)
            if applied:
                stats.paragraphs_changed += 1
                stats.spans_replaced += applied

        stats.field_codes_changed = rewrite_field_codes(doc, self.redact_text)
        stats.hyperlinks_changed = rewrite_hyperlink_targets(
            doc,
            replace_email=lambda v: self.bank.surrogate_for("EMAIL", v),
            replace_url=lambda v: self.bank.surrogate_for("URL", v),
        )

        out_path.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(out_path))
        return RedactionResult(stats=stats, spans=all_spans, bank=self.bank, ner_used=self.ner_used)

    def write_audit(self, result: RedactionResult, path: Path) -> None:
        with path.open("w", encoding="utf-8") as fh:
            for span in result.spans:
                fh.write(
                    json.dumps(
                        {
                            "type": span.pii_type,
                            "detector": span.detector,
                            "confidence": round(span.confidence, 3),
                            "original": span.text,
                            "surrogate": self.bank.surrogate_for(span.pii_type, span.text),
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
