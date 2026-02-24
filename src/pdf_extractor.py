# src/pdf_extractor.py
"""
Direct PDF text extraction using pypdf.

WHY THIS EXISTS
---------------
Azure DI's prebuilt-layout returns paragraphs only for "structured" content.
For this 51-page work order PDF, DI only covers pages 1-2. All C/O notes,
exit clauses, safety norms, ceiling values live on pages 3-51 and were invisible.

THE FIX: extract text directly from PDF with pypdf (free, instant, no quota).

TWO-COLUMN NOTE
---------------
Page 1 has a two-column layout. pypdf reads left-column labels first, then
right-column values. resolve_two_column_headers() pairs them up by position.
"""

import re
from pypdf import PdfReader

# Noise lines that repeat on every "Order Continuation Sheet" page
# FIX: only strip "Order No. Test Contract Number" — NOT bare "Order No."
# (bare "Order No." is a real label on page 1 and was being incorrectly stripped)
_NOISE_PATTERNS = [
    r'^Order\s+Continuation\s+Sheet\s*$',
    r'^Order\s+No\.?\s+Test\s+(?:Contract\s+Number|Order\s+No\.?)\s*$',
    r'^Page\s*:\s*\d+\s+of\s+\d+\s*$',
]
_NOISE_RE = re.compile('|'.join(_NOISE_PATTERNS), re.I | re.M)

# Two-column header labels on page 1
_TWO_COL_LABELS = {
    'Order No.'     : 'Order Number',
    'Order Date'    : 'Order Date',
    'Release Date'  : 'Release Date',
    'Contact Person': 'Contact Person',
    'E-Mail'        : 'Contact Email',
}

_last_two_col_headers: dict = {}


def resolve_two_column_headers(lines: list) -> dict:
    """Pair up two-column label/value lines from page 1."""
    result = {}
    i = 0
    while i < len(lines):
        if lines[i] in _TWO_COL_LABELS:
            labels = []
            while i < len(lines) and lines[i] in _TWO_COL_LABELS:
                labels.append(lines[i])
                i += 1
            values = []
            while i < len(lines) and re.match(r'^:-', lines[i]):
                val = re.sub(r'^:-\s*', '', lines[i]).strip()
                values.append(val)
                i += 1
            for label, value in zip(labels, values):
                if value:
                    result[_TWO_COL_LABELS[label]] = value
        else:
            i += 1
    return result


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract all text from PDF, pipe-separated by paragraph."""
    global _last_two_col_headers
    _last_two_col_headers = {}

    reader = PdfReader(pdf_path)
    n_pages = len(reader.pages)
    pages_text = []

    for i, page in enumerate(reader.pages):
        raw = page.extract_text() or ""
        if not raw.strip():
            continue

        lines = []
        for line in raw.split('\n'):
            line = line.strip()
            if line and not _NOISE_RE.match(line):
                lines.append(line)

        if i == 0:
            _last_two_col_headers = resolve_two_column_headers(lines)

        page_text = ' | '.join(lines)
        if page_text.strip():
            pages_text.append(page_text)

    full_text = ' | '.join(pages_text)
    full_text = re.sub(r'\s{2,}', ' ', full_text)

    print(f"  PDF: {n_pages} pages → {len(full_text):,} chars ({len(full_text.split()):,} words)")
    return full_text


def get_two_col_headers() -> dict:
    """Return header fields resolved from page 1 two-column layout."""
    return _last_two_col_headers