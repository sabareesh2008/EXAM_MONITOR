from pathlib import Path
import fitz
import pytest
from vsb_watch.database import Database
from vsb_watch.allotment.pdf_parser import extract_all_pdf_allotments
from vsb_watch.allotment.detector import is_allotment_filename
from vsb_watch.supabase_client import SupabaseClient


def test_is_allotment_filename_detection():
    assert is_allotment_filename("30.05.25-FN_HALL-ALLOTMENT.pdf")
    assert is_allotment_filename("05.11.26-SEATING-FN.pdf")
    assert is_allotment_filename("test_2026-11-05_FN_922524103002_HALL.pdf")
    assert is_allotment_filename("test_2026-11-05_FN_922524103002_SEATING.pdf")
    assert not is_allotment_filename("internship-proof-and-project-work.pdf")
    assert not is_allotment_filename("academic-calendar.pdf")


def test_extract_all_pdf_allotments_synthetic_hall(tmp_path: Path):
    pdf_path = tmp_path / "15.05.26-FN_HALL-ALLOTMENT.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 40), "V.S.B. ENGINEERING COLLEGE")
    page.insert_text((50, 60), "DATE OF EXAMINATION: 15-05-2026 SESSION : FN")
    page.insert_text((50, 80), "Programme | List of students registered | Hall Number | Total")
    page.insert_text((50, 100), "[CS101] PYTHON PROGRAMMING")
    page.insert_text((50, 120), "922524101001, 922524101002, 922524101003")
    page.insert_text((350, 120), "MB II 105")
    doc.save(pdf_path)
    doc.close()

    records = extract_all_pdf_allotments(pdf_path)
    assert len(records) == 3
    regs = [r["register_number"] for r in records]
    assert "922524101001" in regs
    assert "922524101002" in regs
    assert "922524101003" in regs
    assert all(r["exam_date"] == "2026-05-15" for r in records)
    assert all(r["session"] == "FN" for r in records)
    assert all(r["hall_number"] == "MB II 105" for r in records)


def test_database_bulk_ingest_and_student_search(tmp_path: Path):
    db = Database(tmp_path / "test_v23.sqlite3")
    db.initialize()

    # Simulate regular and arrear records across FN and AN on same date
    sample_records = [
        # Regular FN exam
        {
            "register_number": "922521106001",
            "exam_date": "2026-11-10",
            "session": "FN",
            "hall_number": "MB III 201",
            "seat_number": "12",
            "subject_code": "EC8001",
            "subject_name": "VLSI DESIGN",
            "page": 1,
            "source_url": "https://vsbec.edu.in/fn.pdf"
        },
        # Arrear AN exam on same date
        {
            "register_number": "922521106001",
            "exam_date": "2026-11-10",
            "session": "AN",
            "hall_number": "MB III 202",
            "seat_number": "5",
            "subject_code": "MA8002",
            "subject_name": "LINEAR ALGEBRA",
            "page": 2,
            "source_url": "https://vsbec.edu.in/an.pdf"
        },
        # Another student
        {
            "register_number": "922521106002",
            "exam_date": "2026-11-10",
            "session": "FN",
            "hall_number": "MB III 201",
            "seat_number": "14",
            "subject_code": "EC8001",
            "subject_name": "VLSI DESIGN",
            "page": 1,
            "source_url": "https://vsbec.edu.in/fn.pdf"
        }
    ]

    inserted = db.save_bulk_allotments(None, sample_records)
    assert inserted == 3

    # Test student with FN + AN on same day (current / upcoming)
    allotted = db.find_allotments_by_register("922521106001", current_only=True, reference_date="2026-11-10")
    assert len(allotted) == 2
    assert allotted[0]["session"] == "FN"
    assert allotted[0]["seat_number"] == "12"
    assert allotted[0]["subject_code"] == "EC8001"
    assert allotted[1]["session"] == "AN"
    assert allotted[1]["seat_number"] == "5"
    assert allotted[1]["subject_code"] == "MA8002"

    # Test filtering out past exams: simulate past exam vs current/tomorrow exam
    db.save_bulk_allotments(None, [
        {
            "register_number": "922521106099",
            "exam_date": "2025-05-10",
            "session": "FN",
            "hall_number": "MB I 101",
            "seat_number": "1",
            "subject_code": "OLD101",
            "subject_name": "OLD EXAM"
        },
        {
            "register_number": "922521106099",
            "exam_date": "2026-11-05",
            "session": "FN",
            "hall_number": "MB III A204",
            "seat_number": "27",
            "subject_code": "23CEE037",
            "subject_name": "CURRENT EXAM"
        }
    ])

    # With current_only=True on 2026-11-04 (today checking tomorrow), only 2026-11-05 appears
    current_exams = db.find_allotments_by_register("922521106099", current_only=True, reference_date="2026-11-04")
    assert len(current_exams) == 1
    assert current_exams[0]["exam_date"] == "2026-11-05"
    assert current_exams[0]["hall_number"] == "MB III A204"
    assert current_exams[0]["seat_number"] == "27"

    # With current_only=False, both appear
    all_exams = db.find_allotments_by_register("922521106099", current_only=False)
    assert len(all_exams) == 2

    # Test student with no allotment
    unallotted = db.find_allotments_by_register("999999999999")
    assert unallotted == []


def test_supabase_client_unconfigured_graceful():
    client = SupabaseClient(url="", key="")
    assert not client.is_configured()
    res = client.upsert_allotments([{"register_number": "922521106001"}])
    assert res["upserted"] == 0
    search_res = client.search_allotments("922521106001")
    assert search_res == []
