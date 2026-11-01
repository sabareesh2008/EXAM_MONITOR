from __future__ import annotations
import re
from datetime import date
from pathlib import Path
from typing import Any
import fitz
from vsb_watch.schedule import EXAM_DAYS

REGISTER_RE = re.compile(r'(?<!\d)\d{9,15}(?!\d)')
DATE_TOKEN_RE = re.compile(r'(?<!\d)(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})(?!\d)')
ISO_DATE_RE = re.compile(r'(?<!\d)(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})(?!\d)')
MONTH_DATE_RE = re.compile(r'\b(\d{1,2})\s+(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(20\d{2})\b', re.I)
SESSION_RE = re.compile(r'\bSESSION\s*[:=-]?\s*(FN|AN)\b', re.I)
FILENAME_SESSION_RE = re.compile(r'(?:^|[._\-\s])(FN|AN)(?:[._\-\s]|$)', re.I)
HALL_RE = re.compile(r'(?:HALL\s*(?:NUMBER|NO\.?|#)?|ROOM\s*(?:NUMBER|NO\.?|#)?)\s*[:=-]?\s*([A-Z]{0,5}\s*[A-Z]*\s*\d+[A-Z]?)', re.I)
SEAT_RE = re.compile(r'(?:SEAT\s*(?:NUMBER|NO\.?|#)?|BENCH\s*(?:NUMBER|NO\.?|#)?)\s*[:=-]?\s*([A-Z0-9/-]+)', re.I)
MONTHS = {m.lower(): i for i, m in enumerate(("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"), 1)}
SCHEDULED_DATES = {x.exam_date for x in EXAM_DAYS}

def _to_date(y: int, m: int, d: int):
    if y < 100: y += 2000 if y < 70 else 1900
    try: return date(y, m, d)
    except ValueError: return None

def _find_scheduled_date(text: str, filename: str = "") -> str | None:
    # Prefer a date explicitly labelled as the examination date.
    labelled = re.compile(r'(?:DATE\s+OF\s+EXAM(?:INATION)?|EXAM(?:INATION)?\s+DATE)\s*[:=-]?\s*(\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})', re.I)
    for source in (text, filename):
        m = labelled.search(source)
        if m:
            d, mo, y = map(int, re.split(r'[-/.]', m.group(1)))
            parsed = _to_date(y, mo, d)
            if parsed: return parsed.isoformat()
    # Filename dates are commonly embedded in VSB allotment names (e.g. 06.11.26-FN).
    m = DATE_TOKEN_RE.search(filename)
    if m:
        d, mo, y = map(int, m.groups()); parsed = _to_date(y, mo, d)
        if parsed: return parsed.isoformat()
    # Use an unlabelled date only when exactly one configured exam date occurs in the PDF.
    found = set()
    for d, mo, y in DATE_TOKEN_RE.findall(text):
        parsed = _to_date(int(y), int(mo), int(d))
        if parsed: found.add(parsed)
    for y, mo, d in ISO_DATE_RE.findall(text):
        parsed = _to_date(int(y), int(mo), int(d))
        if parsed: found.add(parsed)
    for d, month, y in MONTH_DATE_RE.findall(text):
        key = month.lower()
        month_num = next((n for name, n in MONTHS.items() if name.startswith(key[:3])), None)
        if month_num:
            parsed = _to_date(int(y), month_num, int(d))
            if parsed: found.add(parsed)
    return next(iter(found)).isoformat() if len(found) == 1 else None

def _find_session(text: str, filename: str = "") -> str | None:
    m = SESSION_RE.search(text)
    if m: return m.group(1).upper()
    m = FILENAME_SESSION_RE.search(filename)
    return m.group(1).upper() if m else None

def read_pdf_text(pdf_path: Path) -> list[str]:
    with fitz.open(pdf_path) as doc:
        return [p.get_text('text', sort=True) for p in doc]

def _ocr_page(page):
    try:
        import pytesseract
        from PIL import Image
        import io
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
        return pytesseract.image_to_string(Image.open(io.BytesIO(pix.tobytes('png'))))
    except Exception:
        return ''

def extract_pdf_metadata(pdf_path: Path, ocr_fallback: bool = True) -> dict[str, Any]:
    pages = []
    with fitz.open(pdf_path) as doc:
        for page in doc:
            txt = page.get_text('text', sort=True)
            if not txt.strip() and ocr_fallback: txt = _ocr_page(page)
            pages.append(txt)
    full = '\n'.join(pages); upper = full.upper()
    regs = sorted(set(REGISTER_RE.findall(full)))
    doc_type = 'department-wise' if 'LIST OF STUDENTS REGISTERED' in upper or 'HALL NUMBER' in upper else ('room-wise' if 'SEAT' in upper or 'BENCH' in upper else 'unknown')
    return {'page_count': len(pages), 'exam_date': _find_scheduled_date(full, pdf_path.name),
            'session': _find_session(full, pdf_path.name), 'document_type': doc_type,
            'register_numbers_found': len(regs), 'register_numbers': regs,
            'text_extractable': bool(full.strip()), 'text': full}

def extract_student_allotment(pdf_path: Path, register_number: str) -> dict[str, Any] | None:
    target = re.sub(r'\s+', '', register_number)
    if not target or not target.isdigit(): raise ValueError('Register number must contain digits only')
    with fitz.open(pdf_path) as doc:
        for pi, page in enumerate(doc):
            text = page.get_text('text', sort=True)
            compact = re.sub(r'\s+', '', text)
            if not re.search(r'(?<!\d)' + re.escape(target) + r'(?!\d)', compact): continue
            lines = [x.strip() for x in text.splitlines() if x.strip()]
            idx = next((i for i, line in enumerate(lines) if target in re.sub(r'\s+', '', line)), -1)
            window = ' | '.join(lines[max(0, idx-5):min(len(lines), idx+6)]) if idx >= 0 else text
            hall = HALL_RE.search(window); seat = SEAT_RE.search(window)
            return {'register_number': target, 'page': pi+1,
                    'hall_number': hall.group(1).strip() if hall else None,
                    'seat_number': seat.group(1).strip() if seat else None,
                    'context': window[:1200],
                    'extraction_confidence': 'high' if hall or seat else 'register-only'}
    return None

def search_register_in_pdf(pdf_path: Path, register_number: str) -> list[dict[str, Any]]:
    result = extract_student_allotment(pdf_path, register_number)
    return [result] if result else []
