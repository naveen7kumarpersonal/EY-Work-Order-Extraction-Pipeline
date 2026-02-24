# src/cleaner.py
"""
Text cleaning utilities for noisy PDF OCR output.
Handles common artifacts in Indian coal work order documents.
"""

import re


# Words that appear letter-spaced in these scanned PDFs
_LETTER_SPACED_WORDS = [
    (r'\bW\s+O\s+R\s+K\s+O\s+R\s+D\s+E\s+R\b', 'WORK ORDER'),
    (r'\bC\s+O\s+A\s+L\b', 'COAL'),
    (r'\bP\s+a\s+g\s+e\b', 'Page'),
    (r'\bh\s+a\s+n\s+d\s+l\s+i\s+n\s+g\b', 'handling'),
    (r'\bt\s+r\s+a\s+n\s+s\s+p\s+o\s+r\s+t\b', 'transport'),
    (r'\bc\s+o\s+m\s+m\s+e\s+n\s+c\s+e\s+m\s+e\s+n\s+t\b', 'commencement'),
    (r'\bs\s+t\s+a\s+t\s+u\s+t\s+o\s+r\s+y\b', 'statutory'),
    (r'\be\s+n\s+v\s+i\s+r\s+o\s+n\s+m\s+e\s+n\s+t\s+a\s+l\b', 'environmental'),
    (r'\bc\s+o\s+m\s+p\s+l\s+i\s+a\s+n\s+c\s+e\b', 'compliance'),
    (r'\bL\s+O\s+A\s+D\s+I\s+N\s+G\b', 'LOADING'),
    (r'\bT\s+R\s+A\s+N\s+S\s+P\s+O\s+R\s+T\s+A\s+T\s+I\s+O\s+N\b', 'TRANSPORTATION'),
    (r'\bH\s+A\s+N\s+D\s+L\s+I\s+N\s+G\b', 'HANDLING'),
    (r'\bL\s+I\s+F\s+T\s+I\s+N\s+G\b', 'LIFTING'),
]


def fix_letter_spacing(text: str) -> str:
    """Fix only known letter-spaced words — does NOT blindly join all single letters."""
    for pattern, replacement in _LETTER_SPACED_WORDS:
        text = re.sub(pattern, replacement, text, flags=re.I)
    return text


def clean_text(text: str | None) -> str:
    """
    Clean a single string extracted from noisy OCR output.
    Fixes specific known artifacts without mangling valid text.
    """
    if not text or not isinstance(text, str):
        return ""

    text = text.strip()

    # Collapse multiple whitespace
    text = re.sub(r'\s+', ' ', text)

    # Fix known letter-spaced words first (targeted, not greedy)
    text = fix_letter_spacing(text)

    # Remove repeated hash noise (### or # # #) but preserve single # used as bullet
    text = re.sub(r'#{2,}', '', text)
    text = re.sub(r'\s#\s', ' ', text)  # lone # used as separator

    # Normalize label separators: ":-" or ":- " → ": "
    text = re.sub(r'\s*:-\s*', ': ', text)

    # Keep placeholders readable: < VENDOR NAME > → <VENDOR NAME>
    text = re.sub(r'<\s*([^>]+?)\s*>', lambda m: f"<{m.group(1).strip()}>", text)

    # Strip trailing/leading noise characters
    text = text.strip(' .,:;-#*')

    return text.strip()


def clean_raw_paragraph(text: str) -> str:
    """
    Lighter clean for a single raw paragraph — preserves structure,
    only removes OCR noise. Use this when building full_text from paragraphs.
    """
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', text.strip())
    text = fix_letter_spacing(text)
    text = re.sub(r'#{2,}', '', text)
    text = re.sub(r'\s#\s', ' ', text)
    text = re.sub(r'\s*:-\s*', ': ', text)
    text = re.sub(r'<\s*([^>]+?)\s*>', lambda m: f"<{m.group(1).strip()}>", text)
    return text.strip()


def clean_full_document_text(raw_text: str) -> str:
    """
    Clean larger blocks of concatenated text for LLM / regex consumption.
    Strips page headers/footers, short noise lines.
    """
    if not raw_text:
        return ""

    lines = raw_text.split('\n')
    cleaned_lines = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Drop page header/footer lines
        if re.match(r'^Page\s*:\s*\d+\s*(of\s*\d+)?$', line, re.I):
            continue
        if re.match(r'^Order\s+Continuation\s+Sheet\s*$', line, re.I):
            continue
        if re.match(r'^Order\s+No\.?\s*$', line, re.I):
            continue
        # Drop very short noise (single chars, just numbers, just symbols)
        if len(line) < 4:
            continue
        cleaned_lines.append(clean_raw_paragraph(line))

    full_clean = ' '.join(cleaned_lines)
    full_clean = re.sub(r'\s{2,}', ' ', full_clean)
    return full_clean.strip()


if __name__ == "__main__":
    samples = [
        "P a g e s   o f   4 5",
        "W O R K   O R D E R",
        "Vendor Code :- <VENDOR CODE>",
        "Order Date :- 26.09.2024",
        "All CGST-SGST/IGST @ 18% Creditable",
        "Diesel component in PVC : 33%",
        "# # Company # means # <CLIENT NAME> LTD",
        "Transportation of material (Coal & coal products) from the designated loading point",
    ]
    for s in samples:
        print(f"IN:  {s}")
        print(f"OUT: {clean_text(s)}")
        print()