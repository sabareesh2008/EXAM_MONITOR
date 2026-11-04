# VSB Exam Watch V2.3 — Automatic Student Examination Allotment Portal

An automated Controller of Examinations monitoring and student examination allotment system for **V.S.B. Engineering College, Karur**. 

### What's New in V2.3: Automatic Student Examination Allotment Portal
- **Zero-Friction Search Portal**: Any student enters **only their Register Number** to view all their allotted exams across published dates.
- **Support for Regular & Arrear Exams**: Automatically surfaces all matching exam dates, including students taking multiple FN and AN examinations on the same day.
- **Serverless Architecture**: 
  - **GitHub Pages Portal** (`docs/` and `portal/`) for high-speed, mobile-responsive student lookup.
  - **Supabase Cloud Sync**: All published exam allotments are ingested and synced to Supabase PostgreSQL with Row Level Security (RLS).
  - **Zero hosting costs**: Entire stack runs on GitHub Actions cron + Supabase + GitHub Pages.
- **Intelligent PDF Ingestion**: Extracts all student registers, hall numbers, seat numbers, subject codes, and subject names from both Hall Allotment and Seating Chart PDFs.
- **Backward Compatible**: Preserves existing V2.2.1 personal single-student email alerting, CLI testing tools (`--test-allotment`), and local SQLite database.

**Official source:** https://vsbec.edu.in/controller-of-examination/  
**COE portal:** https://coe.vsbec.edu.in/  

---

## Student Search Portal (GitHub Pages)

The public search portal is located in `docs/` and `portal/index.html`.
- Deploy it instantly by enabling **GitHub Pages** from the repository settings (`Settings -> Pages -> Deploy from branch: main -> /docs`).
- Students enter their register number and immediately receive clean visual cards with:
  - **Exam Date & Day of Week**
  - **Session (FN 09:30 AM / AN 01:30 PM)**
  - **Subject Code & Subject Title**
  - **Exam Hall / Room Number**
  - **Allocated Seat Number**
  - **Printable Slip option**
- If no records are found, a clear **Not Allotted / Not Yet Published** notice is displayed.

---

## Supabase Database Setup

1. Create a free project at [supabase.com](https://supabase.com).
2. Go to the **SQL Editor** in Supabase and run the script in [`supabase_schema.sql`](supabase_schema.sql).
3. Copy your **Project URL** and **API Keys** (`anon` and `service_role`).
4. Set them in GitHub Secrets or `.env`:
   - `SUPABASE_URL=https://your-project.supabase.co`
   - `SUPABASE_KEY=your-supabase-service-role-or-anon-key`
   - `SUPABASE_TABLE=allotments`

---

## CLI Usage (V2.3)

```bash
# Search any student's published allotments directly from terminal:
python main.py --search-allotment 922524103002

# Ingest all downloaded PDFs into local SQLite and Supabase:
python main.py --ingest-all

# Run one monitoring cycle (discovers new PDFs, extracts, and syncs):
python main.py --once

# Start web dashboard:
python main.py --dashboard
```

## Features

- Five-minute default polling (minimum five minutes; avoid aggressive polling).
- HTML link scanning, embedded PDF scanning, WordPress REST media search and common WordPress XML sitemap discovery.
- Same-college-host restriction for discovered documents.
- PDF content-type/signature checks and 40 MB download safety limit.
- SHA-256 change detection and SQLite history.
- PyMuPDF text extraction; optional Tesseract OCR fallback for image-only pages.
- Register-number matching; hall/seat extraction only when explicit labels and values are close enough to the matching register row.
- Evidence PNG generated from the matching PDF page.
- SMTP email notifications with PDF and evidence attachment; deduplication by document hash + register number.
- Responsive dashboard showing schedule, matches, downloads, recent checks and email history.
- `/health` health endpoint; Docker restart policy and persistent `data/` volume.

## Configured exam dates

| Date | Sessions watched | FN | AN |
|---|---|---|---|
| 06 Nov 2026 | FN + AN | 09:30–12:30 | 13:30–16:30 |
| 11 Nov 2026 | FN + AN | 09:30–12:30 | 13:30–16:30 |
| 14 Nov 2026 | FN + AN | 09:30–12:30 | 13:30–16:30 |
| 17 Nov 2026 | FN + AN | 09:30–12:30 | 13:30–16:30 |
| 20 Nov 2026 | FN + AN | 09:30–12:30 | 13:30–16:30 |
| 24 Nov 2026 | FN + AN | 09:30–12:30 | 13:30–16:30 |

Both sessions are monitored on every date because the exact FN/AN subject allocation was not supplied. This does **not** assert that each date has both sessions. The time windows are configuration metadata; the actual date/session printed inside the official PDF is authoritative.

## Windows setup

1. Extract the ZIP to a folder such as `C:\VSB_EXAM_WATCH`.
2. Install Python 3.11 or 3.12.
3. Open Command Prompt in that folder:

```bat
py -3.11 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
copy .env.example .env
```

4. Open `.env` and set `REGISTER_NUMBER`, `NOTIFICATION_EMAIL`, `SMTP_USER`, `SMTP_PASSWORD`, and a strong `DASHBOARD_PASSWORD`. Keep `.env` private.
5. For Gmail, enable 2-Step Verification and create a Google App Password. Use that 16-character App Password as `SMTP_PASSWORD`; do not use your normal Gmail password.
6. Optionally verify SMTP before waiting for an allotment:

```bat
python main.py --test-email
```

7. Run tests and inspect schedule:

```bat
pytest -q
python main.py --show-schedule
```

8. Run one scan:

```bat
python main.py --once
```

9. Start the dashboard and background monitoring:

```bat
python main.py --dashboard
```

Open `http://127.0.0.1:5000`. Click **Run scan now** to trigger a manual check. The dashboard is protected with HTTP Basic Authentication when `DASHBOARD_PASSWORD` is set (use `admin` as the username and the configured password). For local use, keep `DASHBOARD_HOST=127.0.0.1`.

## OCR setup on Windows

Text-based PDFs work without OCR. For scanned PDFs, install Tesseract OCR for Windows and ensure `tesseract.exe` is on PATH. `pytesseract` and Pillow are installed by requirements. If OCR is unavailable, the program records the document but may not find text embedded only as an image.

## Email setup

- `NOTIFICATION_EMAIL`: destination inbox.
- `SMTP_USER`: Gmail sender address.
- `SMTP_PASSWORD`: Google App Password.
- The first matching allotment for a given PDF hash + register number triggers one email. A changed PDF creates a new event.
- Email body explicitly says when hall/seat could not be confidently extracted. The original PDF and a screenshot of the matching page are attached.

## 24/7 cloud deployment

Use a Linux VPS or a Docker-capable always-on host with persistent disk storage. Free web hosts may sleep and therefore cannot guarantee 24/7 monitoring.

1. Install Docker Engine and Docker Compose on the server.
2. Upload this project folder privately.
3. Create `.env` on the server with the real personal values and a strong dashboard password. Never commit it.
4. Set `DASHBOARD_HOST=0.0.0.0` only behind HTTPS/reverse proxy and firewall; do not expose port 5000 directly to the public internet.
5. Run:

```bash
docker compose up -d --build
docker compose logs -f
```

6. Map persistent storage to `./data`; it contains the SQLite database, PDFs, evidence screenshots and logs. Back it up privately.
7. Configure HTTPS and restrict dashboard access (VPN/IP allowlist/reverse-proxy authentication recommended). Do not expose student data or PDFs publicly.

`restart: unless-stopped` restarts the service after process/server restarts. It does not protect against a provider outage or a deleted persistent disk.

## Data layout

```text
VSB_EXAM_WATCH/
  main.py
  .env.example
  requirements.txt
  Dockerfile
  docker-compose.yml
  vsb_watch/
    config.py
    database.py
    schedule.py
    notifications.py
    dashboard.py
    monitoring/website_monitor.py
    allotment/detector.py
    allotment/pdf_parser.py
    templates/dashboard.html
    static/style.css
  tests/
  data/                 # runtime files; private; do not commit
    downloads/
    evidence/
    logs/
```

## Important validation limits

- Live PDF discovery and downloading must be tested against the official website from the target runtime. A page can publish PDFs through scripts or access rules that are not visible to public link scanning.
- VSB's May 2026 sample is a department-wise list. A register number may be found while the hall is not confidently extractable from the text's table order. In that case the dashboard/email displays **Not extracted**, rather than guessing.
- Seat number is only reported if the PDF explicitly contains seat/bench numbering near the matched register. Many department-wise hall lists provide a hall but no individual seat number.
- OCR requires the external Tesseract executable. It is not enough to install the Python wrapper alone.
- This tool is an independent personal monitor, not an official college service. Always verify the attached original allotment PDF and college notices.
- A missing match does not mean no allotment has been published; check monitoring errors and the official portal.

## Privacy and safety

Do not commit `.env`, database files, downloaded allotment PDFs, evidence screenshots, or register numbers to a public repository. Use only your own register number and email address. Protect cloud storage and dashboard access.


## Strict target-date notification rule (V2.1)

A personal allotment email is sent only when the PDF metadata identifies one of the six configured November 2026 dates AND FN or AN, and the configured register number is found. If date or session cannot be identified unambiguously, the PDF is not treated as an eligible personal allotment and no alert is sent. A hall/seat value is included only when explicitly extracted near the matched register number; otherwise the email says it was not identified and attaches the official PDF evidence. The parser may use a date/session encoded in the official PDF filename when the filename is unambiguous; confirm this against actual VSB documents before relying on it.

## Continuous monitoring

Run `start.bat` or `python main.py --dashboard`. The background monitor repeats every `POLL_INTERVAL_MINUTES` (default 5; minimum 5). For Windows monitoring, keep the computer powered on, connected to the internet, and prevent sleep/hibernation. For genuine unattended 24/7 operation, deploy the Docker service on an always-on VPS with persistent `data/` storage. A laptop that sleeps or is switched off cannot monitor.

## Important: existing V2 installation

Back up your existing `data/` folder and `.env` before replacing project files. Keep the existing `.env` and do not overwrite it with `.env.example`.

## One-time test with a different register number (V2.2)

VSB publishes two separate PDFs for the same date/session:

- **Hall allotment**: maps a register number to the examination hall.
- **Seating allotment**: maps a register number to an individual seat number and page.

Use this one-time test to verify both PDFs, page screenshots and email delivery without changing `REGISTER_NUMBER` in `.env` or altering your normal exam schedule.

Example for the 05 Nov 2026 FN PDFs shown in the VSB COE page:

```bat
python main.py --test-allotment ^
  --register 922524103002 ^
  --date 2026-11-05 ^
  --session FN ^
  --hall-url "https://vsbec.edu.in/wp-content/uploads/2026/11/05.11.26-HALL-FN.pdf" ^
  --seating-url "https://vsbec.edu.in/wp-content/uploads/2026/11/05.11.26-SEATING-FN.pdf"
```

The first run downloads both PDFs, finds the register number, extracts the hall and seat, and creates highlighted PNG evidence. It **does not send an email**. Review the printed values first. If they are correct, run the same command again and append:

```bat
  --send-test-result-email
```

The test report goes to `NOTIFICATION_EMAIL` using the SMTP settings already in `.env`. It attaches both original PDFs and both matching-page screenshots. The test register number is passed on the command line only and does not replace your personal `.env` register number. If either hall or seat cannot be extracted confidently, the command stops and does not send an incomplete email.

The parser uses text positions from the PDF: for VSB seating charts, the seat number is read from the numbered cell immediately to the left of the matched register number. Always compare the result and attached evidence with the official PDFs before relying on notifications. If VSB changes its PDF layout, update and test the parser before using it.


## V2.2.1 seating-box validation update

The seating parser now uses PyMuPDF word coordinates plus drawn rectangle geometry. A seat is accepted only from the numeric left-hand rectangle immediately adjacent to the exact register-number rectangle (range 1–200). It scans every PDF page; duplicate page matches, missing boxes, partial words (including `ING`), and ambiguous cell geometry produce `UNKNOWN`. The one-time test command refuses to email unless the seat is numeric, page-specific evidence exists, and both PDFs' printed date/session match the requested values. The test email attaches both original PDFs and both screenshots. The routine monitoring email path also blocks unknown/non-numeric seats.

The included automated suite uses synthetic PDFs and verifies the geometry and safety rules. **The November 5, 2026 VSB source PDFs were not included in the supplied ZIP and could not be reached from the build environment**, so the synthetic tests are not a substitute for the required live-PDF confirmation. Run the manual command below on a Windows machine with internet access and inspect both screenshots before relying on the result.
