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
 p.add_argument('--search-allotment',help='Search published examination allotments for a register number (V2.3)')
 p.add_argument('--all-history',action='store_true',help='Include past examination history (default is current published only)')
 p.add_argument('--ingest-all',action='store_true',help='Parse all downloaded PDFs and ingest allotments into database and Supabase')
 p.add_argument('--show-schedule',action='store_true')
 p.add_argument('--test-email',action='store_true',help='Send a test notification email using .env settings')
 p.add_argument('--test-allotment',action='store_true',help='Run a one-time test against separate hall and seating PDFs')
 p.add_argument('--register',help='Register number for --test-allotment (does not change .env)')
 p.add_argument('--date',help='Exam date for --test-allotment in YYYY-MM-DD format')
 p.add_argument('--session',choices=['FN','AN'],help='Exam session for --test-allotment')
 p.add_argument('--hall-url',help='Official hall-allotment PDF URL')
 p.add_argument('--seating-url',help='Official seating-allotment PDF URL')
 p.add_argument('--send-test-result-email',action='store_true',help='Send the one-time test report to NOTIFICATION_EMAIL')
 args=p.parse_args(); configure_logging(); db=Database(settings.database_path); db.initialize()
 if args.test_email:
  from vsb_watch.notifications import send_test_email
  send_test_email(); print('Test email sent.'); return 0
 if args.test_allotment:
  required = {'--register':args.register,'--date':args.date,'--session':args.session,'--hall-url':args.hall_url,'--seating-url':args.seating_url}
  missing = [k for k,v in required.items() if not v]
  if missing: p.error('--test-allotment requires ' + ', '.join(missing))
  from vsb_watch.allotment.manual_test import run_manual_test
  result = run_manual_test(args.register,args.date,args.session,args.hall_url,args.seating_url,args.send_test_result_email)
  print('TEST RESULT')
  for key in ('register_number','exam_date','session','hall_number','seat_number','hall_page','seating_page'):
   print(f'{key}: {result[key]}')
  print(f"Hall screenshot: {result['hall_screenshot']}")
  print(f"Seating screenshot: {result['seating_screenshot']}")
  print('Test email sent.' if args.send_test_result_email else 'Email not sent. Re-run with --send-test-result-email after verifying values.')
  return 0
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
 if args.search_allotment:
  from vsb_watch.supabase_client import supabase_client
  reg = args.search_allotment.strip()
  current_only = not args.all_history
  records = db.find_allotments_by_register(reg, current_only=current_only)
  if not records and supabase_client.is_configured():
   records = supabase_client.search_allotments(reg, current_only=current_only)
  if not records:
   label = "currently published / upcoming" if current_only else "published"
   print(f"Not Allotted: No {label} examination allotment found for register number '{reg}'.")
   return 0
  hdr = "CURRENT PUBLISHED EXAMINATION ALLOTMENT" if current_only else "EXAMINATION ALLOTMENT HISTORY"
  print(f"=== {hdr} FOR REGISTER: {reg} ({len(records)} EXAM(S)) ===")
  for idx, r in enumerate(records, 1):
   print(f"\n[Exam {idx}] Date: {r.get('exam_date')} | Session: {r.get('session')}")
   print(f"  Subject : [{r.get('subject_code') or '-'}] {r.get('subject_name') or 'Theory Examination'}")
   print(f"  Hall No : {r.get('hall_number') or 'Check Hall'}")
   print(f"  Seat No : {r.get('seat_number') or 'Check Hall Display'}")
   if r.get('page') or r.get('page_number'):
    print(f"  PDF Page: {r.get('page') or r.get('page_number')}")
   if r.get('seating_image'):
    print(f"  Chart   : {r.get('seating_image')}")
  return 0
 if args.ingest_all:
  from vsb_watch.allotment.pdf_parser import extract_all_pdf_allotments
  from vsb_watch.allotment.detector import is_allotment_filename
  from vsb_watch.supabase_client import supabase_client
  total_ingested = 0
  pdf_files = [f for f in settings.download_dir.glob('*.pdf') if is_allotment_filename(f.name)]
  print(f"Found {len(pdf_files)} candidate exam allotment PDF(s) to process in {settings.download_dir}...")
  for f in pdf_files:
   try:
    records = extract_all_pdf_allotments(f)
    if records:
     count = db.save_bulk_allotments(None, records)
     total_ingested += count
     print(f"  Ingested {count} records from {f.name}")
     if supabase_client.is_configured():
      sb_res = supabase_client.upsert_allotments(records)
      print(f"    Supabase synced {sb_res.get('upserted', 0)} records")
   except Exception as exc:
    print(f"  Error processing {f.name}: {exc}")
  print(f"Total allotment records ingested: {total_ingested}")
  from vsb_watch.config import ROOT_DIR
  db.export_allotments_data(ROOT_DIR / 'portal/allotments.json', ROOT_DIR / 'portal/allotments.js', current_only=True)
  db.export_allotments_data(ROOT_DIR / 'docs/allotments.json', ROOT_DIR / 'docs/allotments.js', current_only=True)
  db.export_allotments_data(ROOT_DIR / 'allotments.json', ROOT_DIR / 'allotments.js', current_only=True)
  return 0
 if args.once: print(WebsiteMonitor(db).run_once()); return 0
 if args.dashboard:
  from vsb_watch.dashboard import create_app
  thread=threading.Thread(target=monitor_loop,args=(db,),daemon=True); thread.start()
  create_app(db).run(host=settings.dashboard_host,port=settings.dashboard_port,debug=False,use_reloader=False); return 0
 monitor_loop(db); return 0
if __name__=='__main__': raise SystemExit(main())
