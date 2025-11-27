from django.test import TestCase
from accounts.models import User
from .models import Room, Player
from gamification.models import UserProgress, Streak
from channels.testing import WebsocketCommunicator
from .consumers import GeoGuessrQuizConsumer
from asgiref.sync import sync_to_async
from django.test import TransactionTestCase
from channels.layers import get_channel_layer
import json


class GeoGuessrQuizConsumerTestCase(TransactionTestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(username='user1', password='pass')
        self.user2 = User.objects.create_user(username='user2', password='pass')
        self.room = Room.objects.create(
            room_code='TEST123',
            host=self.user1,
            quiz_state='finished'
        )
        self.player1 = Player.objects.create(
            user=self.user1,
            room=self.room,
            score=40
        )
        self.player2 = Player.objects.create(
            user=self.user2,
            room=self.room,
            score=60
        )
        self.progress1 = UserProgress.objects.create(user=self.user1, total_score=0, quizzes_completed=0, xp=0, level=1)
        self.progress2 = UserProgress.objects.create(user=self.user2, total_score=0, quizzes_completed=0, xp=0, level=1)
        self.streak1 = Streak.objects.create(user=self.user1, current_streak=0, longest_streak=0)
        self.streak2 = Streak.objects.create(user=self.user2, current_streak=0, longest_streak=0)

    async def test_update_user_progress_and_streak(self):
        # Test the update methods directly
        consumer = GeoGuessrQuizConsumer()

        # Update progress for user1
        await consumer.update_user_progress(self.user1.id, 40)
        await consumer.update_streak(self.user1.id)

        # Update progress for user2
        await consumer.update_user_progress(self.user2.id, 60)
        await consumer.update_streak(self.user2.id)

        # Refresh from database
        progress1 = await sync_to_async(UserProgress.objects.get)(user=self.user1)
        progress2 = await sync_to_async(UserProgress.objects.get)(user=self.user2)
        streak1 = await sync_to_async(Streak.objects.get)(user=self.user1)
        streak2 = await sync_to_async(Streak.objects.get)(user=self.user2)

        # Check progress updates
        self.assertEqual(progress1.total_score, 40)
        self.assertEqual(progress1.quizzes_completed, 1)
        self.assertEqual(progress1.xp, 400)
        self.assertEqual(progress1.level, 1)  # 40 // 100 + 1 = 1

        self.assertEqual(progress2.total_score, 60)
        self.assertEqual(progress2.quizzes_completed, 1)
        self.assertEqual(progress2.xp, 600)
        self.assertEqual(progress2.level, 1)  # 60 // 100 + 1 = 1

        # Check streak updates
        self.assertEqual(streak1.current_streak, 1)
        self.assertEqual(streak1.longest_streak, 1)

        self.assertEqual(streak2.current_streak, 1)
        self.assertEqual(streak2.longest_streak, 1)
