from datetime import datetime

from django.core.management.base import BaseCommand

from calibration.services import send_reminders


class Command(BaseCommand):
    help = "Send calibration reminder emails that are due today (safe to run repeatedly)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Print emails instead of sending them.")
        parser.add_argument("--date", help="Pretend today is this date (DD.MM.YYYY), for testing.")

    def handle(self, *args, dry_run=False, date=None, **options):
        today = datetime.strptime(date, "%d.%m.%Y").date() if date else None
        sent = send_reminders(today=today, dry_run=dry_run)
        verb = "Would send" if dry_run else "Sent"
        for email, n in sent:
            self.stdout.write(f"{verb} reminder to {email} ({n} device(s))")
        self.stdout.write(self.style.SUCCESS(f"{verb} {len(sent)} email(s)."))
