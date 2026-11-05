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

def _page_hall_number(page_text: str) -> str | None:
    labelled = HALL_RE.search(page_text)
    if labelled:
        return re.sub(r'\s+', ' ', labelled.group(1)).strip()
    # VSB seating PDFs commonly print a room heading such as "EXAM HALL : MB III 101".
    m = re.search(r'\bMB\s+(?:I{1,3}|IV|V)\s+[A-Z]?\s*\d{2,4}[A-Z]?\b', page_text, re.I)
    return re.sub(r'\s+', ' ', m.group(0)).strip() if m else None

def _rectangles(page) -> list[fitz.Rect]:
    """Return actual rectangular outlines drawn in the PDF page."""
    found = []
    for drawing in page.get_drawings():
        for item in drawing.get("items", []):
            if item[0] == "re":
                rect = fitz.Rect(item[1])
                if rect.width >= 8 and rect.height >= 8:
                    found.append(rect)
    # De-duplicate coincident rectangle paths.
    unique = []
    for rect in found:
        if not any(abs(rect.x0-r.x0)<1 and abs(rect.y0-r.y0)<1 and
                   abs(rect.x1-r.x1)<1 and abs(rect.y1-r.y1)<1 for r in unique):
            unique.append(rect)
    return unique


def _inside(word, rect, pad=1.5) -> bool:
    x0, y0, x1, y1 = word[:4]
    return (x0 >= rect.x0-pad and y0 >= rect.y0-pad and
            x1 <= rect.x1+pad and y1 <= rect.y1+pad)


def _find_seat_from_words(page, target: str) -> dict[str, Any] | None:
    """Resolve seat only from the numeric left cell adjacent to the register cell."""
    words = page.get_text("words")
    rects = _rectangles(page)
    target_words = [w for w in words if w[4].strip() == target]
    candidates = []
    for tw in target_words:
        target_rects = [r for r in rects if _inside(tw, r)]
        for target_rect in target_rects:
            left_cells = []
            for r in rects:
                overlap = max(0, min(r.y1, target_rect.y1)-max(r.y0, target_rect.y0))
                ratio = overlap / max(1, min(r.height, target_rect.height))
                if (r.x1 <= target_rect.x0 + 2 and
                    target_rect.x0-r.x1 <= max(4, target_rect.height*0.25) and
                    ratio >= 0.65 and 0.55 <= r.height/target_rect.height <= 1.8):
                    left_cells.append(r)
            if not left_cells:
                continue
            # The immediately adjacent cell is the one with the greatest right edge.
            nearest_edge = max(r.x1 for r in left_cells)
            nearest = [r for r in left_cells if abs(r.x1-nearest_edge) < 0.75]
            if len(nearest) != 1:
                continue
            left = nearest[0]
            cell_words = [w for w in words if _inside(w, left)]
            numeric = [w for w in cell_words if re.fullmatch(r"\d{1,3}", w[4].strip())]
            # Require exactly one numeric value in the seat cell.
            valid = [w for w in numeric if 1 <= int(w[4]) <= 200]
            if len(valid) == 1 and len(numeric) == 1:
                seat_word = valid[0]
                candidates.append({
                    "seat_number": seat_word[4].strip(),
                    "register_rect": tuple(target_rect),
                    "seat_rect": tuple(left),
                    "register_rect_obj": target_rect,
                    "seat_rect_obj": left,
                })
    # Multiple distinct box-pairs are ambiguous, never choose the first.
    unique = {}
    for c in candidates:
        key = (c["seat_number"], tuple(round(x, 1) for x in c["register_rect"]))
        unique[key] = c
    return next(iter(unique.values())) if len(unique) == 1 else None


def extract_student_allotment(pdf_path: Path, register_number: str) -> dict[str, Any] | None:
    """Find a register number across all pages; seating-chart seats require adjacent boxes."""
    target = re.sub(r"\s+", "", register_number)
    if not target or not target.isdigit():
        raise ValueError("Register number must contain digits only")
    matches = []
    with fitz.open(pdf_path) as doc:
        for pi, page in enumerate(doc):
            words = page.get_text("words")
            # Exact whole-word match only. No digit-stripping of arbitrary text fragments.
            target_words = [w for w in words if w[4].strip() == target]
            text = page.get_text("text", sort=True)
            if not target_words and not re.search(r"(?<!\d)" + re.escape(target) + r"(?!\d)", text):
                continue
            hall = _page_hall_number(text)
            if not hall:
                rooms = re.findall(r"\bMB\s+(?:I{1,3}|IV|V)\s+[A-Z]?\s*\d{2,4}[A-Z]?\b", text, re.I)
                unique_rooms = {re.sub(r"\s+", " ", x).strip().upper() for x in rooms}
                if len(unique_rooms) == 1:
                    hall = next(iter(unique_rooms))
            lines = [x.strip() for x in text.splitlines() if x.strip()]
            idx = next((i for i, line in enumerate(lines) if target in re.sub(r"\s+", "", line)), -1)
            window = " | ".join(lines[max(0, idx-8):min(len(lines), idx+9)]) if idx >= 0 else text[:1600]
            box = _find_seat_from_words(page, target) if target_words else None
            labelled = SEAT_RE.search(window)
            # Label-based seat values are retained only for conventional hall-list documents,
            # never used to interpret arbitrary seating-chart fragments.
            seat = None
            if labelled and ("SEAT" in labelled.group(0).upper() or "BENCH" in labelled.group(0).upper()):
                value = labelled.group(1).strip()
                if re.fullmatch(r"(?:[A-Z]-?)?\d{1,3}", value, re.I):
                    seat = value
            if box:
                seat = box["seat_number"]
            matches.append({
                "register_number": target, "page": pi+1, "hall_number": hall,
                "seat_number": seat or "UNKNOWN", "seat_warning": None if seat else
                "No unique numeric seat box was found immediately left of the register box",
                "context": window[:1600],
                "seat_rect": box["seat_rect"] if box else None,
                "register_rect": box["register_rect"] if box else None,
                "extraction_confidence": "high" if hall and seat else ("partial" if hall or seat else "register-only")
            })
    if not matches:
        return None
    if len(matches) > 1:
        first = matches[0].copy()
        first.update({"seat_number": "UNKNOWN",
                      "seat_warning": f"Register number occurs on {len(matches)} pages; page assignment is ambiguous",
                      "page": None, "hall_number": None, "seat_rect": None, "register_rect": None,
                      "extraction_confidence": "ambiguous"})
        return first
    return matches[0]

def search_register_in_pdf(pdf_path: Path, register_number: str) -> list[dict[str, Any]]:
    result = extract_student_allotment(pdf_path, register_number)
    return [result] if result else []


def extract_all_pdf_allotments(pdf_path: Path, source_url: str = "") -> list[dict[str, Any]]:
    """
    Extract all student allotment records from either a Hall-Allotment PDF
    or a Room-Wise Seating-Allotment PDF.
    Returns list of dicts: register_number, exam_date, session, hall_number, seat_number,
    subject_code, subject_name, page, source_url.
    """
    meta = extract_pdf_metadata(pdf_path)
    doc_type = meta.get("document_type", "unknown")
    if doc_type == "unknown" and not meta.get("exam_date"):
        return []

    default_date = meta.get("exam_date") or ""
    default_session = meta.get("session") or ""

    records = []
    hall_clean_re = re.compile(
        r"\b(MB\s+(?:I{1,3}|IV|V)\s+[A-Z]?\s*\d{2,4}[A-Z]?|LH\s*[-]?\s*\d+|LAB\s*[-]?\s*\d+)", re.I
    )
    subj_re = re.compile(r"\[([A-Z0-9]+)\]\s*([^0-9\n\r]+)", re.I)
    date_re = re.compile(r"DATE\s+OF\s+EXAM(?:INATION)?\s*[:=-]?\s*(\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})", re.I)
    sess_re = re.compile(r"SESSION\s*[:=-]?\s*(FN|AN)", re.I)
    reg_clean_re = re.compile(r"(?<!\d)\d{9,15}(?!\d)")

    with fitz.open(pdf_path) as doc:
        for pi, page in enumerate(doc):
            text = page.get_text("text", sort=True)
            p_date = default_date
            p_sess = default_session

            d_m = date_re.search(text)
            if d_m:
                parts = re.split(r"[-/.]", d_m.group(1))
                if len(parts) == 3:
                    d, m, y = map(int, parts)
                    if y < 100: y += 2000 if y < 70 else 1900
                    p_date = f"{y:04d}-{m:02d}-{d:02d}"

            s_m = sess_re.search(text)
            if s_m:
                p_sess = s_m.group(1).upper()

            page_hall = _page_hall_number(text)
            tables = page.find_tables()

            if doc_type == "department-wise" or "LIST OF STUDENTS REGISTERED" in text.upper():
                # Hall Allotment (Department / Programme list)
                curr_subj_code = ""
                curr_subj_name = ""
                extracted_before = len(records)
                for t in tables.tables:
                    df = t.extract()
                    if not df:
                        continue
                    for row in df:
                        row_str = " ".join(str(c) for c in row if c)
                        sm = subj_re.search(row_str)
                        if sm:
                            curr_subj_code = sm.group(1).strip()
                            curr_subj_name = sm.group(2).strip()
                        hm = hall_clean_re.search(row_str)
                        hall = hm.group(1).strip() if hm else page_hall
                        regs = reg_clean_re.findall(row_str)
                        for reg in regs:
                            records.append({
                                "register_number": reg,
                                "exam_date": p_date,
                                "session": p_sess,
                                "hall_number": hall or "Check Hall",
                                "seat_number": "Check Hall",
                                "subject_code": curr_subj_code,
                                "subject_name": curr_subj_name,
                                "page": pi + 1,
                                "confidence": "high" if hall else "partial",
                                "source_url": source_url,
                            })
                # Fallback to direct text stream parsing if no vector tables were detected on this page
                if len(records) == extracted_before:
                    curr_hall = page_hall
                    for line in text.splitlines():
                        line = line.strip()
                        if not line:
                            continue
                        sm = subj_re.search(line)
                        if sm:
                            curr_subj_code = sm.group(1).strip()
                            curr_subj_name = sm.group(2).strip()
                        hm = hall_clean_re.search(line)
                        if hm:
                            curr_hall = hm.group(1).strip()
                        regs = reg_clean_re.findall(line)
                        for reg in regs:
                            records.append({
                                "register_number": reg,
                                "exam_date": p_date,
                                "session": p_sess,
                                "hall_number": curr_hall or "Check Hall",
                                "seat_number": "Check Hall",
                                "subject_code": curr_subj_code,
                                "subject_name": curr_subj_name,
                                "page": pi + 1,
                                "confidence": "high" if curr_hall else "partial",
                                "source_url": source_url,
                            })
            else:
                # Seating Allotment (Room-wise seating chart)
                safe_stem = re.sub(r'[^a-zA-Z0-9_.-]', '_', pdf_path.stem)
                img_name = f"{safe_stem}_page_{pi+1}.png"
                img_rel = f"evidence/{img_name}"
                rendered_pix = None

                from vsb_watch.config import ROOT_DIR
                for tdir in (ROOT_DIR / 'evidence', ROOT_DIR / 'docs/evidence', ROOT_DIR / 'portal/evidence'):
                    tdir.mkdir(parents=True, exist_ok=True)
                    target_file = tdir / img_name
                    if not target_file.exists():
                        if rendered_pix is None:
                            rendered_pix = page.get_pixmap(matrix=fitz.Matrix(1.4, 1.4), alpha=False)
                        rendered_pix.save(target_file)

                seat_map = {}
                subject_map = {}
                for t in tables.tables:
                    df = t.extract()
                    if not df:
                        continue
                    if len(df[0]) == 2:
                        for r in df:
                            s, reg = r[0], r[1]
                            if (s and reg and re.fullmatch(r"\d{1,3}", str(s).strip())
                                    and re.fullmatch(r"\d{9,15}", str(reg).strip())):
                                seat_map[str(reg).strip()] = str(s).strip()
                    if len(df[0]) >= 3 and any("CODE" in str(c) for c in df[0]):
                        for r in df[1:]:
                            if len(r) >= 4 and r[0] and r[1]:
                                code = str(r[0]).strip()
                                title = str(r[1]).strip()
                                reg_list_str = str(r[3])
                                for reg in reg_clean_re.findall(reg_list_str):
                                    subject_map[reg] = (code, title)

                # Fallback to word-box geometry for any unmapped register numbers on the page
                page_regs = set(reg_clean_re.findall(text))
                for reg in page_regs:
                    if reg not in seat_map:
                        box = _find_seat_from_words(page, reg)
                        if box:
                            seat_map[reg] = box["seat_number"]

                for reg, seat in seat_map.items():
                    sub_code, sub_title = subject_map.get(reg, ("", ""))
                    records.append({
                        "register_number": reg,
                        "exam_date": p_date,
                        "session": p_sess,
                        "hall_number": page_hall or "Check Hall",
                        "seat_number": seat,
                        "subject_code": sub_code,
                        "subject_name": sub_title,
                        "page": pi + 1,
                        "confidence": "high" if page_hall and seat else "partial",
                        "source_url": source_url,
                        "seating_image": img_rel,
                    })

    # Deduplicate within same PDF run
    unique_records = {}
    for r in records:
        key = (r["register_number"], r["exam_date"], r["session"], r.get("subject_code", ""))
        if key not in unique_records:
            unique_records[key] = r
        else:
            # Merge seat or subject if previously missing
            existing = unique_records[key]
            if existing.get("seat_number") in ("Check Hall", "UNKNOWN", "") and r.get("seat_number") not in ("Check Hall", "UNKNOWN", ""):
                existing["seat_number"] = r["seat_number"]
            if not existing.get("subject_name") and r.get("subject_name"):
                existing["subject_name"] = r["subject_name"]
            if not existing.get("subject_code") and r.get("subject_code"):
                existing["subject_code"] = r["subject_code"]
            if not existing.get("seating_image") and r.get("seating_image"):
                existing["seating_image"] = r["seating_image"]
    return list(unique_records.values())

