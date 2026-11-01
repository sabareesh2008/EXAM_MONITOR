from datetime import date
from vsb_watch.schedule import EXAM_DAYS, SESSION_WINDOWS, is_scheduled_exam

def test_six_dates():
    assert [x.exam_date for x in EXAM_DAYS] == [date(2026, 11, d) for d in (6, 11, 14, 17, 20, 24)]

def test_session_windows():
    assert SESSION_WINDOWS['FN'][0].strftime('%H:%M') == '09:30'
    assert SESSION_WINDOWS['FN'][1].strftime('%H:%M') == '12:30'
    assert SESSION_WINDOWS['AN'][0].strftime('%H:%M') == '13:30'
    assert SESSION_WINDOWS['AN'][1].strftime('%H:%M') == '16:30'

def test_schedule_filter():
    assert is_scheduled_exam(date(2026, 11, 6), 'FN')
    assert is_scheduled_exam('2026-11-24', 'AN')
    assert not is_scheduled_exam(date(2026, 11, 7), 'FN')
    assert not is_scheduled_exam('2026-11-06', 'PM')
    assert not is_scheduled_exam(None, 'FN')
