from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from faker import Faker

from .detectors import _luhn_ok, _verhoeff_ok
from .lexicons import HONORIFICS, ORG_SUFFIXES

_SALT = "pii-redactor-v1"


def _seed(value: str) -> int:
    digest = hashlib.sha256((_SALT + value.lower()).encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _is_initial(token: str) -> bool:
    return len(token.strip(".")) == 1 and token.endswith(".")


def _match_case(original: str, replacement: str) -> str:
    if original.isupper() and len(original) > 3:
        return replacement.upper()
    if original.islower():
        return replacement.lower()
    return replacement


@dataclass
class PersonIdentity:

    real_tokens: List[str]
    fake_tokens: List[str]

    @property
    def real_key(self) -> str:
        return " ".join(t.lower() for t in self.real_tokens)


class SurrogateBank:

    def __init__(self, seed: int = 20250810, locale: str = "en_IN") -> None:
        self.master_seed = seed
        self.faker = Faker(locale)
        self.generic = Faker("en_US")
        self.mapping: Dict[str, Dict[str, str]] = {}
        self.people: List[PersonIdentity] = []
        self._token_index: Dict[str, List[PersonIdentity]] = {}
        self._org_core: Dict[str, str] = {}
        self._domain_map: Dict[str, str] = {}
        self._forbidden: set = set()

    def forbid(self, tokens) -> None:
        self._forbidden.update(t.lower() for t in tokens if len(t) >= 3)

    def _is_safe(self, value: str) -> bool:
        return not any(
            tok.strip(".,'-").lower() in self._forbidden for tok in value.split()
        )

    def _safe(self, generate, attempts: int = 20, fallback: str = "") -> str:
        value = ""
        for _ in range(attempts):
            value = generate()
            if self._is_safe(value):
                return value
        return fallback or value

    def _fake(self, seed_value: str) -> Faker:
        self.faker.seed_instance(_seed(seed_value) ^ self.master_seed)
        return self.faker

    def _remember(self, pii_type: str, real: str, fake: str) -> str:
        self.mapping.setdefault(pii_type, {})[real] = fake
        return fake

    def _cached(self, pii_type: str, real: str) -> Optional[str]:
        return self.mapping.get(pii_type, {}).get(real)

    def register_people(self, full_names: Sequence[str]) -> None:
        ordered = sorted(set(full_names), key=lambda n: (-len(n.split()), n))
        for name in ordered:
            tokens = [t for t in name.split() if t.strip(".").lower() not in HONORIFICS]
            if not tokens:
                continue

            existing = self._matching_identity(tokens)
            if existing is not None:
                lowered = [t.lower() for t in existing.real_tokens]
                folded = [existing.fake_tokens[lowered.index(t.lower())] for t in tokens]
                self._remember("PERSON", " ".join(tokens), " ".join(folded))
                for tok in tokens:
                    index = self._token_index.setdefault(tok.lower(), [])
                    if existing not in index:
                        index.append(existing)
                continue

            fake = self._fake(name)
            fake_tokens: List[str] = []
            for position, token in enumerate(tokens):
                if _is_initial(token):
                    fake_tokens.append(self._safe(fake.first_name)[0] + ".")
                elif position == len(tokens) - 1 and len(tokens) > 1:
                    fake_tokens.append(self._safe(fake.last_name))
                else:
                    fake_tokens.append(self._safe(fake.first_name))
            identity = PersonIdentity(real_tokens=tokens, fake_tokens=fake_tokens)
            self.people.append(identity)
            self._remember("PERSON", " ".join(tokens), " ".join(fake_tokens))
            for tok in tokens:
                self._token_index.setdefault(tok.lower(), []).append(identity)

    def register_orgs(self, names: Sequence[str]) -> None:
        for name in sorted(set(names), key=len, reverse=True):
            if self._cached("ORG", name):
                continue
            suffix = ""
            low = name.lower()
            for suf in sorted(ORG_SUFFIXES, key=len, reverse=True):
                if low.endswith(" " + suf.lower()):
                    suffix = name[-len(suf) :]
                    break
            fake = self._fake(name)
            core = self._safe(lambda: fake.company().replace(",", ""))
            for suf in sorted(ORG_SUFFIXES, key=len, reverse=True):
                if core.lower().endswith(" " + suf.lower()):
                    core = core[: -(len(suf) + 1)].strip()
                    break
            full = f"{core} {suffix}".strip() if suffix else core
            self._remember("ORG", name, full)
            real_core = name[: len(name) - len(suffix)].strip() if suffix else name
            if real_core:
                self._org_core[real_core.lower()] = core
                self._remember("ORG", real_core, core)
            slug = re.sub(r"[^a-z0-9]", "", core.lower())[:24] or "example"
            self._domain_map[self._slug(real_core)] = slug

    @staticmethod
    def _slug(text: str) -> str:
        return re.sub(r"[^a-z0-9]", "", text.lower())

    def person(self, mention: str) -> str:
        cached = self._cached("PERSON_MENTION", mention)
        if cached:
            return cached

        raw_tokens = mention.split()
        honorific = ""
        if raw_tokens and raw_tokens[0].strip(".").lower() in HONORIFICS:
            honorific = raw_tokens[0] + " "
            raw_tokens = raw_tokens[1:]
        if not raw_tokens:
            return mention

        agreed = self._cached("PERSON", " ".join(raw_tokens))
        if agreed is not None:
            result = honorific + _match_case(mention, agreed)
            return self._remember("PERSON_MENTION", mention, result)

        identity = self._best_identity(raw_tokens)
        if identity is not None:
            out_tokens: List[str] = []
            lowered = [t.lower() for t in identity.real_tokens]
            for tok in raw_tokens:
                try:
                    idx = lowered.index(tok.lower())
                except ValueError:
                    idx = -1
                if 0 <= idx < len(identity.fake_tokens):
                    out_tokens.append(identity.fake_tokens[idx])
                else:
                    out_tokens.append(self._safe(self._fake(tok).last_name))
            fake = " ".join(out_tokens)
        else:
            fake = self._safe(self._fake(mention).name)

        result = honorific + _match_case(mention, fake)
        return self._remember("PERSON_MENTION", mention, result)

    def _matching_identity(self, tokens: Sequence[str]) -> Optional[PersonIdentity]:
        lowered = [t.lower() for t in tokens]
        matches = []
        for identity in self.people:
            if len(identity.real_tokens) <= len(tokens):
                continue
            existing = [t.lower() for t in identity.real_tokens]
            if existing[-1] != lowered[-1]:
                continue
            it = iter(existing)
            if all(any(tok == candidate for candidate in it) for tok in lowered):
                matches.append(identity)
        if not matches:
            return None
        return min(
            matches,
            key=lambda i: (
                [t.lower() for t in i.real_tokens][:1] != lowered[:1],
                len(i.real_tokens),
                " ".join(i.real_tokens),
            ),
        )

    def _best_identity(self, tokens: Sequence[str]) -> Optional[PersonIdentity]:
        candidates: Dict[int, int] = {}
        for tok in tokens:
            for identity in self._token_index.get(tok.lower(), []):
                candidates[id(identity)] = candidates.get(id(identity), 0) + 1
        if not candidates:
            return None
        lowered = [t.lower() for t in tokens]
        by_id = {id(p): p for p in self.people}

        def rank(key: int):
            identity = by_id[key]
            real = [t.lower() for t in identity.real_tokens]
            return (
                candidates[key],
                real[-1:] == lowered[-1:],
                real[:1] == lowered[:1],
                -len(real),
            )

        return by_id[max(candidates, key=rank)]

    def org(self, mention: str) -> str:
        cached = self._cached("ORG", mention)
        if cached:
            return _match_case(mention, cached)
        core = self._org_core.get(mention.lower())
        if core:
            return _match_case(mention, core)
        fake = self._fake(mention).company().replace(",", "")
        return _match_case(mention, self._remember("ORG", mention, fake))

    def email(self, mention: str) -> str:
        cached = self._cached("EMAIL", mention)
        if cached:
            return cached
        local, _, domain = mention.partition("@")
        parts = re.split(r"([._\-])", local)
        rebuilt: List[str] = []
        replaced_any = False
        for part in parts:
            if part in "._-":
                rebuilt.append(part)
                continue
            identity = self._best_identity([part]) if part else None
            if identity is not None:
                lowered = [t.lower() for t in identity.real_tokens]
                idx = lowered.index(part.lower())
                rebuilt.append(identity.fake_tokens[idx].lower())
                replaced_any = True
            else:
                rebuilt.append(part)
        fake_local = "".join(rebuilt) if replaced_any else self._fake(local).user_name()
        fake_domain = self._fake_domain(domain)
        return self._remember("EMAIL", mention, f"{fake_local}@{fake_domain}")

    def _fake_domain(self, domain: str) -> str:
        cached = self._cached("DOMAIN", domain)
        if cached:
            return cached
        host = domain.lower()
        labels = host.split(".")
        if len(labels) >= 3 and labels[-2] in {"co", "com", "net", "org", "gov", "ac", "edu"}:
            tld = "." + ".".join(labels[-2:])
        elif len(labels) >= 2:
            tld = "." + labels[-1]
        else:
            tld = ".com"
        stem = labels[0]
        replacement = self._domain_map.get(self._slug(stem))
        if replacement is None:
            for slug, target in self._domain_map.items():
                if slug and (slug in self._slug(host)):
                    replacement = target
                    break
        if replacement is None:
            replacement = self._slug(self._fake(domain).company())[:20] or "example"
        return self._remember("DOMAIN", domain, replacement + tld)

    def url(self, mention: str) -> str:
        cached = self._cached("URL", mention)
        if cached:
            return cached
        m = re.match(r"(?i)^(https?://)?(www\.)?([^/]+)(/.*)?$", mention)
        if not m:
            return self._remember("URL", mention, "www.example.com")
        scheme, www, host, path = m.group(1) or "", m.group(2) or "", m.group(3), m.group(4) or ""
        return self._remember("URL", mention, f"{scheme}{www}{self._fake_domain(host)}{path}")

    def phone(self, mention: str) -> str:
        cached = self._cached("PHONE", mention)
        if cached:
            return cached
        fake = self._fake(mention)
        keep = 0
        m = re.match(r"\s*\+\s?\d{1,3}", mention)
        if m:
            keep = m.end()
        out: List[str] = [mention[:keep]]
        for ch in mention[keep:]:
            out.append(str(fake.random_digit()) if ch.isdigit() else ch)
        return self._remember("PHONE", mention, "".join(out))

    def address(self, mention: str) -> str:
        cached = self._cached("ADDRESS", mention)
        if cached:
            return cached
        fake = self._fake(mention)
        text = self._safe(lambda: fake.address().replace("\n", ", "))
        return self._remember("ADDRESS", mention, text)

    def ssn(self, mention: str) -> str:
        cached = self._cached("SSN", mention)
        if cached:
            return cached
        fake = self._fake(mention)
        value = self.generic.ssn() if hasattr(self.generic, "ssn") else "123-45-6789"
        self.generic.seed_instance(_seed(mention))
        value = self.generic.ssn()
        if "-" not in mention:
            value = value.replace("-", "")
        elif " " in mention and "-" not in mention:
            value = value.replace("-", " ")
        return self._remember("SSN", mention, value)

    def credit_card(self, mention: str) -> str:
        cached = self._cached("CREDIT_CARD", mention)
        if cached:
            return cached
        fake = self._fake(mention)
        digits = re.sub(r"\D", "", mention)
        body = [digits[0]] + [str(fake.random_digit()) for _ in range(len(digits) - 2)]
        for check in range(10):
            candidate = "".join(body) + str(check)
            if _luhn_ok(candidate):
                break
        out, it = [], iter(candidate)
        for ch in mention:
            out.append(next(it) if ch.isdigit() else ch)
        return self._remember("CREDIT_CARD", mention, "".join(out))

    def date_of_birth(self, mention: str) -> str:
        cached = self._cached("DATE_OF_BIRTH", mention)
        if cached:
            return cached
        fake = self._fake(mention)
        d = fake.date_of_birth(minimum_age=21, maximum_age=85)
        if re.match(r"^\d{1,2}[/\-.]", mention):
            sep = re.search(r"[/\-.]", mention).group(0)
            value = f"{d.day:02d}{sep}{d.month:02d}{sep}{d.year}"
        elif re.match(r"^\d{4}[/\-.]", mention):
            sep = re.search(r"[/\-.]", mention).group(0)
            value = f"{d.year}{sep}{d.month:02d}{sep}{d.day:02d}"
        elif re.match(r"^\d", mention):
            value = d.strftime("%d %B %Y")
        else:
            value = d.strftime("%B %d, %Y")
        return self._remember("DATE_OF_BIRTH", mention, value)

    def ip_address(self, mention: str) -> str:
        cached = self._cached("IP_ADDRESS", mention)
        if cached:
            return cached
        fake = self._fake(mention)
        value = fake.ipv6() if ":" in mention else fake.ipv4_public()
        return self._remember("IP_ADDRESS", mention, value)

    def aadhaar(self, mention: str) -> str:
        cached = self._cached("AADHAAR", mention)
        if cached:
            return cached
        fake = self._fake(mention)
        while True:
            body = str(fake.random_int(2, 9)) + "".join(
                str(fake.random_digit()) for _ in range(11)
            )
            if _verhoeff_ok(body):
                break
        sep = " " if " " in mention else ("-" if "-" in mention else "")
        value = sep.join([body[0:4], body[4:8], body[8:12]]) if sep else body
        return self._remember("AADHAAR", mention, value)

    def pan(self, mention: str) -> str:
        cached = self._cached("PAN", mention)
        if cached:
            return cached
        fake = self._fake(mention)
        letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        value = (
            "".join(fake.random_element(letters) for _ in range(3))
            + fake.random_element("ABCFGHLJPT")
            + fake.random_element(letters)
            + "".join(str(fake.random_digit()) for _ in range(4))
            + fake.random_element(letters)
        )
        return self._remember("PAN", mention, value)

    def cin(self, mention: str) -> str:
        cached = self._cached("CIN", mention)
        if cached:
            return cached
        fake = self._fake(mention)
        letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        value = (
            fake.random_element("UL")
            + "".join(str(fake.random_digit()) for _ in range(5))
            + "".join(fake.random_element(letters) for _ in range(2))
            + str(fake.random_int(1950, 2024))
            + fake.random_element(["PLC", "PTC", "LTD"])
            + "".join(str(fake.random_digit()) for _ in range(6))
        )
        return self._remember("CIN", mention, value)

    def din(self, mention: str) -> str:
        cached = self._cached("DIN", mention)
        if cached:
            return cached
        fake = self._fake(mention)
        value = "0" + "".join(str(fake.random_digit()) for _ in range(7))
        return self._remember("DIN", mention, value)

    def reg_id(self, mention: str) -> str:
        cached = self._cached("REG_ID", mention)
        if cached:
            return cached
        fake = self._fake(mention)
        prefix = re.match(r"IN[A-Z]{1,2}", mention).group(0)
        digits = len(mention) - len(prefix)
        value = prefix + "".join(str(fake.random_digit()) for _ in range(digits))
        return self._remember("REG_ID", mention, value)

    _DISPATCH = {
        "PERSON": "person",
        "ORG": "org",
        "EMAIL": "email",
        "URL": "url",
        "PHONE": "phone",
        "ADDRESS": "address",
        "SSN": "ssn",
        "CREDIT_CARD": "credit_card",
        "DATE_OF_BIRTH": "date_of_birth",
        "IP_ADDRESS": "ip_address",
        "AADHAAR": "aadhaar",
        "PAN": "pan",
        "CIN": "cin",
        "DIN": "din",
        "REG_ID": "reg_id",
    }

    def surrogate_for(self, pii_type: str, mention: str) -> str:
        method = self._DISPATCH.get(pii_type)
        if method is None:
            return f"[{pii_type}]"
        return getattr(self, method)(mention)

    def save_mapping(self, path: Path) -> None:
        payload = {k: v for k, v in sorted(self.mapping.items()) if k != "PERSON_MENTION"}
        payload["PERSON_MENTION"] = self.mapping.get("PERSON_MENTION", {})
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
