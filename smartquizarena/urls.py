"""
URL configuration for smartquizarena project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.shortcuts import render

def home(request):
    from quizzes.models import Topic
    topics = Topic.objects.all()
    return render(request, 'home.html', {'topics': topics})

def leaderboard(request):
    from accounts.models import User
    from gamification.models import Streak
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
    return render(request, 'leaderboard.html', {'leaderboard': leaderboard_data})

def achievements(request):
    from gamification.views import AchievementListView
    view = AchievementListView()
    return view.get(request)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home, name='home'),
    path('leaderboard/', leaderboard, name='leaderboard'),
    path('accounts/', include('accounts.urls')),
    path('quizzes/', include('quizzes.urls')),
    path('gamification/', include(('gamification.urls', 'gamification'), namespace='gamification')),
    path('multiplayer/', include(('multiplayer.urls', 'multiplayer'), namespace='multiplayer')),
    path('codebattle/', include('codebattle.urls')),
    path('api/accounts/', include('accounts.urls')),
    path('api/quizzes/', include('quizzes.urls')),
    path('api/gamification/', include(('gamification.urls', 'gamification_api'), namespace='gamification_api')),
    path('api/multiplayer/', include(('multiplayer.urls', 'multiplayer_api'), namespace='multiplayer_api')),
    path('api/codebattle/', include('codebattle.urls')),
]
