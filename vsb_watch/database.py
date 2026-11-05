from __future__ import annotations
import re
import sqlite3
from pathlib import Path
from typing import Any
class Database:
    def __init__(self,path:Path): self.path=path
    def connect(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        con=sqlite3.connect(self.path,timeout=30); con.row_factory=sqlite3.Row; con.execute('PRAGMA journal_mode=WAL'); return con
    def initialize(self):
        with self.connect() as c:
            c.executescript('''
            CREATE TABLE IF NOT EXISTS checks(id INTEGER PRIMARY KEY,checked_at TEXT NOT NULL,page_url TEXT,status TEXT,detail TEXT);
            CREATE TABLE IF NOT EXISTS documents(id INTEGER PRIMARY KEY,url TEXT UNIQUE,filename TEXT,sha256 TEXT,local_path TEXT,first_seen_at TEXT,last_seen_at TEXT,exam_date TEXT,session TEXT,document_type TEXT,extraction_json TEXT);
            CREATE TABLE IF NOT EXISTS allotments(id INTEGER PRIMARY KEY,document_id INTEGER,register_number TEXT,exam_date TEXT,session TEXT,hall_number TEXT,seat_number TEXT,page INTEGER,confidence TEXT,context TEXT,subject_code TEXT,subject_name TEXT,source_url TEXT,created_at TEXT,UNIQUE(document_id,register_number),FOREIGN KEY(document_id) REFERENCES documents(id));
            CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY,event_key TEXT UNIQUE,recipient TEXT,subject TEXT,status TEXT,detail TEXT,created_at TEXT);
            CREATE INDEX IF NOT EXISTS idx_allotments_reg ON allotments(register_number);
            CREATE INDEX IF NOT EXISTS idx_allotments_date ON allotments(exam_date);
            ''')
            # Safe schema migrations for existing SQLite databases
            cols = [r['name'] for r in c.execute('PRAGMA table_info(allotments)').fetchall()]
            if 'subject_code' not in cols:
                c.execute('ALTER TABLE allotments ADD COLUMN subject_code TEXT')
            if 'subject_name' not in cols:
                c.execute('ALTER TABLE allotments ADD COLUMN subject_name TEXT')
            if 'source_url' not in cols:
                c.execute('ALTER TABLE allotments ADD COLUMN source_url TEXT')
            if 'seating_image' not in cols:
                c.execute('ALTER TABLE allotments ADD COLUMN seating_image TEXT')
    def record_check(self,at,url,status,detail=''):
        with self.connect() as c: c.execute('INSERT INTO checks(checked_at,page_url,status,detail) VALUES(?,?,?,?)',(at,url,status,detail))
    def get_document(self,url):
        with self.connect() as c:
            r=c.execute('SELECT * FROM documents WHERE url=?',(url,)).fetchone(); return dict(r) if r else None
    def upsert_document(self,v):
        with self.connect() as c:
            c.execute('''INSERT INTO documents(url,filename,sha256,local_path,first_seen_at,last_seen_at,exam_date,session,document_type,extraction_json)
            VALUES(:url,:filename,:sha256,:local_path,:first_seen_at,:last_seen_at,:exam_date,:session,:document_type,:extraction_json)
            ON CONFLICT(url) DO UPDATE SET filename=excluded.filename,sha256=excluded.sha256,local_path=excluded.local_path,last_seen_at=excluded.last_seen_at,exam_date=excluded.exam_date,session=excluded.session,document_type=excluded.document_type,extraction_json=excluded.extraction_json''',v)
            return c.execute('SELECT id FROM documents WHERE url=?',(v['url'],)).fetchone()['id']
    def save_allotment(self,document_id,reg,meta):
        with self.connect() as c:
            c.execute('''INSERT INTO allotments(document_id,register_number,exam_date,session,hall_number,seat_number,page,confidence,context,subject_code,subject_name,source_url,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,datetime('now')) ON CONFLICT(document_id,register_number) DO UPDATE SET exam_date=excluded.exam_date,session=excluded.session,hall_number=excluded.hall_number,seat_number=excluded.seat_number,page=excluded.page,confidence=excluded.confidence,context=excluded.context,subject_code=COALESCE(excluded.subject_code, allotments.subject_code),subject_name=COALESCE(excluded.subject_name, allotments.subject_name),source_url=COALESCE(excluded.source_url, allotments.source_url)''',
            (document_id,reg,meta.get('exam_date'),meta.get('session'),meta.get('hall_number'),meta.get('seat_number'),meta.get('page'),meta.get('extraction_confidence'),meta.get('context'),meta.get('subject_code'),meta.get('subject_name'),meta.get('source_url')))

    def save_bulk_allotments(self, document_id: int | None, records: list[dict[str, Any]]) -> int:
        if not records:
            return 0
        inserted = 0
        with self.connect() as c:
            for rec in records:
                reg = str(rec.get('register_number', '')).strip()
                if not reg:
                    continue
                doc_id = document_id or rec.get('document_id')
                c.execute('''
                INSERT INTO allotments(document_id,register_number,exam_date,session,hall_number,seat_number,page,confidence,context,subject_code,subject_name,source_url,seating_image,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))
                ON CONFLICT(document_id,register_number) DO UPDATE SET
                    exam_date=COALESCE(excluded.exam_date, allotments.exam_date),
                    session=COALESCE(excluded.session, allotments.session),
                    hall_number=COALESCE(excluded.hall_number, allotments.hall_number),
                    seat_number=CASE WHEN excluded.seat_number NOT IN ('UNKNOWN', 'Check Hall', '', NULL) THEN excluded.seat_number ELSE allotments.seat_number END,
                    page=COALESCE(excluded.page, allotments.page),
                    confidence=COALESCE(excluded.confidence, allotments.confidence),
                    context=COALESCE(excluded.context, allotments.context),
                    subject_code=CASE WHEN excluded.subject_code NOT IN ('', NULL) THEN excluded.subject_code ELSE allotments.subject_code END,
                    subject_name=CASE WHEN excluded.subject_name NOT IN ('', NULL) THEN excluded.subject_name ELSE allotments.subject_name END,
                    source_url=COALESCE(excluded.source_url, allotments.source_url),
                    seating_image=CASE WHEN excluded.seating_image NOT IN ('', NULL) THEN excluded.seating_image ELSE allotments.seating_image END
                ''', (
                    doc_id, reg, rec.get('exam_date'), rec.get('session'),
                    rec.get('hall_number'), rec.get('seat_number', 'Check Hall'),
                    rec.get('page'), rec.get('confidence', 'batch'), rec.get('context', ''),
                    rec.get('subject_code', ''), rec.get('subject_name', ''), rec.get('source_url', ''),
                    rec.get('seating_image', '')
                ))
                inserted += 1
        return inserted

    def find_allotments_by_register(self, register_number: str, current_only: bool = True, reference_date: str | None = None) -> list[dict[str, Any]]:
        from datetime import date
        reg = re.sub(r'\s+', '', str(register_number)).strip()
        if not reg:
            return []
        ref = reference_date or date.today().isoformat()
        with self.connect() as c:
            if current_only:
                query = '''
                SELECT 
                    a.register_number,
                    a.exam_date,
                    a.session,
                    MAX(a.hall_number) as hall_number,
                    MAX(CASE WHEN a.seat_number IS NOT NULL AND a.seat_number NOT IN ('UNKNOWN', 'Check Hall', '') THEN a.seat_number ELSE NULL END) as seat_number,
                    MAX(a.subject_code) as subject_code,
                    MAX(a.subject_name) as subject_name,
                    MIN(a.page) as page,
                    MAX(a.source_url) as source_url,
                    MAX(a.seating_image) as seating_image,
                    MAX(d.filename) as filename,
                    MAX(d.url) as document_url
                FROM allotments a
                LEFT JOIN documents d ON d.id = a.document_id
                WHERE a.register_number = ? AND a.exam_date >= ?
                GROUP BY a.register_number, a.exam_date, a.session
                ORDER BY a.exam_date ASC, CASE WHEN a.session = 'FN' THEN 1 ELSE 2 END ASC
                '''
                rows = c.execute(query, (reg, ref)).fetchall()
            else:
                query = '''
                SELECT 
                    a.register_number,
                    a.exam_date,
                    a.session,
                    MAX(a.hall_number) as hall_number,
                    MAX(CASE WHEN a.seat_number IS NOT NULL AND a.seat_number NOT IN ('UNKNOWN', 'Check Hall', '') THEN a.seat_number ELSE NULL END) as seat_number,
                    MAX(a.subject_code) as subject_code,
                    MAX(a.subject_name) as subject_name,
                    MIN(a.page) as page,
                    MAX(a.source_url) as source_url,
                    MAX(a.seating_image) as seating_image,
                    MAX(d.filename) as filename,
                    MAX(d.url) as document_url
                FROM allotments a
                LEFT JOIN documents d ON d.id = a.document_id
                WHERE a.register_number = ?
                GROUP BY a.register_number, a.exam_date, a.session
                ORDER BY a.exam_date ASC, CASE WHEN a.session = 'FN' THEN 1 ELSE 2 END ASC
                '''
                rows = c.execute(query, (reg,)).fetchall()

            cleaned = []
            for r in rows:
                item = dict(r)
                if not item.get('seat_number'):
                    item['seat_number'] = 'Check Hall'
                cleaned.append(item)
            return cleaned

    def export_allotments_data(self, json_path: Path, js_path: Path | None = None, current_only: bool = True):
        import json
        from datetime import date
        json_path.parent.mkdir(parents=True, exist_ok=True)
        today = date.today().isoformat()
        with self.connect() as c:
            if current_only:
                rows = c.execute('''
                SELECT 
                    a.register_number,
                    a.exam_date,
                    a.session,
                    MAX(a.hall_number) as hall_number,
                    MAX(CASE WHEN a.seat_number IS NOT NULL AND a.seat_number NOT IN ('UNKNOWN', 'Check Hall', '') THEN a.seat_number ELSE NULL END) as seat_number,
                    MAX(a.subject_code) as subject_code,
                    MAX(a.subject_name) as subject_name,
                    MIN(a.page) as page,
                    MAX(a.source_url) as source_url,
                    MAX(a.seating_image) as seating_image
                FROM allotments a
                WHERE a.exam_date >= ?
                GROUP BY a.register_number, a.exam_date, a.session
                ORDER BY a.exam_date ASC, CASE WHEN a.session = 'FN' THEN 1 ELSE 2 END ASC
                ''', (today,)).fetchall()
            else:
                rows = c.execute('''
                SELECT 
                    a.register_number,
                    a.exam_date,
                    a.session,
                    MAX(a.hall_number) as hall_number,
                    MAX(CASE WHEN a.seat_number IS NOT NULL AND a.seat_number NOT IN ('UNKNOWN', 'Check Hall', '') THEN a.seat_number ELSE NULL END) as seat_number,
                    MAX(a.subject_code) as subject_code,
                    MAX(a.subject_name) as subject_name,
                    MIN(a.page) as page,
                    MAX(a.source_url) as source_url,
                    MAX(a.seating_image) as seating_image
                FROM allotments a
                GROUP BY a.register_number, a.exam_date, a.session
                ORDER BY a.exam_date ASC, CASE WHEN a.session = 'FN' THEN 1 ELSE 2 END ASC
                ''').fetchall()

        mapping: dict[str, list[dict]] = {}
        for r in rows:
            reg = str(r['register_number']).strip()
            if reg not in mapping:
                mapping[reg] = []
            item = dict(r)
            if not item.get('seat_number'):
                item['seat_number'] = 'Check Hall'
            mapping[reg].append(item)

        json_path.write_text(json.dumps(mapping, indent=2, ensure_ascii=False), encoding='utf-8')
        if js_path:
            js_path.parent.mkdir(parents=True, exist_ok=True)
            js_content = f"window.VSB_ALLOTMENTS = {json.dumps(mapping, ensure_ascii=False)};"
            js_path.write_text(js_content, encoding='utf-8')
        return len(mapping)
    def create_notification(self,event_key,recipient,subject,status,detail):
        with self.connect() as c:
            cur=c.execute('INSERT OR IGNORE INTO notifications(event_key,recipient,subject,status,detail,created_at) VALUES(?,?,?,?,?,datetime(\'now\'))',(event_key,recipient,subject,status,detail));
            if cur.rowcount == 1: return True
            row=c.execute("SELECT status,created_at FROM notifications WHERE event_key=?",(event_key,)).fetchone()
            if not row: return False
            if row['status'] == 'error': return True
            stale=c.execute("SELECT created_at < datetime('now','-15 minutes') AS stale FROM notifications WHERE event_key=?",(event_key,)).fetchone()
            return bool(row['status'] == 'pending' and stale and stale['stale'])
    def update_notification(self,event_key,status,detail):
        with self.connect() as c: c.execute('UPDATE notifications SET status=?,detail=? WHERE event_key=?',(status,detail,event_key))
    def dashboard_data(self):
        with self.connect() as c:
            return {'checks':[dict(x) for x in c.execute('SELECT * FROM checks ORDER BY id DESC LIMIT 20')],
            'documents':[dict(x) for x in c.execute('SELECT * FROM documents ORDER BY id DESC LIMIT 30')],
            'allotments':[dict(x) for x in c.execute('SELECT a.*,d.filename,d.local_path FROM allotments a JOIN documents d ON d.id=a.document_id ORDER BY a.id DESC LIMIT 30')],
            'notifications':[dict(x) for x in c.execute('SELECT * FROM notifications ORDER BY id DESC LIMIT 20')]}
