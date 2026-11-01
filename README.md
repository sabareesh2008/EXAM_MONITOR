# VSB Exam Watch V2 — Personal Allotment Monitoring System

A personal, 24/7 monitoring application for the **V.S.B. Engineering College, Karur** Controller of Examinations website. It discovers hall-allotment PDF links from the official COE page, college homepage and COE portal, WordPress media search and available XML sitemaps; downloads new/changed PDFs; extracts metadata; searches the configured register number; creates page-image evidence; sends email alerts; and provides a protected web dashboard.

**Official source:** https://vsbec.edu.in/controller-of-examination/  
**COE portal:** https://coe.vsbec.edu.in/  
The college's COE page describes the office's responsibility for exam hall arrangements. A real May 2026 hall-allotment PDF was also located and provides an example of the department-wise format. The November 2026 documents and all extraction patterns still need live validation when published.

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
