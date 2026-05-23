import os
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

class Command(BaseCommand):
    help = 'Creates a superuser if it does not exist using environment variables'

    def handle(self, *args, **options):
        User = get_user_model()
        username = os.environ.get('DJANGO_SUPERUSER_USERNAME', 'admin')
        email = os.environ.get('DJANGO_SUPERUSER_EMAIL', 'admin@example.com')
        password = os.environ.get('DJANGO_SUPERUSER_PASSWORD', 'admin12345')

        if not User.objects.filter(username=username).exists():
            user = User.objects.create_superuser(username, email, password)
            user.is_admin = True
            user.can_manage_admins = True
            user.can_manage_books = True
            user.can_manage_members = True
            user.can_manage_circulation = True
            user.can_manage_categories = True
            user.save()
            self.stdout.write(self.style.SUCCESS(f'Successfully created superuser "{username}"'))
        else:
            self.stdout.write(self.style.WARNING(f'Superuser "{username}" already exists.'))
