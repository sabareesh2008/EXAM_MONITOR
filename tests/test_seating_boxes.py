from pathlib import Path
import fitz
import pytest
from vsb_watch.allotment.pdf_parser import extract_student_allotment


REG = "922524103002"


def make_chart(path: Path, *, seat="27", include_left=True, duplicate=False):
    doc = fitz.open()
    count = 2 if duplicate else 1
    for _ in range(count):
        page = doc.new_page()
        page.insert_text((50, 40), "DATE OF EXAMINATION: 05-11-2026 SESSION : FN")
        page.insert_text((50, 65), "EXAM HALL : MB III A204")
        if include_left:
            page.draw_rect(fitz.Rect(50, 100, 85, 135))
            if seat is not None:
                page.insert_text((62, 123), seat, fontsize=11)
        page.draw_rect(fitz.Rect(85, 100, 230, 135))
        page.insert_text((95, 123), REG, fontsize=11)
    doc.save(path)
    doc.close()


def test_extracts_seat_27_from_adjacent_box(tmp_path):
    p = tmp_path / "seating.pdf"
    make_chart(p)
    result = extract_student_allotment(p, REG)
    assert result["seat_number"] == "27"
    assert result["page"] == 1
    assert result["hall_number"] == "MB III A204"
    assert result["seat_rect"] and result["register_rect"]


def test_ing_fragment_is_not_a_seat(tmp_path):
    p = tmp_path / "seating.pdf"
    make_chart(p, seat=None)
    # Add a misleading label fragment in the same text area.
    with fitz.open(p) as doc:
        doc[0].insert_text((50, 160), "SEAT ING")
        doc.saveIncr()
    result = extract_student_allotment(p, REG)
    assert result["seat_number"] == "UNKNOWN"


def test_register_not_found(tmp_path):
    p = tmp_path / "seating.pdf"
    make_chart(p)
    assert extract_student_allotment(p, "922524103999") is None


def test_duplicate_register_on_multiple_pages_is_ambiguous(tmp_path):
    p = tmp_path / "seating.pdf"
    make_chart(p, duplicate=True)
    result = extract_student_allotment(p, REG)
    assert result["seat_number"] == "UNKNOWN"
    assert result["page"] is None
    assert "2 pages" in result["seat_warning"]


def test_missing_adjacent_box_is_unknown(tmp_path):
    p = tmp_path / "seating.pdf"
    make_chart(p, include_left=False)
    result = extract_student_allotment(p, REG)
    assert result["seat_number"] == "UNKNOWN"
    assert result["seat_rect"] is None


def test_hall_extraction_still_works(tmp_path):
    p = tmp_path / "hall.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "DATE OF EXAMINATION: 05-11-2026 SESSION : FN")
    page.insert_text((50, 100), f"{REG}, 922524103003")
    page.insert_text((400, 100), "MB III A204")
    doc.save(p); doc.close()
    result = extract_student_allotment(p, REG)
    assert result["hall_number"] == "MB III A204"


def test_test_email_is_blocked_for_unknown_seat(monkeypatch):
    from vsb_watch.allotment import manual_test
    called = []
    monkeypatch.setattr(manual_test.smtplib, "SMTP", lambda *a, **k: called.append(True))
    with pytest.raises(RuntimeError, match="Seat validation failed"):
        manual_test._send_test_result_email({
            "seat_number": "UNKNOWN", "seating_page": 21,
            "hall_screenshot": "hall.png", "seating_screenshot": "seat.png"
        })
    assert not called


def test_monitoring_email_is_blocked_for_unknown_seat():
    from vsb_watch.notifications import send_allotment_email
    class NeverCalledDB:
        def create_notification(self, *args, **kwargs):
            raise AssertionError("database/email flow must not start for UNKNOWN seat")
    assert send_allotment_email(
        NeverCalledDB(), "event", {"register_number": REG, "seat_number": "UNKNOWN"},
        Path("missing.pdf")
    ) is False


def test_ambiguous_adjacent_cells_are_unknown(tmp_path):
    p = tmp_path / "seating.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 40), "DATE OF EXAMINATION: 05-11-2026 SESSION : FN")
    page.insert_text((50, 65), "EXAM HALL : MB III A204")
    page.draw_rect(fitz.Rect(50, 100, 100, 140))
    page.insert_text((62, 125), "27")
    page.draw_rect(fitz.Rect(60, 100, 100, 140))
    page.insert_text((70, 125), "28")
    page.draw_rect(fitz.Rect(100, 100, 250, 140))
    page.insert_text((110, 125), REG)
    doc.save(p); doc.close()
    result = extract_student_allotment(p, REG)
    assert result["seat_number"] == "UNKNOWN"
