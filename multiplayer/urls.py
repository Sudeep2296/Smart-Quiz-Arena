from django.urls import path
from . import views

urlpatterns = [
    path('', views.multiplayer_home, name='home'),
    path('rooms/', views.RoomListCreateView.as_view(), name='room-list'),
    path('rooms/<int:pk>/join/', views.JoinRoomView.as_view(), name='join-room'),
    path('join-by-code/', views.JoinByCodeView.as_view(), name='join-by-code'),
    path('toggle-ready/', views.ToggleReadyView.as_view(), name='toggle-ready'),
    path('start-game/', views.StartGameView.as_view(), name='start-game'),
    path('leave/', views.LeaveRoomView.as_view(), name='leave-room'),
]
