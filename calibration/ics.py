"""Minimal RFC 5545 calendar feed of calibration due dates."""

from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from .models import Device


def _escape(text):
    return (
        str(text).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r\n", "\\n").replace("\n", "\\n")
    )


def _fold(line):
    """Fold content lines longer than 75 octets."""
    data = line.encode("utf-8")
    if len(data) <= 75:
        return line
    parts, current = [], b""
    for ch in line:
        b = ch.encode("utf-8")
        if len(current) + len(b) > (75 if not parts else 74):
            parts.append(current.decode("utf-8"))
            current = b""
        current += b
    parts.append(current.decode("utf-8"))
    return "\r\n ".join(parts)


def build_calendar(devices, base_url="", name="Calibrations"):
    stamp = timezone.now().strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Calibrator//Calibration due dates//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape(name)}",
        "REFRESH-INTERVAL;VALUE=DURATION:PT6H",
        "X-PUBLISHED-TTL:PT6H",
    ]
    base = base_url.rstrip("/")
    for d in devices:
        if not d.next_calibration_date or d.status not in Device.REMINDER_STATUSES:
            continue
        due = d.next_calibration_date
        desc = [
            f"Device: {d.asset_tag} {d.name}",
            f"Category: {d.category}",
            f"Owner: {d.owner}",
            f"Location: {d.location}" if d.location else "",
            f"Last calibration: {d.last_calibration_date:%d.%m.%Y}" if d.last_calibration_date else "",
        ]
        url = f"{base}{reverse('device_detail', args=[d.pk])}" if base else ""
        if url:
            desc.append(url)
        lines += [
            "BEGIN:VEVENT",
            f"UID:calibration-{d.pk}-{due:%Y%m%d}@calibrator",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{due:%Y%m%d}",
            f"DTEND;VALUE=DATE:{due + timedelta(days=1):%Y%m%d}",
            f"SUMMARY:{_escape(f'Calibration due: {d.asset_tag} {d.name}')}",
            f"DESCRIPTION:{_escape(chr(10).join(x for x in desc if x))}",
            "TRANSP:TRANSPARENT",
        ]
        if url:
            lines.append(f"URL:{url}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
