from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/codebattle/(?P<battle_code>[A-Z0-9]+)/$', consumers.CodeBattleConsumer.as_asgi()),
    re_path(r'ws/codebattle/$', consumers.CodeBattleConsumer.as_asgi()),
]
