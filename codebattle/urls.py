from django.urls import path
from . import views

urlpatterns = [
    path('', views.code_battle_home, name='code_battle'),
    path('editor/', views.code_editor, name='code-editor'),
    path('room/<str:battle_code>/', views.code_battle_room, name='code-battle-room'),
    path('join-by-code/', views.join_by_code, name='join-by-code'),
    path('challenges/', views.ChallengeListView.as_view(), name='challenge-list'),
    path('challenges/<int:pk>/', views.ChallengeDetailView.as_view(), name='challenge-detail'),
    path('battles/', views.BattleListCreateView.as_view(), name='battle-list'),
    path('battles/<int:pk>/join/', views.JoinBattleView.as_view(), name='join-battle'),
    path('battles/create/', views.CreateBattleView.as_view(), name='create-battle'),
    path('submissions/', views.SubmissionCreateView.as_view(), name='submission-create'),
    path('results/', views.battle_results, name='battle-results'),
]
