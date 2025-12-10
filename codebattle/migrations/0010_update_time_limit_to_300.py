# Generated migration to update time_limit to 300 seconds
from django.db import migrations, models


def update_time_limits(apps, schema_editor):
    """Update all existing challenges to 300 seconds"""
    Challenge = apps.get_model('codebattle', 'Challenge')
    Challenge.objects.all().update(time_limit=300)


def reverse_time_limits(apps, schema_editor):
    """Reverse migration - set back to 120 seconds"""
    Challenge = apps.get_model('codebattle', 'Challenge')
    Challenge.objects.all().update(time_limit=120)


class Migration(migrations.Migration):

    dependencies = [
        ('codebattle', '0009_update_challenge_time_limit'),
    ]

    operations = [
        migrations.AlterField(
            model_name='challenge',
            name='time_limit',
            field=models.IntegerField(default=300),
        ),
        migrations.RunPython(
            code=update_time_limits,
            reverse_code=reverse_time_limits,
        ),
    ]
