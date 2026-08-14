# PII Redaction Tool

Replaces personally identifiable information in a `.docx` with consistent, realistic fakes.
Built for and evaluated on the attached Red Herring Prospectus (KSH International Limited, 519 pages).

```bash
pip install -r requirements.txt

python redact.py "Red Herring Prospectus.docx" \
    -o "Red Herring Prospectus (redacted).docx" \
    --mapping mapping.json \
    --audit audit.jsonl
```

Runs in ~23 seconds on the full prospectus. Output for this document is in `out/`.

---

## Approach

**Hybrid: rules and checksums for structured PII, seed-and-propagate gazetteers for free-text
entities, with spaCy NER as an optional additional signal.**

### 1. Structured PII — regex plus a validator

Emails, phones, IP addresses, SSNs, credit cards, Aadhaar, PAN, CIN, DIN and SEBI registration
numbers all have specified formats, so a pattern plus a validity check beats any model:

- credit cards must pass the **Luhn** checksum and start with a real network prefix;
- Aadhaar numbers must pass the **Verhoeff** checksum;
- SSNs must respect the SSA's invalid ranges (`000`/`666`/`9xx` area, `00` group, `0000` serial);
- phone numbers are only accepted with an explicit international prefix **or** a `Telephone:` /
  `Fax:` style label. In a document this dense with share counts and rupee figures, a bare run of
  digits is never treated as a phone number.

Dates are only redacted when a birth cue (`date of birth`, `born on`, `DOB`) appears within 60
characters. An offer document is wall-to-wall dates — board resolutions, fiscal year ends, consent
letters — and redacting them all would destroy the document and tank precision.

### 2. Free-text PII — seed, then propagate

Names, companies and addresses have no fixed shape, so detection happens in two passes.

**Pass 1 (`fit`) mines the whole document** for high-confidence *seeds* using cues that are almost
never wrong:

| Type | Seed sources |
|---|---|
| `PERSON` | `Contact Person:` lines, honorifics, `X is our Company Secretary`, `X, Managing Director`, `OUR PROMOTERS: …`, `Name:` signature blocks, `S/o` / `W/o`, and the **Name column of any table that also has a DIN or Designation column** |
| `ORG` | Legal suffixes (`Private Limited`, `LLP`, `Corporation`, `Family Trust`, …) preceded by a capitalised run |
| `ADDRESS` | A PIN/ZIP code with corroborating address vocabulary nearby, or an `Address:` / `Registered Office:` label |

**Pass 2 propagates** each seed across the document, which is what actually delivers recall:

- Every token of a confirmed name joins a person-token vocabulary, so `Mr. Hegde`, `Kushal Hegde`
  and `Subbayya Hegde` are all caught from `Kushal Subbayya Hegde`.
- Two bounded **expansion rounds** admit capitalised n-grams that share a token with a confirmed
  name. This is what finds `Karunakar Hegde` (a historical shareholder mentioned only in a share
  transfer log), and then `Karunakar N. Bhandary` in the round after.
- Company short forms propagate too: `KSH International Limited` also redacts `KSH International`.
- Address *components* harvested from anchored addresses (`Village Birdewadi`, `Off Pallod Farms`)
  are matched wherever they appear. Addresses in an offer document are laid out as multi-line
  blocks where each line is its own paragraph, so only the line carrying the PIN code is
  detectable on its own — the rest would otherwise survive untouched.

### 3. Optional NER layer

`optional_ner_layer()` folds spaCy `PERSON`/`ORG` entities into the same seed sets. It is enabled
by default and **degrades silently to the rule layer if spaCy or the model is not installed**, so
the tool never hard-fails on a missing dependency.

> The numbers in `EVALUATION.md` were produced **without** the NER layer — the sandbox used for
> this exercise had no network route to the spaCy model host. To reproduce with NER:
> `python -m spacy download en_core_web_lg && python redact.py …`. NER should mainly help the one
> category the rules cannot reach: organisations with no legal suffix (see *Known misses*).

### 4. Replacement — consistent pseudonyms

Every real value maps to exactly one fake value, so the redacted document stays internally
coherent: the same director keeps the same alias in the shareholding table, the signature block
and the risk factors, and their surname alone resolves to *that alias's* surname.

- Fakes are generated with Faker (`en_IN`) seeded by a stable SHA-256 of the real value, so two
  runs over the same input produce identical output with no mapping file to carry around.
- Type-appropriate shapes are preserved: phone numbers keep their country code and punctuation
  (`+91 20 4505 3237` → `+91 20 8172 6640`), companies keep their legal suffix, credit cards stay
  Luhn-valid, Aadhaar stays Verhoeff-valid.
- Email local parts built from a person's name follow that person's alias, and email/website
  domains follow the company's alias — so `sarthak.malvadkar@kshinternational.com` and
  `www.kshinternational.com` stay consistent with each other and with the person and company.
- **Collision guard:** Faker's Indian locale draws from the same name pool as the document, so
  without a guard it will happily invent "Vijay Hegde" while redacting "Rajesh Hegde". The
  surrogate bank refuses to emit any value containing a real token from the source.

### 5. Writing back to .docx

Formatting is preserved by detecting on the full paragraph text but writing back **run by run**.
Word splits runs at every formatting change — often mid-word, often mid-email-address — so a
naive per-run regex misses most matches, and a naive whole-paragraph rewrite destroys the
formatting. Runs containing no PII are left untouched byte-for-byte.

Three non-obvious places PII hides, all covered:

1. **`w:instrText` field codes.** `HYPERLINK "mailto:cs.connect@kshinternational.com"` is not
   visible text. This document has 117 of them; redacting only what you can see leaves every real
   address sitting in the file. This was by far the largest leak found during development.
2. **Headers, footers, and hyperlink relationship targets.**
3. **Table cells, including nested tables.** Cells are walked via the `w:tc` elements directly
   rather than `row.cells`: that property re-materialises a merged cell once per grid column it
   spans, and de-duplicating by `id()` is unsafe because lxml proxy objects are transient — a
   freed proxy's `id()` gets reused, which silently skipped 2,611 of 5,041 paragraphs before this
   was fixed.

---

## Scope decisions

The assignment asks for explicit choices about what is and is not PII. Mine:

**Redacted**

- Person names, including partial mentions and historical shareholders.
- Commercial entities: the issuer, book running lead managers, bankers, auditors, legal advisers,
  registrars, group companies, promoter trusts, suppliers, customers, peers.
- Postal addresses, including directors' residential addresses.
- Emails, phone numbers, corporate websites.
- Entity identifiers: **CIN**, **DIN**, **SEBI registration numbers**. These identify a specific
  company or director as precisely as a name does, so treating them as "reference numbers" would
  be a mistake.

**Deliberately not redacted**

- **Regulators, statutory bodies and market infrastructure** — SEBI, RBI, RoC, NSE, BSE, NSDL,
  CDSL, NPCI, Government ministries, and their websites. These identify no private party; the
  document is unreadable without them and redacting them communicates nothing.
- **Statutes, defined terms and market jargon** — "Companies Act, 2013", "Anchor Investor",
  "Escrow Collection Bank", "Book Running Lead Managers". Capitalised, entity-shaped, and not PII.
- **Bare place names** — "Pune", "Maharashtra", "Chakan", "Birdewadi" on their own. Only full
  postal addresses are redacted. A city or village name in isolation identifies nobody.
- **Non-birth dates, financial figures, share counts, page and section references.** This is the
  main precision trade: this document contains hundreds of dates and thousands of numbers, and a
  looser rule would have shredded it.

---

## Trade-offs, false positives and false negatives

### Known misses (false negatives)

1. **Organisations with no legal suffix** — the one real gap. `Financial Express`, `Jansatta` and
   `Loksatta` (newspapers), `Sterlite Copper` (a brand), and `KSH International Chakan Internal
   Kamgar Sangathna` (a trade union) are all missed, because the ORG detector is anchored on
   incorporation markers. This accounts for **all 10 remaining false-negative tokens** in the
   evaluation. Enabling the spaCy NER layer is the intended fix; a curated seed list is the
   deterministic alternative.
2. **A bare single-token locality**: `Chakan Unit No. 2 (Birdewadi)` keeps "Birdewadi", by the
   scope rule above. Debatable — one could argue a village name plus a unit number is
   re-identifying.
3. **A person whose every token is unique to one mention** and who appears in no structural cue
   would be missed, since expansion needs a shared token to latch onto.

### Precision traps that were deliberately closed

Each of these fired during development and is now guarded, which is why measured precision is
1.000:

- `Promoters`, `Name`, `Promoter Group` detected as people — the directors-table harvester was
  feeding header and label cells straight in without the shape test.
- `Everest Family Trust` and friends detected as *people* rather than companies, from the
  `OUR PROMOTERS:` list.
- `India` (84 times), `State`, `Refund Bank`, `Escrow Collection Bank`, `Practicing Company` as
  companies — fixed by splitting legal suffixes into strong and weak, guarding weak ones against
  offer-machinery vocabulary, and refusing single-token short forms.
- `Nuvama Wealth Management Limited and ICICI Securities Limited` captured as one entity — now
  split on conjunctions so each company keeps its own alias.
- `Yojana PV Photo Voltaic PWIL Precision Wires India Limited` — a company name assembled across
  two adjacent table cells. Company names are no longer allowed to span a newline.
- `Shanti Gopalkrishnan Sebi Registration`, `Indu Jacob Independent` — field labels and role words
  absorbed into names during seed expansion; now blocklisted.

### Residual weaknesses I would fix next

- **Address boundaries are approximate.** A few spans include a leading label
  (`Registered Office: 11/3, …`). Over-redaction, not under-redaction, but untidy.
- **A field code split across several `w:instrText` nodes** would be processed per node. Not
  observed in this document, but possible.
- **The DIN heuristic** treats a bare zero-leading 8-digit number as a DIN. Correct here, but it
  would misfire on a document that uses zero-padded reference numbers.
- **Scanned images are not touched.** PII inside an embedded image survives; that needs OCR.

---

## Extending it to a new PII type

Two places, by design:

```python
# 1. pii_redactor/detectors.py — how to find it
@register
class PassportDetector(Detector):
    pii_type = "PASSPORT"
    name = "passport.regex"
    _RE = re.compile(r"\b[A-PR-WY][1-9]\d\s?\d{4}[1-9]\b")

    def detect(self, text, context):
        for m in self._RE.finditer(text):
            yield self._span(m.start(), m.end(), text)

# 2. pii_redactor/surrogates.py — how to replace it
def passport(self, mention: str) -> str: ...
_DISPATCH = {..., "PASSPORT": "passport"}
```

Then add a priority in `core.PRIORITY` to say who wins when spans overlap. Overlap resolution,
docx rewriting, the audit log and the evaluation harness are all type-agnostic and need no change.
Set `needs_fit = True` if the detector wants a document-level learning pass.

---

## Files

| Path | What it is |
|---|---|
| `redact.py` | CLI entry point |
| `evaluate.py` | Scorer — token-level metrics plus a synthetic suite |
| `pii_redactor/core.py` | `Span`, detector base class, registry, overlap resolution |
| `pii_redactor/detectors.py` | One class per PII type |
| `pii_redactor/surrogates.py` | Consistent fake generation |
| `pii_redactor/lexicons.py` | Stoplists and vocabularies — the domain knowledge, in one place |
| `pii_redactor/docx_io.py` | Run-level docx traversal and rewriting |
| `pii_redactor/pipeline.py` | Orchestration |
| `eval/gold.json` | Hand-annotated gold standard (140 paragraphs) |
| `eval/sample.json` | The sampled paragraphs |
| `eval/results.json` | Full metrics, including every individual error |
| `out/…(redacted).docx` | The redacted document |
| `out/mapping.json` | real → fake lookup. **Sensitive — do not ship with the redacted file.** |
| `out/audit.jsonl` | One line per replacement, for spot-checking |
| `EVALUATION.md` | Evaluation approach and results |
