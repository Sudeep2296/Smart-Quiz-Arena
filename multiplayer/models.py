from django.db import models
from accounts.models import User
from quizzes.models import Quiz
from quizzes.models import Topic
import secrets
import string

class Room(models.Model):
    name = models.CharField(max_length=100)
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, null=True, blank=True)  # Optional, can be created dynamically
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, null=True, blank=True)
    num_questions = models.IntegerField(default=10)
    level = models.CharField(max_length=20, choices=[
        ('easy', 'Easy'),
        ('medium', 'Medium'),
        ('hard', 'Hard'),
    ], default='medium')
    room_code = models.CharField(max_length=6, unique=True, blank=True)
    host = models.ForeignKey(User, on_delete=models.CASCADE)
    max_players = models.IntegerField(default=10)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(blank=True, null=True)
    current_question = models.IntegerField(default=0)
    answered_count = models.IntegerField(default=0)
    quiz_state = models.CharField(
        max_length=20,
        default='not_started',
        choices=[
            ('not_started', 'Not Started'),
            ('active', 'Active'),
            ('finished', 'Finished')
        ]
    )
    timer_duration = models.IntegerField(default=20)  # Default 20 seconds per question
    round_start_time = models.DateTimeField(blank=True, null=True)  # When current round started
    round_state = models.CharField(
        max_length=20,
        default='waiting',
        choices=[
            ('waiting', 'Waiting'),
            ('active', 'Active'),
            ('review', 'Review'),
            ('complete', 'Complete')
        ]
    )

    def save(self, *args, **kwargs):
        if not self.room_code:
            self.room_code = self.generate_room_code()
        super().save(*args, **kwargs)

    def generate_room_code(self):
        """Generate a unique 6-character room code"""
        while True:
            code = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(6))
            if not Room.objects.filter(room_code=code, is_active=True).exists():
                return code

    def __str__(self):
        return self.name

class Player(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    room = models.ForeignKey(Room, on_delete=models.CASCADE)
    score = models.IntegerField(default=0)
    joined_at = models.DateTimeField(auto_now_add=True)
    is_ready = models.BooleanField(default=False)
    is_muted = models.BooleanField(default=False)
    current_answer = models.TextField(blank=True, null=True)  # Current round answer
    answer_timestamp = models.DateTimeField(blank=True, null=True)  # When they answered
    answer_time_used = models.IntegerField(default=0)  # Seconds used to answer

    class Meta:
        unique_together = ('user', 'room')

    def __str__(self):
        return f"{self.user.username} in {self.room.name}"
