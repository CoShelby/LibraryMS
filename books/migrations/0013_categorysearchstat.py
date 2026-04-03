from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('books', '0012_book_created_by'),
    ]

    operations = [
        migrations.CreateModel(
            name='CategorySearchStat',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('search_count', models.PositiveIntegerField(default=0)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('category', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='search_stat', to='books.category')),
            ],
            options={
                'verbose_name': 'Category Search Stat',
                'verbose_name_plural': 'Category Search Stats',
            },
        ),
    ]
