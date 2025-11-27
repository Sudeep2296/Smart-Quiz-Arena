from django.db import models
from accounts.models import User

class Challenge(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField()
    problem_statement = models.TextField()
    test_cases = models.JSONField()  # Input/output pairs
    sample_io = models.TextField(blank=True, null=True)  # For frontend display
    language = models.CharField(max_length=50, default='python')  # Primary language
    reference_solution = models.TextField(blank=True, null=True)  # Server-side reference
    difficulty = models.CharField(max_length=20, choices=[
        ('easy', 'Easy'),
        ('medium', 'Medium'),
        ('hard', 'Hard'),
    ])
    time_limit = models.IntegerField(default=300)  # seconds (5 minutes)
    memory_limit = models.IntegerField(default=256)  # MB
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

class Submission(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    challenge = models.ForeignKey(Challenge, on_delete=models.CASCADE)
    code = models.TextField()
    language = models.CharField(max_length=50)
    status = models.CharField(max_length=20, choices=[
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('accepted', 'Accepted'),
        ('wrong_answer', 'Wrong Answer'),
        ('time_limit', 'Time Limit Exceeded'),
        ('memory_limit', 'Memory Limit Exceeded'),
        ('compilation_error', 'Compilation Error'),
    ], default='pending')
    execution_time = models.FloatField(blank=True, null=True)
    memory_used = models.IntegerField(blank=True, null=True)
    test_results = models.JSONField(blank=True, null=True)  # Per-test-case results
    submitted_at = models.DateTimeField(auto_now_add=True)
    judge0_token = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return f"{self.user.username} - {self.challenge.title}"

class Battle(models.Model):
    player1 = models.ForeignKey(User, on_delete=models.CASCADE, related_name='battles_as_player1')
    player2 = models.ForeignKey(User, on_delete=models.CASCADE, related_name='battles_as_player2', blank=True, null=True)
    challenges = models.ManyToManyField(Challenge, blank=True)  # Multiple challenges for the battle
    winner = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True, related_name='won_battles')
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    status = models.CharField(max_length=20, choices=[
        ('waiting', 'Waiting'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
    ], default='waiting')
    battle_code = models.CharField(max_length=6, unique=True, blank=True, null=True)
    scores = models.JSONField(blank=True, null=True)  # Store scores as dict {username: score}
    num_questions = models.IntegerField(default=5)  # Number of challenges in the battle
    level = models.CharField(max_length=20, choices=[
        ('easy', 'Easy'),
        ('medium', 'Medium'),
        ('hard', 'Hard'),
    ], default='medium')
    current_challenge_index = models.IntegerField(default=0)  # Track current challenge in battle
    player1_ready = models.BooleanField(default=False)
    player2_ready = models.BooleanField(default=False)
    question_winners = models.JSONField(blank=True, null=True)  # Track who solved each question first {challenge_index: username}

    def __str__(self):
        player2_name = self.player2.username if self.player2 else "Waiting"
        return f"{self.player1.username} vs {player2_name}"

    def save(self, *args, **kwargs):
        if not self.battle_code:
            import random
            import string
            # Generate a unique 6-character code
            while True:
                code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
                if not Battle.objects.filter(battle_code=code).exists():
                    self.battle_code = code
                    break
        super().save(*args, **kwargs)
