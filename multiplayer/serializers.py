from rest_framework import serializers
from .models import Room, Player

class PlayerSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='user.username', read_only=True)
    is_host = serializers.SerializerMethodField()
    is_ready = serializers.BooleanField(read_only=True)

    def get_is_host(self, obj):
        return obj.room.host_id == obj.user_id

    class Meta:
        model = Player
        fields = ['username', 'is_host', 'is_ready']

class RoomSerializer(serializers.ModelSerializer):
    host = serializers.StringRelatedField()
    players = PlayerSerializer(many=True, read_only=True, source='player_set')
    topic_name = serializers.CharField(source='topic.name', read_only=True)
    can_start = serializers.SerializerMethodField()
    game_started = serializers.SerializerMethodField()

    def get_can_start(self, obj):
        """Room can start if host is current user, has at least 2 players, and game hasn't started"""
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        player_count = obj.player_set.count()
        is_host = obj.host_id == request.user.id
        has_started = obj.started_at is not None
        return is_host and player_count >= 2 and not has_started

    def get_game_started(self, obj):
        """Check if game has started"""
        return obj.started_at is not None

    class Meta:
        model = Room
        fields = ['id', 'name', 'room_code', 'quiz', 'topic', 'topic_name', 'num_questions', 'level', 'host', 'max_players', 'is_active', 'created_at', 'started_at', 'players', 'can_start', 'game_started']
