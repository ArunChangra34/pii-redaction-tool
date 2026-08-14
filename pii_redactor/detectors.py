from __future__ import annotations

import re
from typing import Dict, Iterable, List, Sequence, Set

from .core import Detector, Span, register
from .lexicons import (
    DEFINED_TERM_STOPWORDS,
    GENERIC_ORG_CORE_BLOCKLIST,
    HONORIFICS,
    INDIAN_STATES,
    NAME_PARTICLES,
    OFFER_MACHINERY_WORDS,
    ORG_SUFFIXES,
    PERSON_TOKEN_BLOCKLIST,
    PUBLIC_BODY_ALLOWLIST,
    STREET_KEYWORDS,
    STRONG_ORG_SUFFIXES,
    WEAK_ORG_SUFFIXES,
)

MONTHS = (
    "January|February|March|April|May|June|July|August|September|October|"
    "November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec"
)


def _luhn_ok(digits: str) -> bool:
    total, parity = 0, len(digits) % 2
    for i, ch in enumerate(digits):
        d = int(ch)
        if i % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


_VERHOEFF_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6], [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8], [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2], [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4], [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]
_VERHOEFF_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9], [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2], [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0], [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5], [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]


def _verhoeff_ok(digits: str) -> bool:
    c = 0
    for i, ch in enumerate(reversed(digits)):
        c = _VERHOEFF_D[c][_VERHOEFF_P[i % 8][int(ch)]]
    return c == 0


def _flexible(phrase: str) -> str:
    return r"\s+".join(re.escape(tok) for tok in phrase.split())


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


@register
class EmailDetector(Detector):
    pii_type = "EMAIL"
    name = "email.regex"

    _RE = re.compile(
        r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?"
        r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9\-]*[A-Za-z0-9])?)*\.[A-Za-z]{2,24}\b"
    )

    def detect(self, text: str, context: dict) -> Iterable[Span]:
        for m in self._RE.finditer(text):
            yield self._span(m.start(), m.end(), text)


@register
class URLDetector(Detector):

    pii_type = "URL"
    name = "url.regex"

    _RE = re.compile(r"\b(?:https?://|www\.)[A-Za-z0-9\-._~/?#\[\]@!$&'()*+,;=%]+", re.I)
    _PUBLIC_DOMAINS = (
        "sebi.gov.in", "bseindia.com", "nseindia.com", "rbi.org.in",
        "mca.gov.in", "fbil.org.in", "oanda.com", "cdslindia.com",
        "nsdl.co.in", "india.gov.in", "incometax.gov.in", "npci.org.in",
    )

    def detect(self, text: str, context: dict) -> Iterable[Span]:
        for m in self._RE.finditer(text):
            raw = m.group(0).rstrip(".,;:)")
            low = raw.lower()
            if any(d in low for d in self._PUBLIC_DOMAINS):
                continue
            yield self._span(m.start(), m.start() + len(raw), text, 0.9)


@register
class PhoneDetector(Detector):

    pii_type = "PHONE"
    name = "phone.regex"

    _INTL = re.compile(r"\+\s?\d{1,3}(?:[\s\-]?\(?\d{2,5}\)?){1,5}\d?")
    _LABELLED = re.compile(
        r"(?i)\b(?:tele\s?phone|telephone|tel|phone|mobile|mob|fax|contact\s*(?:no|number))"
        r"\s*(?:no\.?|number)?\s*[:\-]?\s*"
        r"(\+?\s?\d[\d\s\-\(\)]{7,20}\d)"
    )

    @staticmethod
    def _digits(s: str) -> str:
        return re.sub(r"\D", "", s)

    def _valid(self, raw: str) -> bool:
        n = len(self._digits(raw))
        return 8 <= n <= 15

    def detect(self, text: str, context: dict) -> Iterable[Span]:
        seen: Set[tuple] = set()
        for m in self._INTL.finditer(text):
            raw = m.group(0).rstrip(" -")
            if self._valid(raw):
                key = (m.start(), m.start() + len(raw))
                seen.add(key)
                yield self._span(key[0], key[1], text)
        for m in self._LABELLED.finditer(text):
            raw = m.group(1).rstrip(" -")
            start = m.start(1)
            end = start + len(raw)
            if self._valid(raw) and (start, end) not in seen:
                if not any(s <= start < e for s, e in seen):
                    yield self._span(start, end, text, 0.95)


@register
class IPAddressDetector(Detector):
    pii_type = "IP_ADDRESS"
    name = "ip.regex"

    _V4 = re.compile(
        r"(?<![\d.])((?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}"
        r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(?![\d.])"
    )
    _V6 = re.compile(r"(?<![:\w])(?:[A-Fa-f0-9]{1,4}:){2,7}[A-Fa-f0-9]{1,4}(?![:\w])")
    _VERSION_CUE = re.compile(r"(?i)\b(?:version|v|release|rev|build|ind as|as)\s*$")

    def detect(self, text: str, context: dict) -> Iterable[Span]:
        for m in self._V4.finditer(text):
            if self._VERSION_CUE.search(text[max(0, m.start() - 14) : m.start()]):
                continue
            yield self._span(m.start(), m.end(), text)
        for m in self._V6.finditer(text):
            if ":" in m.group(0) and m.group(0).count(":") >= 2:
                yield self._span(m.start(), m.end(), text, 0.85)


@register
class SSNDetector(Detector):

    pii_type = "SSN"
    name = "ssn.regex"

    _RE = re.compile(
        r"(?<!\d)(?!000|666|9\d\d)(\d{3})[-\s](?!00)(\d{2})[-\s](?!0000)(\d{4})(?!\d)"
    )
    _BARE = re.compile(r"(?i)\b(?:ssn|social security(?:\s+number)?)\s*[:#\-]?\s*(\d{9})\b")

    def detect(self, text: str, context: dict) -> Iterable[Span]:
        for m in self._RE.finditer(text):
            yield self._span(m.start(), m.end(), text)
        for m in self._BARE.finditer(text):
            yield self._span(m.start(1), m.end(1), text, 0.9)


@register
class CreditCardDetector(Detector):

    pii_type = "CREDIT_CARD"
    name = "credit_card.luhn"

    _RE = re.compile(r"(?<![\d.,])(?:\d[ -]?){12,18}\d(?![\d,])(?!\.\d)")

    def detect(self, text: str, context: dict) -> Iterable[Span]:
        for m in self._RE.finditer(text):
            raw = m.group(0)
            digits = re.sub(r"\D", "", raw)
            if not (13 <= len(digits) <= 19):
                continue
            if digits[0] not in "3456":
                continue
            if not _luhn_ok(digits):
                continue
            yield self._span(m.start(), m.end(), text)


@register
class AadhaarDetector(Detector):

    pii_type = "AADHAAR"
    name = "aadhaar.verhoeff"

    _RE = re.compile(r"(?<![\d.,])([2-9]\d{3})[ -]?(\d{4})[ -]?(\d{4})(?![\d.,])")

    def detect(self, text: str, context: dict) -> Iterable[Span]:
        for m in self._RE.finditer(text):
            digits = re.sub(r"\D", "", m.group(0))
            if len(digits) == 12 and _verhoeff_ok(digits):
                yield self._span(m.start(), m.end(), text)


@register
class PANDetector(Detector):

    pii_type = "PAN"
    name = "pan.regex"

    _RE = re.compile(r"\b[A-Z]{3}[ABCFGHLJPTKE][A-Z]\d{4}[A-Z]\b")

    def detect(self, text: str, context: dict) -> Iterable[Span]:
        for m in self._RE.finditer(text):
            yield self._span(m.start(), m.end(), text)


@register
class CINDetector(Detector):

    pii_type = "CIN"
    name = "cin.regex"

    _RE = re.compile(r"\b[LUlu]\d{5}[A-Za-z]{2}\d{4}[A-Za-z]{3}\d{6}\b")

    def detect(self, text: str, context: dict) -> Iterable[Span]:
        for m in self._RE.finditer(text):
            yield self._span(m.start(), m.end(), text)


@register
class DINDetector(Detector):

    pii_type = "DIN"
    name = "din.regex"

    _LABELLED = re.compile(
        r"(?i)\b(?:din|dpin|director identification number)\s*[:#\-]?\s*(\d{8})\b"
    )
    _BARE = re.compile(r"(?<![\w.,])(0\d{7})(?![\w.,])")

    def detect(self, text: str, context: dict) -> Iterable[Span]:
        seen: Set[int] = set()
        for m in self._LABELLED.finditer(text):
            seen.add(m.start(1))
            yield self._span(m.start(1), m.end(1), text)
        for m in self._BARE.finditer(text):
            if m.start(1) not in seen:
                yield self._span(m.start(1), m.end(1), text, 0.7)


@register
class RegistrationNumberDetector(Detector):

    pii_type = "REG_ID"
    name = "reg_id.regex"

    _RE = re.compile(r"\bIN[A-Z]{1,2}\d{8,11}\b")

    def detect(self, text: str, context: dict) -> Iterable[Span]:
        for m in self._RE.finditer(text):
            yield self._span(m.start(), m.end(), text)


@register
class DateOfBirthDetector(Detector):

    pii_type = "DATE_OF_BIRTH"
    name = "dob.contextual"

    _CUE = re.compile(
        r"(?i)\b(?:date of birth|d\.?o\.?b\.?|born on|born|birth ?date|birthday)\b"
    )
    _DATE = re.compile(
        rf"(?i)\b(?:"
        rf"\d{{1,2}}[/\-.]\d{{1,2}}[/\-.]\d{{2,4}}"
        rf"|\d{{4}}[/\-.]\d{{1,2}}[/\-.]\d{{1,2}}"
        rf"|(?:{MONTHS})\.?\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}}"
        rf"|\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{MONTHS})\.?,?\s+\d{{4}}"
        rf")\b"
    )
    WINDOW = 60

    def detect(self, text: str, context: dict) -> Iterable[Span]:
        cues = [m.end() for m in self._CUE.finditer(text)]
        if not cues:
            return
        for m in self._DATE.finditer(text):
            if any(0 <= m.start() - c <= self.WINDOW for c in cues):
                yield self._span(m.start(), m.end(), text)


def _looks_like_person(phrase: str) -> bool:
    phrase = phrase.strip(" .,;:-–—")
    if not phrase or any(ch.isdigit() for ch in phrase):
        return False
    if _norm(phrase) in DEFINED_TERM_STOPWORDS:
        return False
    tokens = [t for t in re.split(r"[\s\u00a0]+", phrase) if t]
    if not (2 <= len(tokens) <= 4):
        return False
    for tok in tokens:
        bare = tok.strip(".,'’-").lower()
        if not bare or bare in PERSON_TOKEN_BLOCKLIST:
            return False
        if bare in NAME_PARTICLES or bare in HONORIFICS:
            continue
        if len(bare) == 1 and tok.endswith("."):
            continue
        if len(bare) < 2:
            return False
        if not (tok[0].isupper() and (tok[1:].islower() or tok.isupper() or "'" in tok or "’" in tok)):
            return False
    return True


@register
class PersonDetector(Detector):

    pii_type = "PERSON"
    name = "person.seed+gazetteer"
    needs_fit = True

    EXPANSION_ROUNDS = 2

    _SEED_PATTERNS = [
        (re.compile(r"(?i)\bcontact\s+person(?:s)?\s*[:\-]\s*([^\n\r]{3,160})"), "list"),
        (re.compile(r"\b([A-Z][A-Za-z'’\-]+(?:\s+[A-Z][A-Za-z'’\-]+){1,3})\s+is\s+(?:our|the)\s+"), "single"),
        (re.compile(r"\b(?:Mr|Mrs|Ms|Dr|Prof|Shri|Smt|Sri)\.?\s+([A-Z][A-Za-z'’\-]+(?:\s+[A-Z][A-Za-z'’\-]+){1,3})"), "single"),
        (re.compile(r"(?i)\bour\s+promoters?\s*[:\-]\s*([^\n\r]{3,400})"), "list"),
        (re.compile(
            r"\b([A-Z][A-Za-z'’\-]+(?:\s+[A-Z][A-Za-z'’\-]+){1,3})\s*,\s*"
            r"(?=(?:aged|Chairman|Managing|Joint|Whole|Independent|Executive|"
            r"Non-Executive|Chief|Company Secretary|Director|Partner|Proprietor|"
            r"CEO|CFO|COO|CTO|CS\b|President|Vice|Head|Manager|Auditor|Secretary|"
            r"Technical|Deputy|Senior|Group|Plant|Unit|Nominee|Additional))"), "single"),
        (re.compile(r"(?im)^\s*name\s*[:\-]\s*([^\n\r]{3,80})$"), "single"),
        (re.compile(r"(?i)\b(?:s/o|w/o|d/o|son of|wife of|daughter of)\s+([A-Z][A-Za-z'’\-]+(?:\s+[A-Z][A-Za-z'’\-]+){1,3})"), "single"),
    ]

    _SPLIT = re.compile(r"\s*(?:/|,|;|\band\b|&)\s*")
    _LABEL_CUT = re.compile(
        r"(?i)\s*\b(?:website|e-?mail|telephone|tel|fax|sebi|cin|address|"
        r"investor|registration|contact|designation|din)\b\s*[:.]?"
    )

    def __init__(self) -> None:
        self.full_names: List[str] = []
        self.person_tokens: Set[str] = set()
        self._full_re: re.Pattern | None = None
        self._partial_re: re.Pattern | None = None
        self._honorific_re: re.Pattern | None = None

    def fit(self, full_text: str, context: dict) -> None:
        seeds: Set[str] = set()

        for pattern, mode in self._SEED_PATTERNS:
            for m in pattern.finditer(full_text):
                raw = m.group(1)
                cut = self._LABEL_CUT.search(raw)
                if cut:
                    raw = raw[: cut.start()]
                chunks = self._SPLIT.split(raw) if mode == "list" else [raw]
                for chunk in chunks:
                    chunk = chunk.strip(" .,;:-–—\t")
                    chunk = re.sub(r"\s+", " ", chunk)
                    if _looks_like_person(chunk):
                        seeds.add(self._titlecase(chunk))

        for name in context.get("person_seeds", set()):
            name = re.sub(r"\s+", " ", name).strip(" .,;:-–—\t")
            if _looks_like_person(name):
                seeds.add(self._titlecase(name))
        for name in context.get("ner_persons", set()):
            if _looks_like_person(name):
                seeds.add(self._titlecase(name))

        for _ in range(self.EXPANSION_ROUNDS):
            grown = self._expand(full_text, seeds, context)
            if not grown:
                break
            seeds |= grown

        self.full_names = sorted(seeds, key=len, reverse=True)
        for name in self.full_names:
            for tok in name.split():
                bare = tok.strip(".,'’-")
                if len(bare) >= 3 and bare.lower() not in PERSON_TOKEN_BLOCKLIST:
                    self.person_tokens.add(bare.lower())

        self._compile()
        context["person_names"] = list(self.full_names)
        context["person_tokens"] = set(self.person_tokens)

    _CAP_TOKEN = r"(?:[A-Z][a-z]{1,15}|[A-Z]{2,4}|[A-Z]\.)"
    _CAP_NGRAM = re.compile(
        rf"\b{_CAP_TOKEN}(?:[\s\u00a0]+{_CAP_TOKEN}){{1,3}}(?![\w])"
    )

    def _expand(self, full_text: str, seeds: Set[str], context: dict) -> Set[str]:
        known = {
            tok.strip(".,'\u2019-").lower()
            for name in seeds
            for tok in name.split()
            if len(tok.strip(".,'\u2019-")) >= 3
        } - PERSON_TOKEN_BLOCKLIST
        if not known:
            return set()

        org_text = " || ".join(context.get("org_names", []))
        found: Set[str] = set()
        for m in self._CAP_NGRAM.finditer(full_text):
            words = re.sub(r"\s+", " ", m.group(0)).split()
            i = 0
            while i < len(words) - 1:
                for length in range(min(4, len(words) - i), 1, -1):
                    phrase = " ".join(words[i : i + length])
                    if not _looks_like_person(phrase):
                        continue
                    tokens = [t.strip(".,'\u2019-").lower() for t in phrase.split()]
                    if not any(t in known for t in tokens):
                        continue
                    if phrase in org_text:
                        continue
                    if phrase not in seeds:
                        found.add(self._titlecase(phrase))
                    i += length
                    break
                else:
                    i += 1
        return found

    @staticmethod
    def _titlecase(phrase: str) -> str:
        return " ".join(
            t if (t.isupper() and len(t) <= 3) else t.capitalize() for t in phrase.split()
        )

    def _compile(self) -> None:
        if self.full_names:
            alts = "|".join(_flexible(n) for n in self.full_names)
            self._full_re = re.compile(rf"\b(?:{alts})\b", re.IGNORECASE)
        if self.person_tokens:
            tok = "|".join(sorted((re.escape(t) for t in self.person_tokens), key=len, reverse=True))
            self._partial_re = re.compile(
                rf"\b(?:{tok})(?:[\s\u00a0]+(?:{tok})){{1,3}}\b", re.IGNORECASE
            )
            hon = "|".join(sorted(HONORIFICS, key=len, reverse=True))
            self._honorific_re = re.compile(
                rf"(?i)\b(?:{hon})\.?[\s\u00a0]+((?:{tok}))\b"
            )

    def detect(self, text: str, context: dict) -> Iterable[Span]:
        if self._full_re is not None:
            for m in self._full_re.finditer(text):
                yield self._span(m.start(), m.end(), text, 1.0)
        if self._partial_re is not None:
            for m in self._partial_re.finditer(text):
                if text[m.start()].isupper():
                    yield self._span(m.start(), m.end(), text, 0.85)
        if self._honorific_re is not None:
            for m in self._honorific_re.finditer(text):
                yield self._span(m.start(1), m.end(1), text, 0.8)


@register
class OrgDetector(Detector):

    pii_type = "ORG"
    name = "org.suffix+gazetteer"
    needs_fit = True

    _WORD = r"(?:[A-Z][\w&.'’\-]*|\d+|[IVX]+)"
    _JOIN = r"(?:and|of|the|for|de|&)"

    _LEAD_STOPWORDS = {
        "the", "and", "of", "for", "our", "a", "an", "&", "company",
        "office", "registered", "corporate", "formerly", "name", "contact",
        "person", "address", "by", "with", "to", "from", "erstwhile", "viz",
    }

    def __init__(self) -> None:
        def alt_of(items):
            return "|".join(re.escape(s) for s in sorted(items, key=len, reverse=True))

        gap = r"[^\S\n]+"
        body = rf"{self._WORD}(?:{gap}(?:{self._WORD}|{self._JOIN})){{0,7}}"
        self._STRONG_RE = re.compile(
            rf"\b({body},?{gap}(?i:{alt_of(STRONG_ORG_SUFFIXES)}))(?![\w])"
        )
        self._WEAK_RE = re.compile(
            rf"\b({body},?{gap}(?i:{alt_of(WEAK_ORG_SUFFIXES)}))(?![\w])"
        )
        self._gazetteer_re: re.Pattern | None = None

    @staticmethod
    def _suffix(name: str) -> str:
        low = name.lower()
        for suf in sorted(ORG_SUFFIXES, key=len, reverse=True):
            if low.endswith(" " + suf.lower()):
                return name[-len(suf):]
        return ""

    def _strip_lead(self, name: str) -> str:
        tokens = name.split()
        keep = len(self._suffix(name).split()) + 1
        while len(tokens) > keep and tokens[0].lower().strip(".,") in self._LEAD_STOPWORDS:
            tokens.pop(0)
        return " ".join(tokens)

    @staticmethod
    def _trim_sentence(name: str) -> str:
        cut = max(name.rfind(". "), name.rfind("? "), name.rfind("! "))
        return name[cut + 2:] if cut != -1 else name

    def _weak_ok(self, name: str) -> bool:
        core_tokens = [t.strip(".,&").lower() for t in self._core(name).split()]
        core_tokens = [t for t in core_tokens if t]
        if not core_tokens:
            return False
        if any(t in OFFER_MACHINERY_WORDS for t in core_tokens):
            return False
        if core_tokens[-1] in {"the", "our", "a", "an", "and", "of"}:
            return False
        return any(t not in GENERIC_ORG_CORE_BLOCKLIST for t in core_tokens)

    _TRIM_TOKENS = (
        _LEAD_STOPWORDS
        | OFFER_MACHINERY_WORDS
        | {"bank", "banks", "banker", "bankers", "account", "portion",
           "personnel", "shareholder", "shareholders", "promoter", "promoters",
           "auditor", "auditors", "lender", "lenders", "registrar", "manager",
           "managers", "member", "members", "intermediary", "intermediaries"}
    )

    def _trim_prefix(self, name: str) -> str:
        tokens = name.split()
        keep = len(self._suffix(name).split()) + 1
        while len(tokens) > keep and tokens[0].lower().strip(".,") in self._TRIM_TOKENS:
            tokens.pop(0)
        return " ".join(tokens)

    def _split_conjunction(self, name: str) -> List[str]:
        pieces = re.split(r"(\s+(?:and|&)\s+)", name)
        if len(pieces) < 3:
            return [name]
        out, buffer, joiner = [], "", ""
        for piece in pieces:
            if re.fullmatch(r"\s+(?:and|&)\s+", piece):
                joiner = piece
                continue
            candidate = f"{buffer}{joiner}{piece}" if buffer else piece
            if self._suffix(candidate):
                out.append(candidate)
                buffer = ""
            else:
                buffer = candidate
        if buffer:
            if out:
                out[-1] = f"{out[-1]}{joiner or ' and '}{buffer}"
            else:
                out.append(buffer)
        return out or [name]

    def _clean(self, raw: str) -> List[str]:
        base = self._trim_sentence(re.sub(r"\s+", " ", raw).strip())
        results = []
        for part in self._split_conjunction(base):
            results.append(self._trim_prefix(self._strip_lead(part)))
        return results

    _SUFFIX_WORDS = {
        w.strip(".,&").lower()
        for suffix in ORG_SUFFIXES
        for w in suffix.split()
        if w.strip(".,&")
    }

    def _acceptable(self, name: str) -> bool:
        low = _norm(name)
        if low in PUBLIC_BODY_ALLOWLIST or low in DEFINED_TERM_STOPWORDS:
            return False
        if len(name.split()) < 2:
            return False
        suffix = self._suffix(name)
        if suffix and suffix[0].islower():
            return False
        core = self._core(name)
        if not core or _norm(core) in DEFINED_TERM_STOPWORDS:
            return False
        core_tokens = [t.strip(".,&").lower() for t in core.split() if t.strip(".,&")]
        if core_tokens and all(
            t in GENERIC_ORG_CORE_BLOCKLIST or t in self._SUFFIX_WORDS for t in core_tokens
        ):
            return False
        return True

    @classmethod
    def _core(cls, name: str) -> str:
        suffix = cls._suffix(name)
        return name[: len(name) - len(suffix)].strip() if suffix else name

    def fit(self, full_text: str, context: dict) -> None:
        found: Set[str] = set()
        for m in self._STRONG_RE.finditer(full_text):
            for name in self._clean(m.group(1)):
                if self._acceptable(name):
                    found.add(name)
        for m in self._WEAK_RE.finditer(full_text):
            for name in self._clean(m.group(1)):
                if self._acceptable(name) and self._weak_ok(name):
                    found.add(name)
        for raw in context.get("ner_orgs", set()):
            for name in self._clean(raw):
                if self._acceptable(name):
                    found.add(name)

        self.orgs = sorted(found, key=len, reverse=True)

        aliases: Set[str] = set()
        person_tokens = context.get("person_tokens", set())
        known = {n.lower() for n in self.orgs}
        for name in self.orgs:
            core = self._core(name)
            low = _norm(core)
            if not core or low in DEFINED_TERM_STOPWORDS or low in PUBLIC_BODY_ALLOWLIST:
                continue
            if low in person_tokens or low in GENERIC_ORG_CORE_BLOCKLIST or low in known:
                continue
            if len(core.split()) >= 2:
                aliases.add(core)

        everything = sorted(set(self.orgs) | aliases, key=len, reverse=True)
        if everything:
            alts = "|".join(_flexible(n) for n in everything)
            self._gazetteer_re = re.compile(rf"\b(?:{alts})\b", re.IGNORECASE)
        context["org_names"] = list(self.orgs)

    def detect(self, text: str, context: dict) -> Iterable[Span]:
        if self._gazetteer_re is None:
            return
        for m in self._gazetteer_re.finditer(text):
            if _norm(m.group(0)) in PUBLIC_BODY_ALLOWLIST:
                continue
            yield self._span(m.start(), m.end(), text, 0.9)


@register
class AddressDetector(Detector):

    pii_type = "ADDRESS"
    name = "address.anchored+gazetteer"
    needs_fit = True

    _GEO_COMMON = set(INDIAN_STATES) | {
        "india", "pune", "mumbai", "delhi", "new delhi", "chennai", "kolkata",
        "bengaluru", "bangalore", "hyderabad", "ahmedabad", "nagpur", "thane",
        "navi mumbai", "gurgaon", "noida", "bhopal", "raigad", "east", "west",
        "north", "south", "central",
    }

    _PIN = re.compile(r"(?<![\d,.])(\d{3}\s?\d{3})(?![\d.])(?!,\s*\d)")
    _ZIP = re.compile(r"\b([A-Z]{2})\s+(\d{5}(?:-\d{4})?)\b")
    _LABEL = re.compile(
        r"(?i)\b(?:registered office|corporate office|correspondence address|"
        r"residential address|mailing address|address)\s*(?:of[^:\n]{0,40})?\s*[:\-]\s*"
    )
    _US = re.compile(
        r"\b\d{1,5}\s+(?:[A-Z][\w.]*\s+){1,4}"
        r"(?:Street|St\.?|Road|Rd\.?|Avenue|Ave\.?|Boulevard|Blvd\.?|Drive|Dr\.?|Lane|Ln\.?|Way|Court|Ct\.?)"
        r"(?:,\s*(?:Apt|Suite|Ste|Unit)\.?\s*[\w\-]+)?"
        r"(?:,\s*[A-Z][\w\s]{2,20},\s*[A-Z]{2}\s+\d{5}(?:-\d{4})?)?"
    )
    _BOUNDARY = re.compile(r"[\n\r]|(?<=[.;])\s")
    _TAIL = re.compile(
        r"(?:[,\s]+\(?(?!Telephone|Tel\b|Fax|Email|E-mail|Website|Contact|Investor|SEBI|CIN|"
        r"Registration|Compliance|Corporate|Registered)[A-Z][a-zA-Z]+\)?){0,3}"
    )
    _ADDRESS_CUE = re.compile(r"(?:\bat\b|[:;])\s+")

    _LEAD_NOISE = {
        "ship", "send", "mail", "post", "deliver", "delivered", "to", "at",
        "in", "from", "the", "our", "is", "are", "was", "were", "located",
        "situated", "address", "please", "it", "by", "on", "of", "and",
        "having", "with", "see", "for", "his", "her", "their", "residing",
        "registered", "corporate", "office", "correspondence", "residential",
        "mailing", "regd", "premises",
    }

    LOOKBACK = 170

    def __init__(self) -> None:
        self._components: List[str] = []
        self._component_re: "re.Pattern | None" = None

    @staticmethod
    def _skip_leading_org(text: str, start: int, pin_start: int, context: dict) -> int:
        for org in context.get("org_names", []):
            idx = text.find(org, start, pin_start)
            if idx != -1 and idx - start <= 3:
                start = idx + len(org)
                while start < pin_start and text[start] in " ,;\t":
                    start += 1
        return start

    @classmethod
    def _trim_lead_noise(cls, text: str, start: int, stop: int) -> int:
        cues = list(cls._ADDRESS_CUE.finditer(text, start, stop))
        if cues:
            start = cues[-1].end()
        while start > 0 and start < stop and text[start - 1].isalnum() and text[start].isalnum():
            start += 1
        for m in re.finditer(r"\S+", text[start:stop]):
            if m.group(0).strip(".,;:").lower() in cls._LEAD_NOISE:
                continue
            return start + m.start()
        return start

    def _has_address_words(self, window: str) -> bool:
        low = window.lower()
        if any(st in low for st in INDIAN_STATES):
            return True
        if "india" in low:
            return True
        return any(re.search(rf"\b{re.escape(k)}\b", low) for k in STREET_KEYWORDS)

    def fit(self, full_text: str, context: dict) -> None:
        components: Set[str] = set()
        for span in self._anchored(full_text, context):
            for raw in re.split(r"[,\n;]", span.text):
                part = raw.strip(" .;–—-\t")
                part = re.sub(r"\s+", " ", part)
                if self._is_reusable_component(part, context):
                    components.add(part)

        self._components = sorted(components, key=len, reverse=True)
        if self._components:
            alts = "|".join(_flexible(c) for c in self._components)
            self._component_re = re.compile(rf"\b(?:{alts})\b", re.IGNORECASE)
        context["address_components"] = list(self._components)

    def _is_reusable_component(self, part: str, context: dict) -> bool:
        tokens = [t for t in part.split() if t.strip(".,-")]
        if not (2 <= len(tokens) <= 8) or len(part) > 60:
            return False
        low = _norm(part)
        if low in self._GEO_COMMON or low in PUBLIC_BODY_ALLOWLIST:
            return False
        if low in DEFINED_TERM_STOPWORDS:
            return False
        if low in {_norm(o) for o in context.get("org_names", [])}:
            return False
        distinctive = [
            t for t in tokens
            if t.lower().strip(".,-") not in self._GEO_COMMON
            and not t.strip(".,-").isdigit()
            and len(t.strip(".,-")) >= 4
            and t[:1].isupper()
        ]
        return bool(distinctive)

    def detect(self, text: str, context: dict) -> Iterable[Span]:
        yield from self._anchored(text, context)
        if self._component_re is not None:
            for m in self._component_re.finditer(text):
                yield self._span(m.start(), m.end(), text, 0.8)

    def _anchored(self, text: str, context: dict) -> Iterable[Span]:
        for m in self._LABEL.finditer(text):
            start = m.end()
            nxt = self._BOUNDARY.search(text, start)
            end = nxt.start() if nxt else min(len(text), start + 200)
            chunk = text[start:end].strip()
            if len(chunk) >= 12 and self._has_address_words(chunk):
                yield self._span(start, start + len(text[start:end].rstrip()), text, 0.9)

        for m in self._PIN.finditer(text):
            lo = max(0, m.start() - self.LOOKBACK)
            window = text[lo : m.start()]
            if not self._has_address_words(window + text[m.end() : m.end() + 40]):
                continue
            boundaries = [lo + b.end() for b in self._BOUNDARY.finditer(window)]
            start = boundaries[-1] if boundaries else lo
            start = self._skip_leading_org(text, start, m.start(), context)
            start = self._trim_lead_noise(text, start, m.start())
            tail = self._TAIL.match(text[m.end():])
            end = m.end() + (len(tail.group(0).rstrip(", \n")) if tail else 0)
            chunk = text[start:end].strip()
            if len(chunk) >= 12:
                offset = len(text[start:end]) - len(text[start:end].lstrip())
                yield self._span(start + offset, end, text, 0.85)

        for m in self._US.finditer(text):
            yield self._span(m.start(), m.end(), text, 0.9)

        for m in self._ZIP.finditer(text):
            lo = max(0, m.start() - self.LOOKBACK)
            window = text[lo:m.start()]
            if not re.search(r"\d", window):
                continue
            boundaries = [lo + b.end() for b in self._BOUNDARY.finditer(window)]
            start = boundaries[-1] if boundaries else lo
            start = self._skip_leading_org(text, start, m.start(), context)
            start = self._trim_lead_noise(text, start, m.start())
            chunk = text[start:m.end()]
            offset = len(chunk) - len(chunk.lstrip())
            if len(chunk.strip()) >= 12:
                yield self._span(start + offset, m.end(), text, 0.85)


def optional_ner_layer(full_text: str, model: str = "en_core_web_lg") -> Dict[str, Set[str]]:
    out: Dict[str, Set[str]] = {"ner_persons": set(), "ner_orgs": set()}
    try:
        import spacy

        nlp = spacy.load(model, disable=["lemmatizer", "textcat"])
        nlp.max_length = max(nlp.max_length, len(full_text) + 1000)
        for doc in nlp.pipe([full_text[i : i + 400_000] for i in range(0, len(full_text), 400_000)]):
            for ent in doc.ents:
                if ent.label_ == "PERSON":
                    out["ner_persons"].add(ent.text.strip())
                elif ent.label_ == "ORG":
                    out["ner_orgs"].add(ent.text.strip())
    except Exception:
        pass
    return out
