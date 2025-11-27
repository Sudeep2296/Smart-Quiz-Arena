from django.db import models
from django.contrib.auth import get_user_model
from accounts.models import User

class Topic(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name

class Quiz(models.Model):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)
    difficulty = models.CharField(max_length=20, choices=[
        ('easy', 'Easy'),
        ('medium', 'Medium'),
        ('hard', 'Hard'),
    ], default='medium')
    time_limit = models.IntegerField(default=30)  # in minutes

    def __str__(self):
        return self.title

class Question(models.Model):
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE, related_name='questions')
    question_text = models.TextField()
    question_type = models.CharField(max_length=20, choices=[
        ('multiple_choice', 'Multiple Choice'),
        ('true_false', 'True/False'),
        ('short_answer', 'Short Answer'),
    ])
    correct_answer = models.TextField()
    options = models.JSONField(blank=True, null=True)  # For multiple choice
    points = models.IntegerField(default=1)
    is_ai_generated = models.BooleanField(default=False)  # To mark AI-generated questions

    def __str__(self):
        return self.question_text[:50]

class Answer(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='answers')
    answer_text = models.TextField()
    is_correct = models.BooleanField()
    submitted_at = models.DateTimeField(auto_now_add=True)

class GameSession(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    quiz = models.ForeignKey(Quiz, on_delete=models.CASCADE)
    score = models.IntegerField(default=0)
    total_questions = models.IntegerField(default=0)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    mode = models.CharField(max_length=20, choices=[
        ('single', 'Single Player'),
        ('multiplayer', 'Multiplayer'),
    ])
    user_answers = models.JSONField(default=dict, blank=True)  # Store user's selected answers

    def __str__(self):
        return f"{self.user.username} - {self.quiz.title}"

class QuizSession(models.Model):
    session_type = models.CharField(max_length=20, choices=[('single', 'Single'), ('multiplayer', 'Multiplayer')], default='single')
    max_players = models.IntegerField(default=1)
    time_limit = models.IntegerField(default=15)
    difficulty_level = models.CharField(max_length=20, default='mixed')
    created_at = models.DateTimeField(auto_now_add=True)
    current_question_index = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    
    def next_question(self):
        # Get the next question based on current_question_index
        sq = self.sessionquestion_set.filter(order=self.current_question_index).first()
        if sq:
            return sq.question
        return None

    def get_current_question(self):
        sq = self.sessionquestion_set.filter(order=self.current_question_index).first()
        if sq:
            return sq.question
        return None

    def end_session(self):
        self.is_active = False
        self.save()

class PlayerScore(models.Model):
    player = models.ForeignKey(User, on_delete=models.CASCADE)
    session = models.ForeignKey(QuizSession, on_delete=models.CASCADE)
    score = models.IntegerField(default=0)
    correct_answers = models.IntegerField(default=0)
    total_answers = models.IntegerField(default=0)
    
    @property
    def accuracy(self):
        if self.total_answers == 0:
            return 0
        return (self.correct_answers / self.total_answers) * 100

class SessionQuestion(models.Model):
    session = models.ForeignKey(QuizSession, on_delete=models.CASCADE)
    question = models.ForeignKey(Question, on_delete=models.CASCADE)
    order = models.IntegerField()
