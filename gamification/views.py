from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import F
from django.shortcuts import render
from .models import Badge, Achievement, UserProgress, Streak
from .serializers import BadgeSerializer, AchievementSerializer, UserProgressSerializer, StreakSerializer, LeaderboardSerializer

class BadgeListView(generics.ListAPIView):
    queryset = Badge.objects.all()
    serializer_class = BadgeSerializer
    permission_classes = [IsAuthenticated]

class AchievementListView(generics.ListAPIView):
    serializer_class = AchievementSerializer
    permission_classes = [IsAuthenticated]

    def get(self, request):
        achievements = Achievement.objects.filter(user=request.user).select_related('badge')
        return render(request, 'achievements.html', {'achievements': achievements})

class UserProgressView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        progress = UserProgress.objects.filter(user=request.user)
        serializer = UserProgressSerializer(progress, many=True)
        return Response(serializer.data)

class StreakView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        streak, created = Streak.objects.get_or_create(user=request.user)
        serializer = StreakSerializer(streak)
        return Response(serializer.data)

class LeaderboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if request.path.startswith('/api/'):
            from django.shortcuts import redirect
            return redirect('/leaderboard/')
        # Get top 10 users by total_score from User model
        from accounts.models import User
        top_users = User.objects.order_by('-total_score')[:10]
        leaderboard_data = []
        for user in top_users:
            streak, _ = Streak.objects.get_or_create(user=user)
            leaderboard_data.append({
                'username': user.username,
                'total_score': user.total_score,
                'level': user.level,
                'xp': user.xp,
                'current_streak': streak.current_streak,
            })
        return Response(leaderboard_data)
