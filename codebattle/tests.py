from django.test import TestCase, TransactionTestCase
from accounts.models import User
from .models import Battle, Challenge, Submission
from gamification.models import UserProgress, Streak
from channels.testing import WebsocketCommunicator
from .consumers import CodeBattleConsumer
from asgiref.sync import sync_to_async
import json


class CodeBattleConsumerTestCase(TransactionTestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(username='user1', password='pass')
        self.user2 = User.objects.create_user(username='user2', password='pass')
        self.challenge = Challenge.objects.create(
            title='Test Challenge',
            description='Test Description',
            problem_statement='Test Problem',
            sample_io='Input: 1\nOutput: 1',
            difficulty='easy',
            time_limit=1.0
        )
        self.battle = Battle.objects.create(
            player1=self.user1,
            player2=self.user2,
            status='completed',
            scores={'user1': 50, 'user2': 70}
        )
        self.battle.challenges.add(self.challenge)
        self.progress1 = UserProgress.objects.create(user=self.user1, total_score=0, quizzes_completed=0, xp=0, level=1)
        self.progress2 = UserProgress.objects.create(user=self.user2, total_score=0, quizzes_completed=0, xp=0, level=1)
        self.streak1 = Streak.objects.create(user=self.user1, current_streak=0, longest_streak=0)
        self.streak2 = Streak.objects.create(user=self.user2, current_streak=0, longest_streak=0)

    async def test_end_battle_updates_progress_and_streak(self):
        # Simulate end battle event
        consumer = CodeBattleConsumer()
        consumer.battle_id = self.battle.id
        consumer.user = self.user1

        # Call the handle_end_battle method
        await consumer.handle_end_battle(self.user1, {})

        # Refresh from database
        progress1 = await sync_to_async(UserProgress.objects.get)(user=self.user1)
        progress2 = await sync_to_async(UserProgress.objects.get)(user=self.user2)
        streak1 = await sync_to_async(Streak.objects.get)(user=self.user1)
        streak2 = await sync_to_async(Streak.objects.get)(user=self.user2)

        # Check progress updates
        self.assertEqual(progress1.total_score, 50)
        self.assertEqual(progress1.quizzes_completed, 1)
        self.assertEqual(progress1.xp, 500)
        self.assertEqual(progress1.level, 1)  # 50 // 100 + 1 = 1

        self.assertEqual(progress2.total_score, 70)
        self.assertEqual(progress2.quizzes_completed, 1)
        self.assertEqual(progress2.xp, 700)
        self.assertEqual(progress2.level, 1)  # 70 // 100 + 1 = 1

        # Check streak updates
        self.assertEqual(streak1.current_streak, 1)
        self.assertEqual(streak1.longest_streak, 1)

        self.assertEqual(streak2.current_streak, 1)
        self.assertEqual(streak2.longest_streak, 1)
