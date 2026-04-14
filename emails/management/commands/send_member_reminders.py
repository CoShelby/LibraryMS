from django.core.management.base import BaseCommand

from emails.member_messages import sync_automatic_member_messages


class Command(BaseCommand):
    help = "Send automatic member reminder emails."

    def handle(self, *args, **options):
        sent_count = sync_automatic_member_messages()
        self.stdout.write(self.style.SUCCESS(f"Sent {sent_count} reminder email(s)."))