from __future__ import annotations
import hashlib,json,logging,re
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urljoin,urlparse
import requests
from bs4 import BeautifulSoup
from xml.etree import ElementTree
import fitz
from vsb_watch.allotment.detector import is_allotment_candidate
from vsb_watch.allotment.pdf_parser import extract_pdf_metadata,extract_student_allotment
from vsb_watch.config import settings
from vsb_watch.database import Database
from vsb_watch.notifications import send_allotment_email
from vsb_watch.schedule import is_scheduled_exam
logger=logging.getLogger(__name__)

class WebsiteMonitor:
 def __init__(self,database):
  self.database=database; self.session=requests.Session(); self.session.headers.update({'User-Agent':settings.user_agent})
  self.base_host=urlparse(settings.coe_url).netloc.lower()
 def _get(self,url):
  r=self.session.get(url,timeout=settings.request_timeout_seconds); r.raise_for_status(); return r
 def _allowed(self,url):
  host=urlparse(url).netloc.lower()
  return host == self.base_host or host.endswith('.' + self.base_host)
 def _discover_candidates(self,html,page_url):
  soup=BeautifulSoup(html,'html.parser'); found={}
  for a in soup.find_all('a',href=True):
   u=urljoin(page_url,a['href'].strip()); label=' '.join(a.get_text(' ',strip=True).split())
   if self._allowed(u) and is_allotment_candidate(u,label): found[u]=label
  # Also inspect embedded PDF links and common WordPress media search endpoint.
  for tag in soup.find_all(['iframe','embed','object']):
   raw=tag.get('src') or tag.get('data')
   if raw:
    u=urljoin(page_url,raw)
    if self._allowed(u) and ('.pdf' in u.lower() or is_allotment_candidate(u)): found[u]='Embedded document'
  return found
 def _discover_sitemap(self):
  urls=[]
  for endpoint in [urljoin(settings.coe_url,'/wp-sitemap-posts-attachment-1.xml'),urljoin(settings.coe_url,'/wp-sitemap.xml'),urljoin(settings.coe_url,'/sitemap_index.xml')]:
   try:
    r=self._get(endpoint)
    if 'xml' not in r.headers.get('Content-Type','').lower() and not r.text.lstrip().startswith('<?xml'): continue
    root=ElementTree.fromstring(r.content)
    for loc in root.iter():
     if loc.tag.rsplit('}',1)[-1].lower() == 'loc' and loc.text:
      u=loc.text.strip()
      if self._allowed(u) and is_allotment_candidate(u): urls.append(u)
   except Exception: continue
  return urls
 def _discover_wp_media(self):
  urls=[]
  for term in ('hall','allotment','seating','exam'):
   try:
    r=self._get(urljoin(settings.coe_url,f'/wp-json/wp/v2/media?search={term}&per_page=50'))
    if r.headers.get('Content-Type','').startswith('application/json'):
     for item in r.json():
      u=item.get('source_url',''); title=item.get('title',{}).get('rendered','')
      if self._allowed(u) and is_allotment_candidate(u,title): urls.append(u)
   except Exception: continue
  return urls
 def _download_pdf(self,url):
  r=self._get(url); content=r.content
  if len(content)>40*1024*1024: raise ValueError('PDF exceeds 40 MB safety limit')
  if not content.startswith(b'%PDF') and 'application/pdf' not in r.headers.get('Content-Type','').lower(): raise ValueError('Candidate is not a PDF')
  return content
 def _evidence(self,pdf_path,allotment):
  try:
   settings.evidence_dir.mkdir(parents=True,exist_ok=True)
   with fitz.open(pdf_path) as doc:
    page=doc[allotment['page']-1]; pix=page.get_pixmap(matrix=fitz.Matrix(1.6,1.6),alpha=False)
    out=settings.evidence_dir/f"{pdf_path.stem}_page_{allotment['page']}.png"; pix.save(out); return out
  except Exception: return None
 def run_once(self):
  now=datetime.now(timezone.utc).isoformat(timespec='seconds')
  settings.download_dir.mkdir(parents=True,exist_ok=True)
  try:
   candidates={}; page_errors=[]
   for page_url in settings.monitor_urls:
    try:
     page=self._get(page_url)
     page_candidates=self._discover_candidates(page.text,page_url)
     candidates.update(page_candidates)
     self.database.record_check(now,page_url,'success',f'{len(page_candidates)} candidate PDF link(s) found on page')
    except Exception as page_exc:
     page_errors.append(f'{page_url}: {page_exc}')
     self.database.record_check(now,page_url,'error',str(page_exc))
   for u in self._discover_sitemap():
    candidates.setdefault(u,'Sitemap attachment')
   for u in self._discover_wp_media():
    candidates.setdefault(u,'WordPress media search')
   if not candidates and page_errors:
    raise RuntimeError('; '.join(page_errors))
   self.database.record_check(now,settings.coe_url,'success',f'{len(candidates)} candidate PDF(s) found across {len(settings.monitor_urls)} pages, sitemap and media API')
  except Exception as exc:
   self.database.record_check(now,settings.coe_url,'error',str(exc))
   logger.exception('COE discovery failed')
   return {'candidates':0,'new':0,'changed':0,'matches':0,'errors':1}
  new=changed=errors=matches=eligible=skipped=0
  for url,label in candidates.items():
   try:
    content=self._download_pdf(url)
    digest=hashlib.sha256(content).hexdigest()
    existing=self.database.get_document(url)
    if existing and existing['sha256']==digest:
     continue
    original=Path(urlparse(url).path).name or 'allotment.pdf'
    filename=f'{digest[:12]}_{original}'
    if not filename.lower().endswith('.pdf'):
     filename+='.pdf'
    path=settings.download_dir/filename
    path.write_bytes(content)
    metadata=extract_pdf_metadata(path)
    first=existing['first_seen_at'] if existing else now
    doc_id=self.database.upsert_document({
     'url':url,'filename':filename,'sha256':digest,'local_path':str(path),
     'first_seen_at':first,'last_seen_at':now,'exam_date':metadata.get('exam_date'),
     'session':metadata.get('session'),'document_type':metadata.get('document_type') or label,
     'extraction_json':json.dumps({k:v for k,v in metadata.items() if k!='text'},ensure_ascii=False)})
    if existing: changed+=1
    else: new+=1
    # Only process personal register-number matches for the six configured dates and FN/AN.
    if not is_scheduled_exam(metadata.get('exam_date'), metadata.get('session')):
     skipped+=1
     logger.info('Ignored non-target/uncertain exam PDF: %s (date=%s, session=%s)', filename, metadata.get('exam_date'), metadata.get('session'))
     logger.info('Saved %s (%s)',filename,label)
     continue
    eligible+=1
    if settings.register_number:
     allotment=extract_student_allotment(path,settings.register_number)
     if allotment:
      matches+=1
      allotment['exam_date']=metadata.get('exam_date')
      allotment['session']=metadata.get('session')
      self.database.save_allotment(doc_id,settings.register_number,allotment)
      evidence=self._evidence(path,allotment)
      # One notification per unique PDF version and register number.
      event_key=f"{digest}:{settings.register_number}"
      try:
       send_allotment_email(self.database,event_key,allotment,path,evidence)
      except Exception:
       logger.exception('Email notification failed')
    logger.info('Saved %s (%s)',filename,label)
   except Exception:
    errors+=1
    logger.exception('Could not process candidate %s',url)
  return {'candidates':len(candidates),'new':new,'changed':changed,'eligible_target_pdfs':eligible,'ignored_non_target_pdfs':skipped,'matches':matches,'errors':errors}
