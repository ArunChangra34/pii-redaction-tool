from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Sequence


PRIORITY: Dict[str, int] = {
    "EMAIL": 100,
    "IP_ADDRESS": 98,
    "CREDIT_CARD": 96,
    "SSN": 95,
    "AADHAAR": 94,
    "PAN": 93,
    "CIN": 92,
    "DIN": 91,
    "REG_ID": 89,
    "PHONE": 90,
    "URL": 80,
    "DATE_OF_BIRTH": 70,
    "ADDRESS": 50,
    "PERSON": 40,
    "ORG": 30,
}

REQUIRED_TYPES: Sequence[str] = (
    "PERSON",
    "EMAIL",
    "PHONE",
    "ORG",
    "ADDRESS",
    "SSN",
    "CREDIT_CARD",
    "DATE_OF_BIRTH",
    "IP_ADDRESS",
)


@dataclass(frozen=True)
class Span:

    start: int
    end: int
    pii_type: str
    text: str
    detector: str = ""
    confidence: float = 1.0

    def __post_init__(self) -> None:
        if self.end <= self.start:
            raise ValueError(f"empty or inverted span: {self!r}")

    @property
    def priority(self) -> int:
        return PRIORITY.get(self.pii_type, 0)

    def overlaps(self, other: "Span") -> bool:
        return self.start < other.end and other.start < self.end


class Detector:

    pii_type: str = ""
    name: str = ""

    needs_fit: bool = False

    def fit(self, full_text: str, context: dict) -> None:
        pass

    def detect(self, text: str, context: dict) -> Iterable[Span]:
        raise NotImplementedError

    def _span(self, start: int, end: int, text: str, confidence: float = 1.0) -> Span:
        return Span(
            start=start,
            end=end,
            pii_type=self.pii_type,
            text=text[start:end],
            detector=self.name or type(self).__name__,
            confidence=confidence,
        )


_REGISTRY: List[Callable[[], Detector]] = []


def register(cls):
    _REGISTRY.append(cls)
    return cls


def build_detectors(enabled: Sequence[str] | None = None) -> List[Detector]:
    detectors = [cls() for cls in _REGISTRY]
    if enabled is not None:
        allowed = {t.upper() for t in enabled}
        detectors = [d for d in detectors if d.pii_type in allowed]
    return detectors


def resolve_overlaps(spans: Iterable[Span]) -> List[Span]:
    ordered = sorted(
        spans,
        key=lambda s: (-s.priority, -(s.end - s.start), s.start),
    )
    kept: List[Span] = []
    for span in ordered:
        if not any(span.overlaps(k) for k in kept):
            kept.append(span)
    return sorted(kept, key=lambda s: s.start)


def apply_spans(text: str, spans: Sequence[Span], replace: Callable[[Span], str]) -> str:
    out: List[str] = []
    cursor = 0
    for span in sorted(spans, key=lambda s: s.start):
        if span.start < cursor:
            continue
        out.append(text[cursor : span.start])
        out.append(replace(span))
        cursor = span.end
    out.append(text[cursor:])
    return "".join(out)
