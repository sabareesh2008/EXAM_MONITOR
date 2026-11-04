from __future__ import annotations

import re
import smtplib
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urlparse

import fitz
import requests

from vsb_watch.allotment.pdf_parser import extract_student_allotment, extract_pdf_metadata
from vsb_watch.config import settings


def _download_pdf(url: str, destination: Path) -> Path:
    parsed = urlparse(url)
    if parsed.scheme != 'https' or parsed.hostname != 'vsbec.edu.in':
        raise ValueError('Only HTTPS PDFs hosted on vsbec.edu.in are allowed.')
    response = requests.get(url, timeout=settings.request_timeout_seconds,
                            headers={'User-Agent': settings.user_agent})
    response.raise_for_status()
    if len(response.content) > 40 * 1024 * 1024:
        raise ValueError('PDF exceeds 40 MB safety limit.')
    if not response.content.startswith(b'%PDF'):
        raise ValueError(f'The URL did not return a PDF: {url}')
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(response.content)
    return destination


def _highlight_evidence(pdf_path: Path, register_number: str, suffix: str,
                        allotment: dict | None = None) -> Path | None:
    settings.evidence_dir.mkdir(parents=True, exist_ok=True)
    page_number = (allotment or {}).get("page")
    with fitz.open(pdf_path) as doc:
        indices = [page_number-1] if isinstance(page_number, int) and 1 <= page_number <= len(doc) else range(len(doc))
        for index in indices:
            page = doc[index]
            matches = page.search_for(register_number)
            if not matches:
                continue
            for rect in matches:
                page.draw_rect(rect + (-4, -3, 4, 3), color=(1, 0, 0), width=2)
            hall_text = (allotment or {}).get('hall_number')
            if suffix == 'hall' and hall_text:
                for rect in page.search_for(hall_text):
                    page.draw_rect(rect + (-4, -3, 4, 3), color=(0, 0.2, 1), width=2)
            if allotment and allotment.get("register_rect"):
                page.draw_rect(fitz.Rect(allotment["register_rect"]), color=(1, 0, 0), width=2.5)
            if allotment and allotment.get("seat_rect"):
                page.draw_rect(fitz.Rect(allotment["seat_rect"]), color=(0, 0.65, 0), width=3)
                page.insert_text((fitz.Rect(allotment["seat_rect"]).x0,
                                  max(12, fitz.Rect(allotment["seat_rect"]).y0-5)),
                                 f"SEAT {allotment.get('seat_number','UNKNOWN')}",
                                 fontsize=8, color=(0, 0.5, 0))
            page.insert_text((24, 24), f"{suffix.upper()} ALLOTMENT | PDF PAGE {index+1}",
                             fontsize=10, color=(0, 0, 1))
            pix = page.get_pixmap(matrix=fitz.Matrix(1.8, 1.8), alpha=False)
            output = settings.evidence_dir / f"{pdf_path.stem}_{suffix}_page_{index+1}.png"
            pix.save(output)
            return output
    return None


def run_manual_test(register_number: str, exam_date: str, session: str,
                    hall_url: str, seating_url: str, send_email: bool = False) -> dict:
    register_number = re.sub(r'\s+', '', register_number)
    if not register_number.isdigit():
        raise ValueError('Register number must contain digits only.')
    datetime.strptime(exam_date, '%Y-%m-%d')
    session = session.upper()
    if session not in {'FN', 'AN'}:
        raise ValueError('Session must be FN or AN.')

    tag = f'{exam_date}_{session}_{register_number}'
    hall_pdf = _download_pdf(hall_url, settings.download_dir / f'test_{tag}_HALL.pdf')
    seating_pdf = _download_pdf(seating_url, settings.download_dir / f'test_{tag}_SEATING.pdf')
    for label, path in (('hall', hall_pdf), ('seating', seating_pdf)):
        meta = extract_pdf_metadata(path)
        if meta.get('exam_date') != exam_date or meta.get('session') != session:
            raise RuntimeError(f'{label.title()} PDF date/session mismatch: found {meta.get("exam_date")} {meta.get("session")}; expected {exam_date} {session}.')
    hall = extract_student_allotment(hall_pdf, register_number)
    seating = extract_student_allotment(seating_pdf, register_number)
    if not hall:
        raise RuntimeError(f'Register number was not found in the hall-allotment PDF: {hall_pdf.name}')
    if not seating:
        raise RuntimeError(f'Register number was not found in the seating-allotment PDF: {seating_pdf.name}')

    hall_no = hall.get('hall_number') or seating.get('hall_number')
    seat_no = seating.get('seat_number', 'UNKNOWN')
    if not hall_no or not re.fullmatch(r'\d{1,3}', str(seat_no)) or not (1 <= int(seat_no) <= 200):
        raise RuntimeError(
            'The register number was found, but the hall/seat could not both be extracted confidently. '
            f'Hall candidate={hall_no!r}; seat candidate={seat_no!r}. No email was sent.'
        )

    hall_evidence = _highlight_evidence(hall_pdf, register_number, 'hall', hall)
    seating_evidence = _highlight_evidence(seating_pdf, register_number, 'seating', seating)
    if not hall_evidence or not seating_evidence:
        raise RuntimeError('Could not create both page-specific evidence screenshots; no email was sent.')
    result = {
        'register_number': register_number, 'exam_date': exam_date, 'session': session,
        'hall_number': hall_no, 'seat_number': seat_no,
        'hall_page': hall.get('page'), 'seating_page': seating.get('page'),
        'hall_pdf': hall_pdf, 'seating_pdf': seating_pdf,
        'hall_screenshot': hall_evidence, 'seating_screenshot': seating_evidence,
    }
    if send_email:
        _send_test_result_email(result)
    return result


def _send_test_result_email(result: dict) -> None:
    if (not re.fullmatch(r'\d{1,3}', str(result.get('seat_number', ''))) or
            not 1 <= int(result['seat_number']) <= 200 or
            not isinstance(result.get('seating_page'), int) or
            not result.get('hall_screenshot') or not result.get('seating_screenshot')):
        raise RuntimeError('Seat validation failed; test email blocked.')
    if not (settings.notification_email and settings.smtp_user and settings.smtp_password):
        raise RuntimeError('Configure NOTIFICATION_EMAIL, SMTP_USER and SMTP_PASSWORD in .env first.')
    subject = (f"VSB Exam Watch TEST – {result['exam_date']} {result['session']} – "
               f"{result['register_number']}")
    body = (
        'This is a one-time TEST report from VSB Exam Watch.\n\n'
        f"Register number: {result['register_number']}\n"
        f"Exam date: {result['exam_date']}\nSession: {result['session']}\n"
        f"Hall number: {result['hall_number']}\nSeat number: {result['seat_number']}\n"
        f"Hall PDF page: {result['hall_page']}\nSeating PDF page: {result['seating_page']}\n\n"
        'Both official PDFs and the matching-page screenshots are attached. '
        'Please compare these values with the official PDFs. This test does not alter your personal monitoring register number.'
    )
    required_attachments = [result.get('hall_pdf'), result.get('seating_pdf'),
                            result.get('hall_screenshot'), result.get('seating_screenshot')]
    if any(not path or not Path(path).is_file() for path in required_attachments):
        raise RuntimeError('All four evidence attachments must exist; test email blocked.')
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = settings.smtp_user
    msg['To'] = settings.notification_email
    msg.set_content(body)
    attachments = [
        (result['hall_pdf'], 'application', 'pdf'),
        (result['seating_pdf'], 'application', 'pdf'),
        (result['hall_screenshot'], 'image', 'png'),
        (result['seating_screenshot'], 'image', 'png'),
    ]
    for path, maintype, subtype in attachments:
        if path and Path(path).exists():
            msg.add_attachment(Path(path).read_bytes(), maintype=maintype,
                               subtype=subtype, filename=Path(path).name)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as server:
        server.starttls()
        server.login(settings.smtp_user, settings.smtp_password)
        server.send_message(msg)
