from pathlib import Path
import fitz
from vsb_watch.allotment.pdf_parser import extract_pdf_metadata, extract_student_allotment

def test_extract_explicit_hall_and_seat(tmp_path: Path):
    path=tmp_path/'sample.pdf'
    doc=fitz.open(); page=doc.new_page()
    page.insert_text((50,50),'V.S.B. ENGINEERING COLLEGE')
    page.insert_text((50,80),'DATE OF EXAMINATION: 07-05-2026 SESSION: AN')
    page.insert_text((50,110),'Register Number: 922522106123')
    page.insert_text((50,140),'Hall Number: MB II 107')
    page.insert_text((50,170),'Seat Number: A-12')
    doc.save(path); doc.close()
    meta=extract_pdf_metadata(path)
    assert meta['exam_date']=='2026-05-07'
    assert meta['session']=='AN'
    result=extract_student_allotment(path,'922522106123')
    assert result and result['hall_number']=='MB II 107'
    assert result['seat_number']=='A-12'
