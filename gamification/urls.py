from django.urls import path
from . import views

urlpatterns = [
    path('badges/', views.BadgeListView.as_view(), name='badge-list'),
    path('achievements/', views.AchievementListView.as_view(), name='achievement-list'),
    path('progress/', views.UserProgressView.as_view(), name='user-progress'),
    path('streaks/', views.StreakView.as_view(), name='streak'),
    path('leaderboard/', views.LeaderboardView.as_view(), name='api_leaderboard'),
]
