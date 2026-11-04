from __future__ import annotations

import logging
import re
from typing import Any
import requests

from vsb_watch.config import settings

logger = logging.getLogger(__name__)


class SupabaseClient:
    def __init__(self, url: str = "", key: str = "", table: str = ""):
        self.url = (url or settings.supabase_url).rstrip("/")
        self.key = key or settings.supabase_key
        self.table = table or settings.supabase_table or "allotments"

    def is_configured(self) -> bool:
        return bool(self.url and self.key)

    def _headers(self) -> dict[str, str]:
        return {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }

    def upsert_allotments(self, records: list[dict[str, Any]], batch_size: int = 200) -> dict[str, int]:
        """
        Upsert extracted exam allotments into Supabase using REST API.
        Deduplicates on (register_number, exam_date, session, subject_code).
        """
        if not self.is_configured():
            logger.debug("Supabase is not configured; skipping remote upsert.")
            return {"upserted": 0, "batches": 0, "errors": 0}

        endpoint = f"{self.url}/rest/v1/{self.table}?on_conflict=register_number,exam_date,session,subject_code"
        headers = self._headers()
        headers["Prefer"] = "resolution=merge-duplicates,return=minimal"

        total_upserted = 0
        errors = 0
        batches = 0

        # Clean payload fields
        cleaned = []
        for r in records:
            reg = re.sub(r"\s+", "", str(r.get("register_number", ""))).strip()
            if not reg:
                continue
            item = {
                "register_number": reg,
                "exam_date": r.get("exam_date"),
                "session": r.get("session"),
                "hall_number": r.get("hall_number"),
                "seat_number": r.get("seat_number", "Check Hall"),
                "subject_code": r.get("subject_code", ""),
                "subject_name": r.get("subject_name", ""),
                "page_number": r.get("page") or r.get("page_number"),
                "source_pdf_url": r.get("source_url") or r.get("source_pdf_url", ""),
            }
            cleaned.append(item)

        for i in range(0, len(cleaned), batch_size):
            chunk = cleaned[i : i + batch_size]
            batches += 1
            try:
                resp = requests.post(
                    endpoint,
                    json=chunk,
                    headers=headers,
                    timeout=settings.request_timeout_seconds,
                )
                if resp.status_code in (200, 201, 204):
                    total_upserted += len(chunk)
                else:
                    errors += 1
                    logger.error("Supabase upsert error (%s): %s", resp.status_code, resp.text[:400])
            except Exception as exc:
                errors += 1
                logger.exception("Supabase upsert request failed: %s", exc)

        return {"upserted": total_upserted, "batches": batches, "errors": errors}

    def search_allotments(self, register_number: str, current_only: bool = True) -> list[dict[str, Any]]:
        """
        Search for allotments for a given student register number.
        By default, returns current and upcoming published examinations (exam_date >= today).
        """
        from datetime import date
        if not self.is_configured():
            return []

        clean_reg = re.sub(r"\s+", "", str(register_number)).strip()
        if not clean_reg:
            return []

        date_filter = f"&exam_date=gte.{date.today().isoformat()}" if current_only else ""
        endpoint = f"{self.url}/rest/v1/{self.table}?register_number=eq.{clean_reg}{date_filter}&order=exam_date.asc,session.asc"
        headers = self._headers()

        try:
            resp = requests.get(
                endpoint,
                headers=headers,
                timeout=settings.request_timeout_seconds,
            )
            if resp.status_code == 200:
                return resp.json()
            logger.warning("Supabase search returned %s: %s", resp.status_code, resp.text[:200])
            return []
        except Exception as exc:
            logger.exception("Supabase search failed: %s", exc)
            return []


supabase_client = SupabaseClient()
