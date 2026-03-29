from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('circulations', '0006_borrowing_created_by_and_finepayment'),
    ]

    operations = [
        migrations.CreateModel(
            name='Notification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('notification_type', models.CharField(choices=[('overdue', 'استعارة متأخرة'), ('reservation_created', 'طلب حجز جديد'), ('reservation_available', 'كتاب محجوز أصبح متاحًا')], db_index=True, max_length=40)),
                ('title', models.CharField(max_length=255)),
                ('message', models.TextField()),
                ('is_read', models.BooleanField(db_index=True, default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('borrowing', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='circulations.borrowing')),
                ('reservation', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='circulations.reservation')),
            ],
            options={
                'ordering': ['-created_at', '-id'],
            },
        ),
    ]