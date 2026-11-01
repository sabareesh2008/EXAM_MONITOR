# GitHub Actions configuration

Create these repository secrets under Settings -> Secrets and variables -> Actions -> New repository secret:

- `REGISTER_NUMBER` — your register number
- `NOTIFICATION_EMAIL` — email address that receives alerts
- `SMTP_USER` — Gmail account used to send alerts
- `SMTP_PASSWORD` — Gmail App Password (never your normal Gmail password)

Create these repository variables under the Variables tab:

- `STUDENT_NAME` — optional
- `DEPARTMENT` — e.g. ECE
- `SMTP_HOST` — smtp.gmail.com
- `SMTP_PORT` — 587

The workflow runs at minute 3 and 33 of each hour (UTC), approximately every 30 minutes. GitHub may delay scheduled jobs. The workflow commits only the SQLite state database so duplicate detection survives between fresh GitHub-hosted runners. Downloaded PDFs, evidence images and logs are not committed.

Keep the repository private. Never commit `.env`, Gmail App Passwords, or personal credentials. Enable Actions and ensure the workflow file is on the repository's default branch.
