from __future__ import annotations
import argparse,logging,time,threading
from vsb_watch.config import settings
from vsb_watch.database import Database
from vsb_watch.monitoring.website_monitor import WebsiteMonitor

def configure_logging():
 settings.log_dir.mkdir(parents=True,exist_ok=True)
 logging.basicConfig(level=logging.INFO,format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',handlers=[logging.StreamHandler(),logging.FileHandler(settings.log_dir/'monitor.log',encoding='utf-8')])

def monitor_loop(db,stop_event=None):
 monitor=WebsiteMonitor(db)
 while stop_event is None or not stop_event.is_set():
  try: monitor.run_once()
  except Exception: logging.getLogger(__name__).exception('Monitoring cycle failed')
  if stop_event is None: time.sleep(settings.poll_interval_minutes*60)
  elif stop_event.wait(settings.poll_interval_minutes*60): break

def main():
 p=argparse.ArgumentParser(description='VSB Exam Watch')
 p.add_argument('--once',action='store_true',help='Run one monitoring cycle')
 p.add_argument('--dashboard',action='store_true',help='Start dashboard and background monitoring')
 p.add_argument('--search-register',help='Search already downloaded PDFs for a register number')
 p.add_argument('--show-schedule',action='store_true')
 p.add_argument('--test-email',action='store_true',help='Send a test notification email using .env settings')
 args=p.parse_args(); configure_logging(); db=Database(settings.database_path); db.initialize()
 if args.test_email:
  from vsb_watch.notifications import send_test_email
  send_test_email(); print('Test email sent.'); return 0
 if args.show_schedule:
  from vsb_watch.schedule import schedule_as_dict
  import json; print(json.dumps(schedule_as_dict(),indent=2)); return 0
 if args.search_register:
  from vsb_watch.allotment.pdf_parser import search_register_in_pdf
  found=False
  for f in settings.download_dir.glob('*.pdf'):
   for item in search_register_in_pdf(f,args.search_register): found=True; print(f"{f.name}: page {item['page']} | hall={item['hall_number']} | seat={item['seat_number']} | {item['extraction_confidence']}")
  if not found: print('No match found in downloaded PDFs.')
  return 0
 if args.once: print(WebsiteMonitor(db).run_once()); return 0
 if args.dashboard:
  from vsb_watch.dashboard import create_app
  thread=threading.Thread(target=monitor_loop,args=(db,),daemon=True); thread.start()
  create_app(db).run(host=settings.dashboard_host,port=settings.dashboard_port,debug=False,use_reloader=False); return 0
 monitor_loop(db); return 0
if __name__=='__main__': raise SystemExit(main())
