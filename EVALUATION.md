# Evaluation Report

**Document:** Red Herring Prospectus, KSH International Limited, dated December 10, 2025 (519 pages)
**This run:** rules only, no spaCy model available while I was building it (see README)
**To reproduce:** `python evaluate.py --source "Red Herring Prospectus.docx" --unit-tests`

## 1. How I evaluated it

### Why I score per token instead of per span

I started out scoring whole spans and threw it away, for two reasons.

First, it's unfairly harsh on the free-text types. My detector finds `Kirtane & Pandit` inside the
gold span `Kirtane & Pandit, LLP`. That's nearly all of the useful work done, but exact span
matching calls it one false positive *and* one false negative, which tells me nothing about whether
the tool is any good.

Second, accuracy needs true negatives to mean anything, and there's no sensible unit for "a span
that was correctly not detected". Per token, every ordinary word is a real true negative, so
accuracy is actually well defined.

So each token gets one gold label and one predicted label - a PII type, or `O` - and precision,
recall and F1 come out of the confusion matrix. Accuracy is just correct tokens over all tokens.

### The gold standard

I couldn't hand-annotate 5,041 paragraphs, so I took a stratified sample of 140 paragraphs (6,968
tokens) and labelled every PII mention in each one:

| Stratum | Paragraphs | Tokens | Gold PII tokens | Why |
|---|---|---|---|---|
| A - PII-dense | 70 | 3,785 | 261 | Measures recall where the PII actually is |
| B - random prose | 70 | 3,183 | 90 | Measures false positives on text that's nearly all negatives |

Stratum A was drawn from paragraphs matching contact-block and governance cues (`Contact Person`,
`Registered Office`, `Telephone`, `Promoter`, `Director`, `DIN`, `@`). Stratum B was drawn
uniformly from everything else. Sampling is seeded so it's reproducible.

The detector is fitted on the whole source document, not on the sample. Fitting on the sample alone
would have flattered recall for names that only ever appear in a directors table somewhere else in
the file.

### Two more checks, because a sample can't see everything

- **Manual precision audit over the whole document.** I went through all 635 replacements - 277
  distinct mentions - by hand in `out/audit.jsonl`. No false positives.
- **Residual-PII scan.** I unzip the redacted .docx and re-scan every XML part with independent
  patterns for the PII I know is in the source. This catches leaks in places the detector never
  visited, and it did catch one.
- **Synthetic suite** (`--unit-tests`) for the four required types that don't appear in this
  document at all, plus negative controls.

### Things worth being upfront about

- I wrote both the detector and the gold annotations, so precision of 1.000 should be read with
  that in mind. An independent annotator would be a much stronger test. The stratum B number is
  the more trustworthy signal - 3,183 tokens of ordinary prose sampled blind, no false positives.
- Recall is measured on a sample. The document-wide residual scan is my guard against a systematic
  blind spot, and it found one (bare locality names).
- These numbers are with NER off. Turning it on should help ORG recall and might introduce new
  false positives; I haven't been able to measure that run.

## 2. Results against the gold standard

6,968 tokens, 351 of them PII.

| Metric | Value |
|---|---|
| Token accuracy | 0.9986 |
| Micro precision | 1.0000 |
| Micro recall | 0.9715 |
| Micro F1 | 0.9855 |
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
| A - PII-dense | 3,785 | 261 | 0.9989 | 1.000 | 0.9847 | 0.9923 |
| B - random prose | 3,183 | 90 | 0.9981 | 1.000 | 0.9333 | 0.9655 |

### Every error that's left

All ten false-negative tokens are companies with no legal suffix. It's one failure mode, not ten:

| Paragraph | Missed | Why |
|---|---|---|
| 67 | `Financial Express`, `Jansatta`, `Loksatta` | Newspaper names, no incorporation marker |
| 97 | `Sterlite Copper` | Brand name, written right after `Vedanta Limited` which was caught |
| 122 | `Chakan Internal Kamgar Sangathna` | Trade union; the `KSH International` prefix was caught, the rest wasn't |

No false positives, no type confusions.

## 3. Synthetic suite

Covers the four required types that don't occur in this prospectus (SSN, credit card, date of
birth, IP address), plus Aadhaar and PAN, plus negative controls.

| Metric | Value |
|---|---|
| Token accuracy | 1.0000 |
| Precision / Recall / F1 | 1.000 / 1.000 / 1.000 |
| Failing cases | 0 of 8 |

The negative controls matter as much as the positive ones. None of these get touched:

- `Order 4111111111111112 shipped on ticket 100200300 for Fiscal 2025.` - a 16-digit order number
  that fails Luhn, and a ticket number
- `Refer to page 280 and section 12(1) of the Companies Act, 2013.`
- `The resolution passed on May 6, 2025 was filed with the Registrar of Companies.` - a date with
  no birth cue anywhere near it

On the brief's precision question: I treat order and ticket numbers as not sensitive, and leave
them intact.

## 4. The full document run

5,041 paragraphs scanned, 379 changed, 635 replacements across 277 distinct mentions, about 20
seconds.

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
| Total | 635 | 277 |

SSN, credit card, date of birth and IP address are all supported but genuinely don't occur here. I
checked by scanning every XML part of the source package, not just the body text. The CLI says so
explicitly rather than quietly printing a zero.

### Residual scan of the output

| Pattern | Distinct in source | Left in output |
|---|---:|---:|
| Email addresses | 50 | 0 |
| Phone numbers (+91) | 20 | 0 |
| CIN | 4 | 0 |
| SEBI registration numbers | 6 | 0 |
| Director Identification Numbers | 7 | 0 |
| Promoter and director surnames | 10 | 0 |
| Address localities | 7 | 1 |

The one left is `Birdewadi` in `Chakan Unit No. 2 (Birdewadi)`. It's a bare village name, which my
scope rules say to leave alone.

That count of 50 distinct source emails includes ones that only exist inside hyperlink field codes
and never appear as visible text. Before I handled `w:instrText`, 12 of them survived redaction
while the visible text showed fakes. No amount of checking the body text would have caught that,
which is the whole argument for scanning the output package instead of trusting the detector's own
report.

## 5. Summary

| | Precision | Recall | Accuracy |
|---|---:|---:|---:|
| Gold standard, all types | 1.000 | 0.972 | 0.9986 |
| Gold standard, excluding suffix-less companies | 1.000 | 1.000 | 1.000 |
| Synthetic suite | 1.000 | 1.000 | 1.000 |
| Manual audit, 277 distinct mentions | 1.000 | - | - |

I tuned this for precision. A redaction tool that mangles the document gets switched off and stops
protecting anything, and under-redaction is something the audit log lets a human catch. The price
of that choice is companies without an incorporation marker, and I've listed every one I know
about.
