from rest_framework import serializers
from .models import Challenge, Battle, Submission

class ChallengeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Challenge
        fields = '__all__'

class BattleSerializer(serializers.ModelSerializer):
    player1 = serializers.StringRelatedField()
    player2 = serializers.StringRelatedField()
    scores = serializers.JSONField()
    challenges = serializers.StringRelatedField(many=True)

    class Meta:
        model = Battle
        fields = '__all__'

class SubmissionSerializer(serializers.ModelSerializer):
    challenge_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = Submission
        fields = '__all__'

    def create(self, validated_data):
        challenge_id = validated_data.pop('challenge_id')
        validated_data['challenge'] = Challenge.objects.get(id=challenge_id)
        return super().create(validated_data)
