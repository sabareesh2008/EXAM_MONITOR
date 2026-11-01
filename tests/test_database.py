from pathlib import Path
from vsb_watch.database import Database

def test_notification_event_dedup_and_retry(tmp_path: Path):
    db=Database(tmp_path/'test.sqlite3'); db.initialize()
    assert db.create_notification('event-1','x@example.com','subject','pending','queued')
    assert not db.create_notification('event-1','x@example.com','subject','pending','queued')
    db.update_notification('event-1','error','smtp failed')
    assert db.create_notification('event-1','x@example.com','subject','pending','retry')
