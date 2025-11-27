"""
ASGI config for smartquizarena project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os

import django
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from django.core.asgi import get_asgi_application

os.environ['DJANGO_SETTINGS_MODULE'] = 'smartquizarena.settings'
django.setup()

import multiplayer.routing
import codebattle.routing
import smartquizarena.routing

application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": AuthMiddlewareStack(
        URLRouter(
            multiplayer.routing.websocket_urlpatterns +
            codebattle.routing.websocket_urlpatterns +
            smartquizarena.routing.websocket_urlpatterns
        )
    ),
})
