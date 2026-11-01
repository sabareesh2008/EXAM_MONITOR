from __future__ import annotations
from urllib.parse import urlparse, unquote

KEYWORDS = (
    "hall allotment", "hall-allotment", "hall_allotment",
    "hall seating", "hall-seating", "hall_seating",
    "seating allotment", "seating arrangement",
    "exam hall allotment", "exam-hall-allotment",
    "hall allocation", "hall-allocation",
)

def is_allotment_candidate(url: str, label: str = "") -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    raw = unquote(f"{parsed.path} {parsed.query} {label}").lower()
    normalized = raw.replace("_", " ").replace("-", " ")
    return any(k.replace("_", " ").replace("-", " ") in normalized for k in KEYWORDS)
