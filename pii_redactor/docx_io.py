from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Iterator, List, Sequence, Set, Tuple

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table, _Cell
from docx.text.paragraph import Paragraph
from docx.text.run import Run

from .core import Span


def iter_block_paragraphs(container) -> Iterator[Paragraph]:
    for para in getattr(container, "paragraphs", []):
        yield para
    for table in getattr(container, "tables", []):
        yield from iter_table_paragraphs(table)


def iter_table_paragraphs(table: Table) -> Iterator[Paragraph]:
    for tr in table._tbl.tr_lst:
        for tc in tr.tc_lst:
            yield from iter_block_paragraphs(_Cell(tc, table))


def iter_all_paragraphs(doc: Document) -> Iterator[Paragraph]:
    yield from iter_block_paragraphs(doc)
    for section in doc.sections:
        for part in (
            section.header,
            section.footer,
            section.first_page_header,
            section.first_page_footer,
            section.even_page_header,
            section.even_page_footer,
        ):
            if part is not None:
                yield from iter_block_paragraphs(part)


def paragraph_runs(para: Paragraph) -> List[Run]:
    return [Run(r, para) for r in para._p.xpath(".//w:r")]


def paragraph_text(para: Paragraph) -> str:
    return "".join(_run_text(r) for r in paragraph_runs(para))


def _run_text(run: Run) -> str:
    parts: List[str] = []
    for child in run._r:
        tag = child.tag
        if tag == qn("w:t"):
            parts.append(child.text or "")
        elif tag == qn("w:tab"):
            parts.append("\t")
        elif tag in (qn("w:br"), qn("w:cr")):
            parts.append("\n")
    return "".join(parts)


def _set_run_text(run: Run, text: str) -> None:
    for child in list(run._r):
        if child.tag in (qn("w:t"), qn("w:tab"), qn("w:br"), qn("w:cr")):
            run._r.remove(child)
    if text:
        run.text = text


def extract_full_text(doc: Document) -> str:
    return "\n".join(paragraph_text(p) for p in iter_all_paragraphs(doc))


_NAME_HEADERS = {"name", "name of the promoter", "name of promoter",
                 "name of the shareholder", "name of shareholder",
                 "name of the director", "name of director",
                 "name of the selling shareholder", "promoter selling shareholder",
                 "name of key managerial personnel", "name of the partner"}
_PERSON_TABLE_SIGNALS = {"din", "designation", "date of birth", "age", "term"}


def harvest_table_person_seeds(doc: Document) -> Set[str]:
    seeds: Set[str] = set()
    for table in doc.tables:
        if not table.rows:
            continue
        header = [re.sub(r"\s+", " ", c.text).strip().lower() for c in table.rows[0].cells]
        name_cols = [i for i, h in enumerate(header) if h in _NAME_HEADERS]
        if not name_cols:
            continue
        if not any(any(sig in h for sig in _PERSON_TABLE_SIGNALS) for h in header):
            continue
        for row in table.rows[1:]:
            cells = row.cells
            for i in name_cols:
                if i >= len(cells):
                    continue
                value = re.sub(r"\s+", " ", cells[i].text).strip()
                value = value.strip("*^&#†‡ ").strip()
                if value:
                    seeds.add(value)
    return seeds


@dataclass
class RedactionStats:
    paragraphs_scanned: int = 0
    paragraphs_changed: int = 0
    spans_replaced: int = 0
    field_codes_changed: int = 0
    hyperlinks_changed: int = 0


def rewrite_paragraph(para: Paragraph, spans: Sequence[Span], replace: Callable[[Span], str]) -> int:
    if not spans:
        return 0

    runs = paragraph_runs(para)
    if not runs:
        return 0

    offsets: List[Tuple[int, int]] = []
    cursor = 0
    for run in runs:
        length = len(_run_text(run))
        offsets.append((cursor, cursor + length))
        cursor += length
    text_len = cursor

    ordered = sorted((s for s in spans if s.end <= text_len), key=lambda s: s.start)
    if not ordered:
        return 0

    emitted = [False] * len(ordered)
    applied = 0

    for run, (run_start, run_end) in zip(runs, offsets):
        if run_start == run_end:
            continue
        original = _run_text(run)
        if not any(s.start < run_end and run_start < s.end for s in ordered):
            continue

        out: List[str] = []
        pos = run_start
        while pos < run_end:
            covering = next(
                (i for i, s in enumerate(ordered) if s.start <= pos < s.end), None
            )
            if covering is None:
                nxt = min(
                    (s.start for s in ordered if s.start > pos), default=run_end
                )
                stop = min(nxt, run_end)
                out.append(original[pos - run_start : stop - run_start])
                pos = stop
            else:
                if not emitted[covering]:
                    out.append(replace(ordered[covering]))
                    emitted[covering] = True
                    applied += 1
                pos = min(ordered[covering].end, run_end)
        _set_run_text(run, "".join(out))

    return applied


def _story_roots(doc: Document) -> List:
    roots = [doc.element.body]
    for section in doc.sections:
        for part in (
            section.header,
            section.footer,
            section.first_page_header,
            section.first_page_footer,
            section.even_page_header,
            section.even_page_footer,
        ):
            if part is not None:
                roots.append(part._element)
    unique, seen = [], set()
    for root in roots:
        if id(root) not in seen:
            seen.add(id(root))
            unique.append(root)
    return unique


def rewrite_field_codes(doc: Document, redact: Callable[[str], str]) -> int:
    changed = 0
    for root in _story_roots(doc):
        for node in root.iter(qn("w:instrText")):
            original = node.text or ""
            if not original.strip():
                continue
            replaced = redact(original)
            if replaced != original:
                node.text = replaced
                changed += 1
        for node in root.iter(qn("w:fldSimple")):
            instr = node.get(qn("w:instr")) or ""
            if not instr.strip():
                continue
            replaced = redact(instr)
            if replaced != instr:
                node.set(qn("w:instr"), replaced)
                changed += 1
    return changed


_MAILTO = re.compile(r"(?i)^mailto:(.+)$")


def rewrite_hyperlink_targets(doc: Document, replace_email: Callable[[str], str],
                              replace_url: Callable[[str], str]) -> int:
    changed = 0
    parts = [doc.part] + [s.header.part for s in doc.sections if s.header is not None]
    parts += [s.footer.part for s in doc.sections if s.footer is not None]
    for part in dict.fromkeys(parts):
        for rel in list(part.rels.values()):
            if not rel.is_external:
                continue
            target = rel._target
            if not isinstance(target, str):
                continue
            mail = _MAILTO.match(target)
            try:
                if mail:
                    rel._target = "mailto:" + replace_email(mail.group(1))
                    changed += 1
                elif target.lower().startswith(("http://", "https://", "www.")):
                    rel._target = replace_url(target)
                    changed += 1
            except Exception:
                continue
    return changed
