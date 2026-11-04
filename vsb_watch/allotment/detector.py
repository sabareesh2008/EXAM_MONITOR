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

def is_allotment_filename(filename: str) -> bool:
    normalized = filename.lower().replace("_", " ").replace("-", " ")
    if "internship" in normalized or "project" in normalized or "calendar" in normalized:
        return False
    words = ("hall", "seating", "allotment", "allocation")
    return any(w in normalized for w in words)
