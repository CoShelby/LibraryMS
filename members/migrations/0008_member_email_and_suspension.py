from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('members', '0007_member_is_printed'),
    ]

    operations = [
        migrations.AddField(
            model_name='member',
            name='email',
            field=models.EmailField(blank=True, db_index=True, max_length=254, null=True),
        ),
        migrations.AddField(
            model_name='member',
            name='is_suspended',
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AddField(
            model_name='member',
            name='suspension_reason',
            field=models.CharField(blank=True, default='', max_length=255),
        ),
    ]
