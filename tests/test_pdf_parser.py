from pathlib import Path
from vsb_watch.allotment.detector import is_allotment_candidate
from vsb_watch.allotment.pdf_parser import _find_scheduled_date, _find_session

def test_detects_hall_allotment():
    assert is_allotment_candidate('https://vsbec.edu.in/files/06.11.26-FN-HALL-ALLOTMENT.pdf')

def test_ignores_unrelated_internship_allotment():
    assert not is_allotment_candidate('https://vsbec.edu.in/files/internship-proof-and-project-work-allotment-2023.pdf')

def test_ignores_generic_calendar():
    assert not is_allotment_candidate('https://vsbec.edu.in/files/academic-calendar.pdf')

def test_scheduled_filename_date_and_session():
    assert _find_scheduled_date('', '06.11.26-FN-HALL-ALLOTMENT.pdf') == '2026-11-06'
    assert _find_session('', '06.11.26-FN-HALL-ALLOTMENT.pdf') == 'FN'

def test_non_target_filename_date_is_extracted_for_filtering():
    assert _find_scheduled_date('', '12.05.26-AN-HALL-ALLOTMENT.pdf') == '2026-05-12'

def test_ambiguous_unlabelled_dates_are_rejected():
    assert _find_scheduled_date('Dates: 06.11.26 and 11.11.26', 'hall-allotment.pdf') is None
