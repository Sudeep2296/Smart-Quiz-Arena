# Generated manually for GeoGuessr-style multiplayer quiz

from django.db import migrations, models


def add_field_if_not_exists(apps, schema_editor):
    """Add fields only if they don't already exist"""
    from django.db import connection
    
    with connection.cursor() as cursor:
        # Check if round_state exists
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='multiplayer_room' AND column_name='round_state'
        """)
        if not cursor.fetchone():
            cursor.execute("""
                ALTER TABLE multiplayer_room 
                ADD COLUMN round_state VARCHAR(20) DEFAULT 'waiting' NOT NULL
            """)
        
        # Check if round_start_time exists
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='multiplayer_room' AND column_name='round_start_time'
        """)
        if not cursor.fetchone():
            cursor.execute("""
                ALTER TABLE multiplayer_room 
                ADD COLUMN round_start_time TIMESTAMP NULL
            """)
        
        # Check if answer_timestamp exists
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='multiplayer_player' AND column_name='answer_timestamp'
        """)
        if not cursor.fetchone():
            cursor.execute("""
                ALTER TABLE multiplayer_player 
                ADD COLUMN answer_timestamp TIMESTAMP NULL
            """)
        
        # Check if answer_time_used exists
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='multiplayer_player' AND column_name='answer_time_used'
        """)
        if not cursor.fetchone():
            cursor.execute("""
                ALTER TABLE multiplayer_player 
                ADD COLUMN answer_time_used INTEGER DEFAULT 0 NOT NULL
            """)
        
        # Rename webrtc_answer to current_answer if needed
        cursor.execute("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name='multiplayer_player' AND column_name='webrtc_answer'
        """)
        if cursor.fetchone():
            cursor.execute("""
                ALTER TABLE multiplayer_player 
                RENAME COLUMN webrtc_answer TO current_answer
            """)


class Migration(migrations.Migration):

    dependencies = [
        ('multiplayer', '0004_player_is_muted_player_webrtc_answer_and_more'),
    ]

    operations = [
        migrations.RunPython(add_field_if_not_exists, migrations.RunPython.noop),
    ]

