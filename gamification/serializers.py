from rest_framework import serializers
from .models import Badge, Achievement, UserProgress, Streak

class BadgeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Badge
        fields = '__all__'

class AchievementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Achievement
        fields = '__all__'

class UserProgressSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserProgress
        fields = '__all__'

class LeaderboardSerializer(serializers.Serializer):
    username = serializers.CharField()
    total_score = serializers.IntegerField()
    level = serializers.IntegerField()
    xp = serializers.IntegerField()
    current_streak = serializers.IntegerField()

class StreakSerializer(serializers.ModelSerializer):
    class Meta:
        model = Streak
        fields = '__all__'
