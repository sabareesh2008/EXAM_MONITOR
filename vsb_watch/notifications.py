from __future__ import annotations
import smtplib
from email.message import EmailMessage
from pathlib import Path
from vsb_watch.config import settings
from vsb_watch.database import Database

def send_allotment_email(db: Database, event_key: str, allotment: dict, pdf_path: Path, evidence_path: Path | None = None) -> bool:
    recipient=settings.notification_email
    if not (recipient and settings.smtp_user and settings.smtp_password): return False
    hall=allotment.get('hall_number') or 'Not explicitly identified in PDF'
    seat=allotment.get('seat_number') or 'Not explicitly identified in PDF'
    subject=f"VSB Exam Allotment – {allotment.get('exam_date') or 'Date in PDF'} {allotment.get('session') or ''}"
    body=(f"Your register number {allotment['register_number']} was found in a VSB allotment PDF.\n\n"
      f"Exam date: {allotment.get('exam_date') or 'Please verify in attached PDF'}\nSession: {allotment.get('session') or 'Please verify in attached PDF'}\n"
      f"Hall: {hall}\nSeat: {seat}\nPDF page: {allotment.get('page')}\n"
      f"Extraction: {allotment.get('extraction_confidence')}\n\nPlease open the attached official PDF and verify the details. A missing hall/seat value means it was not confidently extracted; it does not mean no allotment exists.")
    if not db.create_notification(event_key,recipient,subject,'pending','Email queued for delivery'): return False
    msg=EmailMessage(); msg['Subject']=subject; msg['From']=settings.smtp_user; msg['To']=recipient; msg.set_content(body)
    for path,ctype in [(pdf_path,'application/pdf'),(evidence_path,'image/png') if evidence_path else (None,None)]:
        if path and path.exists():
            maintype,subtype=ctype.split('/'); msg.add_attachment(path.read_bytes(),maintype=maintype,subtype=subtype,filename=path.name)
    try:
        with smtplib.SMTP(settings.smtp_host,settings.smtp_port,timeout=30) as server:
            server.starttls(); server.login(settings.smtp_user,settings.smtp_password); server.send_message(msg)
        db.update_notification(event_key,'sent','SMTP accepted the message'); return True
    except Exception as exc:
        db.update_notification(event_key,'error',str(exc)); raise

def send_test_email() -> None:
    if not (settings.notification_email and settings.smtp_user and settings.smtp_password):
        raise RuntimeError('Set NOTIFICATION_EMAIL, SMTP_USER and SMTP_PASSWORD in .env first')
    msg=EmailMessage(); msg['Subject']='VSB Exam Watch – email configuration test'; msg['From']=settings.smtp_user; msg['To']=settings.notification_email
    msg.set_content('Your VSB Exam Watch email configuration is working. This is a test message; no allotment has been detected.')
    with smtplib.SMTP(settings.smtp_host,settings.smtp_port,timeout=30) as server:
        server.starttls(); server.login(settings.smtp_user,settings.smtp_password); server.send_message(msg)
