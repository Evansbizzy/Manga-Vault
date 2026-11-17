from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('core', '0004_readingprogress'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='manga',
            name='unique_manga_source_id',
        ),
        migrations.AddField(
            model_name='manga',
            name='owner',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='manga_library',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddConstraint(
            model_name='manga',
            constraint=models.UniqueConstraint(
                fields=('owner', 'source', 'source_id'),
                name='unique_owner_manga_source_id',
            ),
        ),
    ]
