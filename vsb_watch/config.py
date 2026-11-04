from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv
ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / '.env')
def _path(name, default):
    p = Path(os.getenv(name, default)); return p if p.is_absolute() else ROOT_DIR / p
@dataclass(frozen=True)
class Settings:
    coe_url: str = os.getenv('COE_URL', 'https://vsbec.edu.in/controller-of-examination/')
    monitor_urls: tuple[str, ...] = tuple(x.strip() for x in os.getenv('MONITOR_URLS', 'https://vsbec.edu.in/controller-of-examination/,https://vsbec.edu.in/,https://coe.vsbec.edu.in/').split(',') if x.strip())
    poll_interval_minutes: int = max(5, int(os.getenv('POLL_INTERVAL_MINUTES', '5')))
    request_timeout_seconds: int = max(5, int(os.getenv('REQUEST_TIMEOUT_SECONDS', '30')))
    user_agent: str = os.getenv('USER_AGENT', 'VSBExamWatch/2.0 (personal academic notice monitor)')
    register_number: str = ''.join(c for c in os.getenv('REGISTER_NUMBER', '') if c.isdigit())
    student_name: str = os.getenv('STUDENT_NAME', '')
    department: str = os.getenv('DEPARTMENT', 'ECE')
    notification_email: str = os.getenv('NOTIFICATION_EMAIL', '')
    smtp_host: str = os.getenv('SMTP_HOST', 'smtp.gmail.com')
    smtp_port: int = int(os.getenv('SMTP_PORT', '587'))
    smtp_user: str = os.getenv('SMTP_USER', '')
    smtp_password: str = os.getenv('SMTP_PASSWORD', '')
    dashboard_host: str = os.getenv('DASHBOARD_HOST', '127.0.0.1')
    dashboard_port: int = int(os.getenv('DASHBOARD_PORT', '5000'))
    dashboard_secret: str = os.getenv('DASHBOARD_SECRET', 'change-this-secret')
    database_path: Path = _path('DATABASE_PATH', 'data/vsb_exam_watch.sqlite3')
    download_dir: Path = _path('DOWNLOAD_DIR', 'data/downloads')
    evidence_dir: Path = _path('EVIDENCE_DIR', 'data/evidence')
    log_dir: Path = _path('LOG_DIR', 'data/logs')
    supabase_url: str = os.getenv('SUPABASE_URL', '').rstrip('/')
    supabase_key: str = os.getenv('SUPABASE_KEY', '')
    supabase_table: str = os.getenv('SUPABASE_TABLE', 'allotments')
    allow_all_exam_dates: bool = os.getenv('ALLOW_ALL_EXAM_DATES', 'true').lower() in ('true', '1', 'yes')
settings = Settings()
