from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'^ws/multiplayer/(?P<room_code>\w+)/$', consumers.QuizRoomConsumer.as_asgi()),
]
