# Generated manually for GeoGuessr-style multiplayer quiz

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('multiplayer', '0004_player_is_muted_player_webrtc_answer_and_more'),
    ]

    operations = [
        # Add round_start_time to Room model
        migrations.AddField(
            model_name='room',
            name='round_start_time',
            field=models.DateTimeField(blank=True, null=True),
        ),
        # Add round_state to Room model
        migrations.AddField(
            model_name='room',
            name='round_state',
            field=models.CharField(
                choices=[
                    ('waiting', 'Waiting'),
                    ('active', 'Active'),
                    ('review', 'Review'),
                    ('complete', 'Complete')
                ],
                default='waiting',
                max_length=20
            ),
        ),
        # Rename webrtc_answer to current_answer in Player model
        migrations.RenameField(
            model_name='player',
            old_name='webrtc_answer',
            new_name='current_answer',
        ),
        # Add answer_timestamp to Player model
        migrations.AddField(
            model_name='player',
            name='answer_timestamp',
            field=models.DateTimeField(blank=True, null=True),
        ),
        # Add answer_time_used to Player model
        migrations.AddField(
            model_name='player',
            name='answer_time_used',
            field=models.IntegerField(default=0),
        ),
    ]
