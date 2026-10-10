# Calibrator – Admin manual

This manual is for **Editors** and **Administrators**. It covers everything beyond day-to-day use: manufacturers and models, custom fields, importing, users and settings. The last part, *Server administration*, is for whoever runs the server.

Everything in the **User manual** applies to you as well.

## Roles and permissions

| | Owner | Viewer | Editor | Administrator |
|---|:-:|:-:|:-:|:-:|
| See own devices | ✓ | ✓ | ✓ | ✓ |
| See all devices | | ✓ | ✓ | ✓ |
| Edit own devices, record calibrations, upload files | ✓ | ✓ | ✓ | ✓ |
| Edit all devices, change owners | | | ✓ | ✓ |
| Add manufacturers/models with "+" on the device form | ✓ | ✓ | ✓ | ✓ |
| **Brands & models** page: intervals, reminders, custom fields | | | ✓ | ✓ |
| **Import**, **Audit log** | | | ✓ | ✓ |
| Receives reminders for **all** devices | | | ✓ | ✓ |
| Delete devices | | | | ✓ |
| **Admin → Users**, **Admin → Settings & email** | | | | ✓ |

Owners and Viewers who create a device always become its owner.

Superusers created with `createsuperuser` are Administrators. They can also open the raw database view at `/django-admin/`.

## Brands & models

Open **Brands & models** in the top menu. Manufacturers and models are shared lists that every device picks from. They also carry the **calibration interval**, the **reminder days** and the **custom fields** for their devices.

### Adding, renaming, deleting

- Add a manufacturer with **Add manufacturer**. Add a model with **Add model**: choose its manufacturer, type the name and click **Add**.
- Users can also add entries while editing a device, with the **+** button. Names are compared without regard to upper/lower case, so "FLUKE" and "Fluke" are the same entry.
- Click a name to open its page, then **Edit** to rename it or change its settings.
- **Moving a model** to another manufacturer also changes the manufacturer of every device that uses that model.
- An entry that is used by devices can be renamed but not deleted. Deleting a manufacturer also deletes its unused models.

### Interval and reminder days

On a manufacturer's or model's **Edit** page:

- **Calibration interval (months)**: how often its devices must be calibrated.
- **Reminder days**: when reminder emails go out, as days before the due date, comma separated. For example, `60,14,0` sends reminders 60 days before, 14 days before and on the due date.

Both are optional. A device uses the first value that is set, in this order:

1. **Interval override** on the device itself (interval only)
2. its **model**
3. its **manufacturer**
4. the default in **Admin → Settings & email**

The manufacturer or model page shows the value in effect and where it comes from, e.g. "(from manufacturer)" or "(default)".

When you change an interval, the next calibration date of every affected device is recalculated straight away. That covers devices without their own override.

## Custom fields

Custom fields add device information that differs between kinds of equipment, such as *Measuring range* for multimeters or *Jaw length* for calipers. They are defined on a **manufacturer** or on a **model**:

- **Manufacturer fields** appear on every device of that manufacturer.
- **Model fields** appear only on devices of that model, after the manufacturer's fields.

Open the manufacturer or model page and click **+ Add field**. The settings are:

| Setting | Meaning |
|---|---|
| **Name** | label shown on the form; must be unique within that manufacturer or model |
| **Field type** | *Text*, *Long text*, *Number*, *Dropdown*, *Date*, *Checkbox* or *File* |
| **Required** | the device cannot be saved without a value. Use this sparingly. |
| **Show in list** | shown as a column in the device list when it is filtered by this manufacturer or model |
| **Order** | position on the form, smallest first |
| **Help text** | hint shown under the field |
| **Options** | for *Dropdown* only: one option per line |

Notes:

- Once devices have values for a field, its **type** can no longer be changed. Its name, options and the other settings can still be changed.
- Removing a dropdown option doesn't change existing values. A device that already has the old option keeps it.
- **Deleting a field deletes all values** stored for it, including uploaded files. The confirmation page tells you how many there are.
- If a device moves to another manufacturer or model, the values of fields that no longer apply are kept but hidden. They come back if the device moves back.

## Importing devices

**Import** creates or updates many devices at once from an **Excel (.xlsx)** or **CSV** file. CSV files can use `;` or `,` as the separator.

1. Prepare a file with **column headers in the first row** and **one device per row**.
2. **Upload & preview**. Calibrator guesses which column is which.
3. Check the **Column mapping** and correct it if needed, then click **Update preview**.
4. The preview marks each row as *new*, *update* or *error*, with the problems listed. Nothing has been saved yet.
5. Click **Import N row(s)**. If some rows have errors, either fix the file and **Start over**, or tick **Skip rows with errors**.

### Columns

| Column | Required | Recognised headers (any case) | Notes |
|---|:-:|---|---|
| Asset ID | ✓ | asset id, asset, asset tag, id, inventory number, inv no, tag | an existing Asset ID **updates** that device |
| Name | ✓ | name, device, device name, description, instrument | |
| Owner | ✓ | owner, user, responsible, username, email, owner email | username, email or full name of an existing user |
| Status | | status, state | Active, At calibration, Out of service, Retired |
| Manufacturer | | manufacturer, make, brand, vendor | created automatically if missing |
| Model | | model | needs a manufacturer; created automatically if missing |
| Serial number | | serial, serial number, serial no, s/n, sn | |
| Location | | location, place, room, site | |
| Interval override (months) | | interval, interval months, calibration interval | only for devices that differ from their model/manufacturer |
| Last calibration date | | last calibration, calibration date, last cal, calibrated | adds a history entry; DD.MM.YYYY is preferred, and YYYY-MM-DD and Excel dates also work |
| Certificate number | | certificate, certificate no, cert no | stored on that history entry |
| Notes | | notes, note, comment, remarks | |

For updates, the required columns may be empty. Empty cells don't overwrite existing values.

**Custom fields**: a column whose header equals a custom field name of the row's manufacturer or model fills that field. Dropdown values must match one of the options. Checkboxes accept yes/no, 1/0, true/false or x. File fields cannot be imported. Only manufacturers and models that **already exist** have fields, so create them and their fields first, then import.

## Audit log

**Audit log** lists who created, changed or deleted what, with the old and new values. It covers devices, calibrations, files, manufacturers, models, fields, users, settings and imports. **Search** filters by user, object or action, and the latest 500 entries are shown. Each device page also shows its own **Change log**.

## Users (Administrators)

**Admin → Users**:

- **+ New user**: username, name, **email** (required, used for reminders and password reset), **role**, **Email notifications**, and an initial password.
- **edit**: change details or the role. Untick **Active** to block a user who leaves. Their devices and history are kept, and they get no emails. Reassign their devices to someone else (filter the device list by **Owner**).
- **set password**: set a new password for a user, e.g. after a lockout or a forgotten password when email isn't working.
- A user locked out after 5 failed logins is unlocked automatically after 30 minutes.

## Settings (Administrators)

**Admin → Settings & email**.

**General & notifications**

- **Site name**: shown in the header and the email subjects.
- **Base URL**: the public address, e.g. `https://calibrator.example.com`. It's needed for the links in emails and for the calendar links.
- **Notifications enabled**: the master switch for all reminder emails.
- **Due soon days**: how many days before the due date a device counts as *Due soon*.
- **Overdue repeat days**: how often overdue reminders are repeated.
- **Default color mode** and **Default accent color**: the look for everyone who hasn't chosen their own in **Profile & calendar → Appearance**, and for the login page.
- **Default calibration interval (months)** and **Default reminder days**: used when neither the model nor the manufacturer sets its own. Changing the default interval recalculates the affected due dates.

**Outgoing email (SMTP)**: host, port, security, username, password and **From address**. Click **Send test email** after saving, and the test goes to your own address. Some examples:

- Gmail: `smtp.gmail.com`, 587, STARTTLS, your address and an *app password*.
- Microsoft 365: `smtp.office365.com`, 587, STARTTLS. SMTP AUTH must be enabled for the mailbox.
- Internal relay: your mail server, often port 25, no security and no login.

The SMTP password is stored and never shown again. Leave the field empty to keep it, or tick **Remove stored SMTP password**.

## Server administration

This part is for the person who runs the server. Paths assume the app lives in `~/calibrator`.

### Components

- **Django app** served by gunicorn on `0.0.0.0:8000` (`calibrator.service`), behind your reverse proxy.
- **SQLite database** and uploaded files in `data/` (`data/db.sqlite3`, `data/media/`).
- **Configuration** in `.env`: `SECRET_KEY`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `BEHIND_HTTPS_PROXY`, `TIME_ZONE`. See `.env.example`. Never commit `.env`.
- **Reminders**: `calibrator-reminders.timer` runs `manage.py send_reminders` every day at 07:00 and catches up if the server was off.

### Installation

```sh
cd ~/calibrator
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env          # edit SECRET_KEY, ALLOWED_HOSTS, CSRF_TRUSTED_ORIGINS
.venv/bin/python manage.py migrate
.venv/bin/python manage.py collectstatic --noinput
.venv/bin/python manage.py createsuperuser
sudo cp deploy/calibrator.service deploy/calibrator-reminders.service deploy/calibrator-reminders.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now calibrator.service calibrator-reminders.timer
```

### Reverse proxy and HTTPS

Proxy to port 8000. Pass the `Host`, `X-Forwarded-Proto` and `X-Forwarded-For` headers, and allow uploads of at least 30 MB (nginx: `client_max_body_size 30m;`). In `.env`:

```
ALLOWED_HOSTS=calibrator.example.com,localhost
CSRF_TRUSTED_ORIGINS=https://calibrator.example.com
BEHIND_HTTPS_PROXY=1
```

Then run `sudo systemctl restart calibrator`, and set the same address as **Base URL** in Settings.

### Backups and restore

`deploy/backup.sh` copies the database safely while the app runs and archives the uploaded files into `~/calibrator-backups/<date-time>/`. It keeps the last 30. To schedule it, run `crontab -e` and add:

```
30 2 * * * /home/smolam/calibrator/deploy/backup.sh
```

To restore:

```sh
sudo systemctl stop calibrator
cp ~/calibrator-backups/<date-time>/db.sqlite3 ~/calibrator/data/db.sqlite3
tar -xzf ~/calibrator-backups/<date-time>/media.tar.gz -C ~/calibrator/data
sudo systemctl start calibrator
```

Copy the backups to another machine as well. A backup on the same disk doesn't protect against disk failure.

### Updating the application

```sh
cd ~/calibrator
deploy/backup.sh                               # always back up first
git pull                                       # or copy the new code
.venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py collectstatic --noinput
sudo systemctl restart calibrator
```

### Checks and troubleshooting

- **Logs**: `journalctl -u calibrator -f` for the app, and `journalctl -u calibrator-reminders` for reminder runs.
- **Timer status**: `systemctl list-timers calibrator-reminders.timer`.
- **Test reminders without sending**: `.venv/bin/python manage.py send_reminders --dry-run --date 01.12.2026`.
- **Run the test suite**: `.venv/bin/python manage.py test calibration`.
- **"Bad Request (400)"**: the address used isn't in `ALLOWED_HOSTS`.
- **"CSRF verification failed"**: add the HTTPS origin to `CSRF_TRUSTED_ORIGINS` and check that the proxy sends `X-Forwarded-Proto`.
- **Emails not arriving**: use **Send test email** in Settings and read the error. Check that **Notifications enabled** is on and that the users have email addresses.
- **Raw data**: superusers can inspect and fix records at `/django-admin/`. Prefer the normal pages, because changes there skip the audit log and date recalculation.
