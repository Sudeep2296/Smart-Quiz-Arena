"""
Script to update all existing Challenge time_limits to 300 seconds (5 minutes)
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smartquizarena.settings')
django.setup()

from codebattle.models import Challenge

# Update all challenges to have 300 second time limit (5 minutes)
updated_count = Challenge.objects.all().update(time_limit=300)
print(f"Updated {updated_count} challenge(s) to have time_limit=300 seconds")
