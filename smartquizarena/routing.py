from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/quiz/$', consumers.QuizConsumer.as_asgi()),
    re_path(r'ws/coding-battle/$', consumers.CodingBattleConsumer.as_asgi()),
]
