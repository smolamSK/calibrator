# Calibrator – User manual

Calibrator keeps track of measuring devices and when they need to be calibrated. For every device it stores who owns it, its full calibration history with certificates, and when the next calibration is due. It also reminds people by email before a device falls due.

This manual is for everyone who uses the app. Editors and Administrators should also read the **Admin manual**.

## Signing in

Open the address your administrator gave you and log in with your **Username** and **Password**.

- **Forgot password?** on the login page sends a reset link to the email address on your account.
- After **5 failed attempts** your account is locked for **30 minutes** for the computer you are using. Wait, or ask an administrator to help.
- You stay logged in for up to 12 hours. Use **Log out** in the menu under your name when you are on a shared computer.
- To change your password, open **Profile & calendar** (menu under your name) → **Change password**.

## What you can see and do

Your role is set by an administrator.

| Role | Devices you see | Devices you can edit | Also |
|---|---|---|---|
| **Owner** | only your own | only your own | |
| **Viewer** | all devices | only your own | |
| **Editor** | all devices | all devices | Brands & models, Import, Audit log, gets all reminders |
| **Administrator** | all devices | all devices | everything an Editor can do, plus Users, Settings and deleting devices |

"Your own" devices are those where you are the **Owner**.

## Dashboard

The start page shows what needs attention:

- **Overdue**: active devices whose next calibration date has passed.
- **Due soon**: devices due within the next few days. The number of days is set by the administrator, usually 30.
- **Never calibrated (no history)**: devices without any calibration recorded yet, so no due date can be calculated.
- **Currently at calibration**: devices with the status *At calibration*.
- **Devices in use**: the number of devices that are not retired.
- **Recent activity** (Viewers and above): the latest changes.

Click an Asset ID to open the device. **+ New device** creates one.

## Finding devices

**Devices** opens the device list. Above it you can filter by:

- **Search**: Asset ID, name, serial number, location, manufacturer, model, and the text of custom fields.
- **Status**: Active, At calibration, Out of service, Retired, or *In use (not retired)*.
- **Due date**: Overdue, Due soon, OK, Never calibrated.
- **Manufacturer** and **Model**: picking a manufacturer narrows the model list to its models.
- **Owner** (Viewers and above).

When you filter by a manufacturer or model, the list can show extra columns for that manufacturer's or model's custom fields. Which fields appear is chosen by an Editor.

**Export Excel** and **Export CSV** download the filtered list, including custom field values. **My devices** in the top menu lists the devices you own.

### Due badges

| Badge | Meaning |
|---|---|
| <span class="badge bg-danger">Overdue</span> | the next calibration date has passed |
| <span class="badge bg-warning text-dark">Due soon</span> | due within the "due soon" period |
| <span class="badge bg-success">OK</span> | not due for a while |
| <span class="badge bg-secondary">Never calibrated</span> | no calibration recorded yet |
| <span class="badge bg-body-tertiary text-body border">Inactive</span> | Retired or Out of service; these devices get no reminders |

## The device page

A device page has these sections:

- **Calibration**: last and next calibration date, the **Interval** in months, and the **Reminders** (days before the due date). The text after the interval tells you where it comes from:
  - *device override*: set on this device.
  - *from model* / *from manufacturer*: set on the device's model or manufacturer by an Editor.
  - *default*: the general default from Settings.
- **Details**: owner, status, manufacturer, model, serial number, location, notes and the custom fields of its manufacturer and model.
- **Calibration history**: every calibration recorded, newest first, with certificates.
- **Documents**: manuals, photos and other files. **Upload** adds a file (up to 25 MB).
- **Change log**: who changed what and when.

If you may edit the device, you see the buttons **Record calibration**, **Edit** and, for Administrators, **Delete**.

## Adding or editing a device

**+ New device** (or **Edit** on a device page) opens the form.

**General**

- **Asset ID**: your inventory number; it must be unique.
- **Name**: a short description, e.g. "Digital multimeter lab 2".
- **Owner**: the person responsible. Owners and Viewers can only create devices for themselves.
- **Status**:
  - *Active*: in normal use.
  - *At calibration*: away at the lab. Reminders continue.
  - *Out of service* / *Retired*: no reminders are sent.
- **Manufacturer** and **Model**: pick from the lists.
  - If the one you need is missing, click **+** next to the list and type the name. A model is always added under the selected manufacturer.
  - Choosing a model first fills in its manufacturer automatically.
- **Serial number**, **Location**, **Notes**: free text.
- **Interval override (months)**: the grey badge next to it shows the interval the device gets without an override, e.g. *Model default: 6 months*. It updates when you change the manufacturer or model. Fill the field in only if *this* device needs a different interval. Leave it empty in most cases.
- **Last calibration date** (only when creating a device): if the device was calibrated before you started using Calibrator, enter that date. It becomes the first history entry and the next due date is calculated from it.

**Manufacturer & model fields**

Manufacturers and models can have their own extra fields, for example *Measuring range* or *Probe type*. When you change the manufacturer or model, the form reloads to show the matching fields. Your other entries are kept, and nothing is saved until you click **Save**. Fields marked as required must be filled in.

## Recording a calibration

On the device page click **Record calibration** and fill in:

- **Calibration date**: the date on the certificate.
- **Performed**: *Internal* or *External lab*, plus **Performed by** (person or laboratory).
- **Result**: *Pass*, *Pass after adjustment*, *Limited use*, *Fail* or *Not recorded*.
- **Certificate number** and **Notes**.
- **Certificate / attachments**: upload the certificate PDF or photos. You can select several files at once, up to 25 MB each.

The latest calibration date becomes the device's *last calibration*. The *next calibration* is that date plus the interval. If the result is *Fail*, consider changing the device status to *Out of service*.

You can **edit** or **delete** history entries. The last and next dates are recalculated automatically.

## How the due date is calculated

**Next calibration = latest calibration date + interval (months).**

The interval is taken from the first of these that is set:

1. the device's **Interval override**,
2. its **model**,
3. its **manufacturer**,
4. the **default** in Settings.

If the target month is shorter, the date moves to the last day of that month. For example, 31 January + 1 month = 28 February.

## Reminder emails

Reminders are sent every morning at 07:00 to:

- the device **owner**, and
- all **Editors and Administrators**,

as one summary email per person per day.

- **Before the due date**: one email when each reminder threshold is reached. For example, with reminder days `30,7,0` you get one email 30 days before, one 7 days before and one on the due date.
- **After the due date**: repeated every few days (set by the administrator) until a new calibration is recorded.
- Devices that are *Retired* or *Out of service* never trigger reminders.

To stop receiving reminders, open **Profile & calendar** and untick **Email notifications**.

## Calendar subscription

**Profile & calendar → Calendar subscription** gives you a private link that shows every device's next calibration as an all-day event in Outlook, Google Calendar or Apple Calendar.

- **Copy** the link and add it to your calendar:
  - Outlook: *Add calendar → Subscribe from web*.
  - Google Calendar: *Other calendars → From URL*.
- Viewers and above get two links: all devices, or **Only devices you own**.
- The calendar refreshes by itself every few hours.
- Anyone with the link can see the events. If it leaks, click **Create new link**. The old link stops working.

## Appearance

- **Light / dark mode**: click the ◐ / ☀ / ☾ symbol in the top menu and choose **Light**, **Dark** or **Auto (follow system)**. Auto switches with your computer's or phone's dark-mode setting.
- **Accent color**: **Profile & calendar → Appearance** lets you pick Blue, Indigo, Teal, Green, Orange or Graphite. The color is used for the top bar, buttons and links.
- **Site default** uses the colors chosen by the administrator. Your choice is saved on your account, so it applies on every computer you use.

## Questions and problems

**I can't see a device.** Owners only see their own devices. Ask an Editor to change the owner, or ask an administrator for the Viewer role.

**The device has no due date.** No calibration has been recorded yet. Record one, or enter the *Last calibration date*.

**The due date is wrong.** Check the interval on the device page and where it comes from. Correct the override on the device, or ask an Editor to change it on the model or manufacturer.

**I don't get reminder emails.** Check that **Email notifications** is ticked and your email address is correct in **Profile & calendar**. Also check your spam folder. The administrator can send a test email from Settings.

**The form says a field is required that I don't know.** The field belongs to the device's manufacturer or model. Ask an Editor if it should really be required.

**I am locked out.** Wait 30 minutes or ask an administrator.
