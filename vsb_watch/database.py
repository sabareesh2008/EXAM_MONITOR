from __future__ import annotations
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
            CREATE TABLE IF NOT EXISTS allotments(id INTEGER PRIMARY KEY,document_id INTEGER,register_number TEXT,exam_date TEXT,session TEXT,hall_number TEXT,seat_number TEXT,page INTEGER,confidence TEXT,context TEXT,created_at TEXT,UNIQUE(document_id,register_number),FOREIGN KEY(document_id) REFERENCES documents(id));
            CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY,event_key TEXT UNIQUE,recipient TEXT,subject TEXT,status TEXT,detail TEXT,created_at TEXT);
            ''')
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
            c.execute('''INSERT INTO allotments(document_id,register_number,exam_date,session,hall_number,seat_number,page,confidence,context,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,datetime('now')) ON CONFLICT(document_id,register_number) DO UPDATE SET exam_date=excluded.exam_date,session=excluded.session,hall_number=excluded.hall_number,seat_number=excluded.seat_number,page=excluded.page,confidence=excluded.confidence,context=excluded.context''',
            (document_id,reg,meta.get('exam_date'),meta.get('session'),meta.get('hall_number'),meta.get('seat_number'),meta.get('page'),meta.get('extraction_confidence'),meta.get('context')))
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
