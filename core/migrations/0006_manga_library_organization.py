from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('core', '0005_manga_owner'),
    ]

    operations = [
        migrations.AddField(
            model_name='manga',
            name='library_status',
            field=models.CharField(
                choices=[
                    ('unread', 'Unread'),
                    ('reading', 'Reading'),
                    ('completed', 'Completed'),
                    ('paused', 'Paused'),
                    ('dropped', 'Dropped'),
                ],
                default='unread',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='manga',
            name='tags',
            field=models.JSONField(blank=True, default=list),
        ),
    ]
