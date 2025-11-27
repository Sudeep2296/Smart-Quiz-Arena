from django.core.management.base import BaseCommand
from gamification.models import Badge

class Command(BaseCommand):
    help = 'Populate the database with sample badges'

    def handle(self, *args, **options):
        badges_data = [
            {
                'name': 'First Steps',
                'description': 'Complete your first quiz',
                'criteria': {'quizzes_completed': 1}
            },
            {
                'name': 'Quiz Novice',
                'description': 'Complete 5 quizzes',
                'criteria': {'quizzes_completed': 5}
            },
            {
                'name': 'Quiz Master',
                'description': 'Complete 10 quizzes',
                'criteria': {'quizzes_completed': 10}
            },
            {
                'name': 'Perfect Score',
                'description': 'Score 100% on a quiz',
                'criteria': {'perfect_score': True}
            },
            {
                'name': 'High Scorer',
                'description': 'Score 90% or higher on a quiz',
                'criteria': {'high_score': True}
            },
            {
                'name': 'Streak Starter',
                'description': 'Maintain a 3-day streak',
                'criteria': {'streak': 3}
            },
            {
                'name': 'Streak Master',
                'description': 'Maintain a 7-day streak',
                'criteria': {'streak': 7}
            },
            {
                'name': 'Level Up',
                'description': 'Reach level 5',
                'criteria': {'level': 5}
            },
            {
                'name': 'XP Collector',
                'description': 'Earn 500 XP',
                'criteria': {'xp': 500}
            },
            {
                'name': 'Code Warrior',
                'description': 'Complete your first code battle',
                'criteria': {'code_battles_completed': 1}
            }
        ]

        for badge_data in badges_data:
            badge, created = Badge.objects.get_or_create(
                name=badge_data['name'],
                defaults={
                    'description': badge_data['description'],
                    'criteria': badge_data['criteria']
                }
            )
            if created:
                self.stdout.write(self.style.SUCCESS(f'Created badge: {badge.name}'))
            else:
                self.stdout.write(f'Badge already exists: {badge.name}')

        self.stdout.write(self.style.SUCCESS('Badge population completed!'))
