# Evaluation Report

**Document:** Red Herring Prospectus — KSH International Limited, dated December 10, 2025 (519 pages)
**Run:** rule layer only, no spaCy model available in the sandbox (see README, *Optional NER layer*)
**Reproduce:** `python evaluate.py --source "Red Herring Prospectus.docx" --unit-tests`

---

## 1. Evaluation approach

### Why token-level scoring

Metrics are computed **per token**, not per span. Two reasons:

1. **Span-exact matching is misleadingly harsh for free-text entities.** A detector that finds
   `Kirtane & Pandit` inside the gold span `Kirtane & Pandit, LLP` has done nearly all of the
   useful work, but exact matching scores it as one false positive *and* one false negative.
2. **Accuracy is meaningless without true negatives.** There is no natural unit for "a span that
   was correctly not detected". At the token level, every ordinary word is a genuine true
   negative, so accuracy is well defined.

Each token gets one gold label and one predicted label (a PII type, or `O`), and precision, recall
and F1 fall out of the resulting confusion matrix. Accuracy is `correct tokens / all tokens`.

### The gold standard

Annotating all 5,041 paragraphs by hand is not feasible, so a **stratified sample of 140
paragraphs (6,968 tokens)** was drawn and every PII mention in each was hand-labelled:

| Stratum | Paragraphs | Tokens | Gold PII tokens | Purpose |
|---|---|---|---|---|
| **A — PII-dense** | 70 | 3,785 | 261 | Measures recall where the PII actually lives |
| **B — random prose** | 70 | 3,183 | 90 | Measures false positives on text that is almost all negatives |

Stratum A was sampled from paragraphs matching contact-block and governance cues (`Contact
Person`, `Registered Office`, `Telephone`, `Promoter`, `Director`, `DIN`, `@`, …); stratum B was
sampled uniformly from everything else. Sampling is seeded (`random.seed(7)`) and reproducible.

The detector is **fitted on the whole source document**, not on the sample. Fitting on the sample
alone would flatter recall for names that only appear in a directors table elsewhere in the file.

### Three complementary checks

Because a 140-paragraph sample cannot see everything, the gold-standard score is backed by two
further checks:

- **Document-wide manual precision audit.** All 635 replacements — 277 distinct mentions — were
  reviewed by hand in `out/audit.jsonl`. **Zero false positives.**
- **Residual-PII scan.** The redacted `.docx` is unzipped and every XML part re-scanned with
  independent patterns for the PII known to be in the source. This catches leaks in places the
  detector never visited (field codes, headers, relationship targets).
- **Synthetic suite** (`--unit-tests`) for the four required PII types that do not occur in this
  document, plus negative controls.

### Honest caveats

- The gold annotations and the scope rules were authored by the same person who wrote the
  detector. Precision of 1.000 should be read with that in mind — an independent annotator would
  be a stronger test. The stratum-B result (3,183 tokens of ordinary prose, zero false positives)
  is the more meaningful precision signal, since those paragraphs were sampled blind.
- Recall is measured on a sample. The document-wide residual scan is the check against a
  systematic blind spot, and it found one (bare locality names).
- Metrics were computed with the NER layer off. NER should improve ORG recall and could introduce
  new false positives; that run has not been measured.

---

## 2. Results — gold standard

**6,968 tokens · 351 gold PII tokens**

| Metric | Value |
|---|---|
| **Token accuracy** | **0.9986** |
| **Micro precision** | **1.0000** |
| **Micro recall** | **0.9715** |
| **Micro F1** | **0.9855** |
| Macro precision | 1.0000 |
| Macro recall | 0.9853 |
| Macro F1 | 0.9922 |

### Per type

| PII type | Support | TP | FP | FN | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|---:|
| PERSON | 83 | 83 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| ORG | 85 | 75 | 0 | 10 | 1.000 | 0.882 | 0.938 |
| ADDRESS | 28 | 28 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| EMAIL | 76 | 76 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| PHONE | 50 | 50 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| URL | 25 | 25 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| REG_ID | 3 | 3 | 0 | 0 | 1.000 | 1.000 | 1.000 |
| CIN | 1 | 1 | 0 | 0 | 1.000 | 1.000 | 1.000 |

### By stratum

| Stratum | Tokens | Gold PII | Accuracy | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|
| A — PII-dense | 3,785 | 261 | 0.9989 | 1.000 | 0.9847 | 0.9923 |
| B — random prose | 3,183 | 90 | 0.9981 | 1.000 | 0.9333 | 0.9655 |

### Every remaining error

All 10 false-negative tokens are organisations with no legal suffix — a single, well-understood
failure mode:

| Paragraph | Missed | Why |
|---|---|---|
| 67 | `Financial Express`, `Jansatta`, `Loksatta` | Newspaper titles; no incorporation marker |
| 97 | `Sterlite Copper` | Brand name, written after `Vedanta Limited` (which *was* caught) |
| 122 | `Chakan Internal Kamgar Sangathna` | Trade union; the `KSH International` prefix was caught, the rest was not |

There are **no false positives and no type confusions**.

---

## 3. Results — synthetic suite

Covers the four required PII types absent from this prospectus (`SSN`, `CREDIT_CARD`,
`DATE_OF_BIRTH`, `IP_ADDRESS`), plus `AADHAAR`/`PAN`, plus negative controls.

| Metric | Value |
|---|---|
| Token accuracy | 1.0000 |
| Precision / Recall / F1 | 1.000 / 1.000 / 1.000 |
| Failing cases | 0 of 8 |

The negative controls matter as much as the positives — these are **not** redacted:

- `Order 4111111111111112 shipped on ticket 100200300 for Fiscal 2025.`
  (a 16-digit order number that fails Luhn; a ticket number)
- `Refer to page 280 and section 12(1) of the Companies Act, 2013.`
- `The resolution passed on May 6, 2025 was filed with the Registrar of Companies.`
  (a date with no birth cue)

Per the assignment's precision criterion: **order and ticket numbers are treated as non-sensitive**
and are deliberately left intact.

---

## 4. Results — full-document run

5,041 paragraphs scanned · 379 modified · **635 replacements across 277 distinct mentions** ·
23 seconds.

| PII type | Occurrences | Distinct mentions |
|---|---:|---:|
| PERSON | 211 | 64 |
| ORG | 207 | 81 |
| ADDRESS | 74 | 53 |
| EMAIL | 52 | 26 |
| PHONE | 36 | 22 |
| URL | 26 | 14 |
| REG_ID | 13 | 6 |
| CIN | 9 | 4 |
| DIN | 7 | 7 |
| **Total** | **635** | **277** |

`SSN`, `CREDIT_CARD`, `DATE_OF_BIRTH` and `IP_ADDRESS` are supported but **do not occur in this
document** — confirmed by scanning every XML part of the source package, not just the body text.
The CLI reports this explicitly rather than silently showing a zero.

### Residual-PII scan of the redacted output

| Pattern class | Distinct in source | Residual in output |
|---|---:|---:|
| Email addresses | 50 | **0** |
| Phone numbers (+91) | 20 | **0** |
| CIN | 4 | **0** |
| SEBI registration numbers | 6 | **0** |
| Director Identification Numbers | 7 | **0** |
| Promoter / director surnames | 10 | **0** |
| Address localities | 7 | 1 |

The single residual is `Birdewadi` in the unit label `Chakan Unit No. 2 (Birdewadi)` — a bare
village name, which is out of scope by the stated rule that only full postal addresses are
redacted (see README, *Scope decisions*).

The 50 distinct source emails include hyperlink field-code occurrences invisible in the body text.
Before `w:instrText` handling was added, 12 of them survived redaction while the visible text
showed fakes — a leak that no body-text evaluation would ever have caught, and the strongest
argument for scanning the output package rather than trusting the detector's own report.

---

## 5. Summary

| | Precision | Recall | Accuracy |
|---|---:|---:|---:|
| Gold standard, all types | 1.000 | 0.972 | 0.9986 |
| Gold standard, excluding suffix-less ORG | 1.000 | 1.000 | 1.000 |
| Synthetic suite | 1.000 | 1.000 | 1.000 |
| Document-wide manual audit (277 mentions) | 1.000 | — | — |

The system is tuned for precision, on the view that a redaction tool which mangles a document
gets switched off, and that under-redaction should be caught by the audit log rather than by
blanket over-redaction. The cost of that choice is visible and bounded: organisations that carry
no incorporation marker are missed, and every one of them is listed above.
