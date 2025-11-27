from django.db import models
from accounts.models import User
from datetime import timedelta

class Badge(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField()
    icon = models.ImageField(upload_to='badges/', blank=True, null=True)
    criteria = models.JSONField()  # e.g., {"quizzes_completed": 10}

    def __str__(self):
        return self.name

class Achievement(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    badge = models.ForeignKey(Badge, on_delete=models.CASCADE)
    earned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'badge')

class Streak(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    current_streak = models.IntegerField(default=0)
    longest_streak = models.IntegerField(default=0)
    last_activity = models.DateField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - Streak: {self.current_streak}"

class UserProgress(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    quizzes_completed = models.IntegerField(default=0)
    total_score = models.IntegerField(default=0)
    average_score = models.FloatField(default=0.0)
    time_spent = models.DurationField(default=timedelta(0))
    level = models.IntegerField(default=0)
    xp = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.user.username} Progress"
