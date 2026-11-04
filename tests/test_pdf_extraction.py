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

def test_vsb_seating_chart_extracts_seat_from_left_cell(tmp_path: Path):
    path = tmp_path / '05.11.26-SEATING-FN.pdf'
    doc = fitz.open(); page = doc.new_page()
    page.insert_text((50, 50), 'V.S.B. ENGINEERING COLLEGE')
    page.insert_text((50, 80), 'DATE OF EXAMINATION: 05-11-2026 SESSION : FN')
    page.insert_text((50, 120), 'EXAM HALL : MB III 101')
    page.draw_rect(fitz.Rect(50, 150, 80, 180)); page.draw_rect(fitz.Rect(80, 150, 220, 180))
    page.insert_text((60, 170), '5'); page.insert_text((90, 170), '922524103002')
    doc.save(path); doc.close()
    result = extract_student_allotment(path, '922524103002')
    assert result is not None
    assert result['seat_number'] == '5'
    assert result['hall_number'] == 'MB III 101'


def test_vsb_hall_list_extracts_room_heading(tmp_path: Path):
    path = tmp_path / '05.11.26-HALL-FN.pdf'
    doc = fitz.open(); page = doc.new_page()
    page.insert_text((50, 50), 'DATE OF EXAMINATION: 05-11-2026 SESSION : FN')
    page.insert_text((50, 100), '922524103001, 922524103002, 922524103003')
    page.insert_text((400, 100), 'MB III A204')
    doc.save(path); doc.close()
    result = extract_student_allotment(path, '922524103002')
    assert result is not None
    assert result['hall_number'] == 'MB III A204'
