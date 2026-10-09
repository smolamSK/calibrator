# Calibrator

A web app that tracks device calibrations: owners, full calibration history and certificates, custom fields per category, email reminders and a calendar feed.

Django + SQLite. Data lives in `data/` (database and uploaded files). Configuration lives in `.env`.

## Roles
| Role | Devices visible | Can edit | Extra |
|---|---|---|---|
| Owner | own | own | |
| Viewer | all | own | |
| Editor | all | all | import, audit log, receives all reminders |
| Administrator | all | all | categories and fields, users, settings and SMTP |

## Setup (once)
```sh
sudo apt install -y python3-venv python3-pip        # already done
cd ~/calibrator
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env    # then edit: SECRET_KEY, ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS
.venv/bin/python manage.py migrate
.venv/bin/python manage.py collectstatic --noinput
.venv/bin/python manage.py createsuperuser           # your admin login
```

## Run as a service
```sh
sudo cp deploy/calibrator.service deploy/calibrator-reminders.service deploy/calibrator-reminders.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now calibrator.service calibrator-reminders.timer
```
The app listens on `0.0.0.0:8000`, so point the reverse proxy there. Behind HTTPS, set this in `.env`, then run `sudo systemctl restart calibrator`:
```
ALLOWED_HOSTS=calibrator.example.com,192.168.205.174,localhost
CSRF_TRUSTED_ORIGINS=https://calibrator.example.com
BEHIND_HTTPS_PROXY=1
```
The proxy must pass the `Host`, `X-Forwarded-Proto` and `X-Forwarded-For` headers. Allow uploads of at least 30 MB (for nginx: `client_max_body_size 30m;`).

## First steps in the app
1. **Admin → Settings**: set the public URL. Add SMTP details and click "Send test email".
2. **Admin → Categories**: create categories with an interval, reminder days (e.g. `60,14,0`) and custom fields.
3. **Admin → Users**: create accounts and roles.
4. **Import**: upload an Excel or CSV file, or add devices by hand.

## Reminders
The `calibrator-reminders.timer` runs `send_reminders` every day at 07:00 (catching up if a run was missed).
- **Before the due date:** one email at each lead-day threshold set on the category.
- **After the due date:** an email every N days, set in Settings.
- **Recipients:** the device owner plus all Editors and Administrators who have notifications on, each getting one summary email per day.
- **Excluded devices:** Retired and Out of service devices never trigger reminders.

To test without sending: `.venv/bin/python manage.py send_reminders --dry-run --date 01.12.2026`

## Maintenance
- Tests: `.venv/bin/python manage.py test calibration`
- Backup: `deploy/backup.sh` writes to `~/calibrator-backups/` and keeps the last 30. Add it to cron: `crontab -e` → `30 2 * * * /home/smolam/calibrator/deploy/backup.sh`
- Logs: `journalctl -u calibrator -f`
- Update code: `sudo systemctl restart calibrator`
- Built-in Django admin (raw data): `/django-admin/`, for superusers only.
