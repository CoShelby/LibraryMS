from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('circulations', '0005_borrowing_datetime_precision'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='borrowing',
            name='created_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_borrowings', to=settings.AUTH_USER_MODEL),
        ),
        migrations.CreateModel(
            name='FinePayment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_fine_payments', to=settings.AUTH_USER_MODEL)),
                ('fine', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='payment', to='circulations.fine')),
            ],
        ),
    ]