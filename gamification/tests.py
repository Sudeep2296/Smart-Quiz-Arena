from django.test import TestCase
from accounts.models import User
from .models import UserProgress, Streak
from .serializers import LeaderboardSerializer
from .views import LeaderboardView
from rest_framework.test import APIRequestFactory
from rest_framework import status
from django.urls import reverse
from rest_framework.test import APITestCase


class UserProgressTestCase(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(username='user1', password='pass')
        self.user2 = User.objects.create_user(username='user2', password='pass')
        self.progress1 = UserProgress.objects.create(user=self.user1, total_score=100, quizzes_completed=5, xp=500, level=2)
        self.progress2 = UserProgress.objects.create(user=self.user2, total_score=200, quizzes_completed=10, xp=1000, level=3)
        self.streak1 = Streak.objects.create(user=self.user1, current_streak=5, longest_streak=7)
        self.streak2 = Streak.objects.create(user=self.user2, current_streak=3, longest_streak=5)

    def test_user_progress_creation(self):
        self.assertEqual(self.progress1.total_score, 100)
        self.assertEqual(self.progress1.level, 2)

    def test_streak_creation(self):
        self.assertEqual(self.streak1.current_streak, 5)


class LeaderboardSerializerTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='pass')
        self.progress = UserProgress.objects.create(user=self.user, total_score=150, quizzes_completed=7, xp=750, level=2)
        self.streak = Streak.objects.create(user=self.user, current_streak=4, longest_streak=6)

    def test_serializer_data(self):
        serializer = LeaderboardSerializer(self.progress)
        data = serializer.data
        self.assertEqual(data['username'], 'testuser')
        self.assertEqual(data['total_score'], 150)
        self.assertEqual(data['level'], 2)
        self.assertEqual(data['xp'], 750)
        self.assertEqual(data['current_streak'], 4)


class LeaderboardViewTestCase(APITestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(username='user1', password='pass')
        self.user2 = User.objects.create_user(username='user2', password='pass')
        self.progress1 = UserProgress.objects.create(user=self.user1, total_score=100, quizzes_completed=5, xp=500, level=2)
        self.progress2 = UserProgress.objects.create(user=self.user2, total_score=200, quizzes_completed=10, xp=1000, level=3)
        self.streak1 = Streak.objects.create(user=self.user1, current_streak=5, longest_streak=7)
        self.streak2 = Streak.objects.create(user=self.user2, current_streak=3, longest_streak=5)

    def test_leaderboard_view(self):
        url = reverse('leaderboard')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data), 2)
        # Check ordering by total_score descending
        self.assertEqual(data[0]['username'], 'user2')
        self.assertEqual(data[0]['total_score'], 200)
        self.assertEqual(data[1]['username'], 'user1')
        self.assertEqual(data[1]['total_score'], 100)
