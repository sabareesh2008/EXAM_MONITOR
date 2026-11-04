from __future__ import annotations
from functools import wraps
from flask import Flask,render_template,redirect,url_for,request,Response,send_file,flash
from vsb_watch.config import settings
from vsb_watch.schedule import schedule_as_dict
from vsb_watch.database import Database
from vsb_watch.monitoring.website_monitor import WebsiteMonitor
import hmac

def create_app(db: Database):
 app=Flask(__name__); app.secret_key=settings.dashboard_secret
 @app.after_request
 def add_cors_headers(response):
  response.headers['Access-Control-Allow-Origin'] = '*'
  response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
  response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, x-requested-with'
  return response
 def protect(fn):
  @wraps(fn)
  def wrapper(*args,**kwargs):
   # Local-only default. Set DASHBOARD_PASSWORD before exposing the dashboard publicly.
   import os
   password=os.getenv('DASHBOARD_PASSWORD','')
   if password:
    auth=request.authorization
    if not auth or not hmac.compare_digest(auth.password or '',password):
     return Response('Authentication required',401,{'WWW-Authenticate':'Basic realm="VSB Exam Watch"'})
   return fn(*args,**kwargs)
  return wrapper
 @app.get('/')
 @protect
 def index():
  data=db.dashboard_data()
  return render_template('dashboard.html',data=data,schedule=schedule_as_dict(),reg=settings.register_number,department=settings.department,interval=settings.poll_interval_minutes,coe_url=settings.coe_url,monitor_urls=settings.monitor_urls)
 @app.post('/scan')
 @protect
 def scan():
  result=WebsiteMonitor(db).run_once(); flash(f"Scan completed: {result}",'success' if not result['errors'] else 'warning'); return redirect(url_for('index'))
 @app.get('/health')
 def health(): return {'status':'ok','service':'VSB Exam Watch'}
 @app.get('/api/allotments/<reg>')
 def api_allotments(reg):
  current_only = not (request.args.get('all_history') == 'true')
  results = db.find_allotments_by_register(reg, current_only=current_only)
  return {'register_number': reg, 'count': len(results), 'current_only': current_only, 'allotments': results}
 @app.get('/search')
 def search():
  query = request.args.get('register_number', '').strip()
  current_only = not (request.args.get('all_history') == 'true')
  results = db.find_allotments_by_register(query, current_only=current_only) if query else []
  return render_template('dashboard.html', search_query=query, current_only=current_only, search_results=results, data=db.dashboard_data(), schedule=schedule_as_dict(), reg=settings.register_number, department=settings.department, interval=settings.poll_interval_minutes, coe_url=settings.coe_url, monitor_urls=settings.monitor_urls)
 @app.get('/documents/<int:doc_id>')
 @protect
 def document(doc_id):
  data=db.dashboard_data();
  for d in data['documents']:
   if d['id']==doc_id: return send_file(d['local_path'],as_attachment=True,download_name=d['filename'])
  return 'Not found',404
 return app
