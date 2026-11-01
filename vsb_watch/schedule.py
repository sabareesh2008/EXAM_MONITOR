from __future__ import annotations
from dataclasses import dataclass
from datetime import date, time

@dataclass(frozen=True)
class ExamDay:
    exam_date: date
    sessions: tuple[str, ...] = ("FN", "AN")

SESSION_WINDOWS = {
    "FN": (time(9, 30), time(12, 30)),
    "AN": (time(13, 30), time(16, 30)),
}
EXAM_DAYS = tuple(ExamDay(date(2026, 11, d)) for d in (6, 11, 14, 17, 20, 24))

def is_scheduled_exam(exam_date, session):
    if isinstance(exam_date, str):
        try:
            exam_date = date.fromisoformat(exam_date)
        except ValueError:
            return False
    if not isinstance(exam_date, date) or not session:
        return False
    session = session.strip().upper()
    return any(x.exam_date == exam_date and session in x.sessions for x in EXAM_DAYS)

def schedule_as_dict():
    return [{"date": x.exam_date.isoformat(), "sessions": [
        {"name": s, "start": SESSION_WINDOWS[s][0].strftime("%H:%M"),
         "end": SESSION_WINDOWS[s][1].strftime("%H:%M")} for s in x.sessions]}
        for x in EXAM_DAYS]
