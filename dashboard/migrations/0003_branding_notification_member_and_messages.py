from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('dashboard', '0002_alter_notification_notification_type'),
        ('members', '0008_member_email_and_suspension'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='LibraryBranding',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(default='نظام إدارة المكتبة', max_length=255)),
                ('tagline', models.CharField(blank=True, default='', max_length=255)),
                ('logo', models.ImageField(blank=True, null=True, upload_to='branding/')),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.AddField(
            model_name='notification',
            name='member',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='members.member'),
        ),
        migrations.CreateModel(
            name='MemberMessageLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('message_type', models.CharField(choices=[('overdue', 'Overdue books'), ('reservation_approved', 'Reservation approved'), ('book_available', 'Book available'), ('pending_fines', 'Pending fines'), ('suspension_warning', 'Suspension warning'), ('general', 'General')], db_index=True, max_length=40)),
                ('channel', models.CharField(choices=[('email', 'Email'), ('sms', 'SMS')], db_index=True, max_length=16)),
                ('recipient', models.CharField(max_length=255)),
                ('subject', models.CharField(blank=True, default='', max_length=255)),
                ('body', models.TextField()),
                ('status', models.CharField(choices=[('sent', 'Sent'), ('failed', 'Failed'), ('prepared', 'Prepared')], db_index=True, default='prepared', max_length=16)),
                ('error_message', models.TextField(blank=True, default='')),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('member', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='message_logs', to='members.member')),
                ('notification', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='dashboard.notification')),
                ('sent_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='sent_member_messages', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-created_at', '-id'],
            },
        ),
    ]

