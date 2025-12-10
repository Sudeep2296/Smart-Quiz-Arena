from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.contrib.auth import authenticate, logout, login
from django.contrib.auth.views import LogoutView
from django.shortcuts import redirect, render
from django.contrib import messages
from rest_framework_simplejwt.tokens import RefreshToken
from django.templatetags.static import static
from .models import User
from .serializers import UserSerializer, RegisterSerializer, LoginSerializer
from rest_framework.renderers import TemplateHTMLRenderer
from rest_framework.response import Response

class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = (AllowAny,)
    serializer_class = RegisterSerializer

    def get(self, request, *args, **kwargs):
        return render(request, 'accounts/register.html')

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            login(request, user)
            messages.success(request, 'Registration successful!')
            return redirect('home')
        return render(request, 'accounts/register.html', {'errors': serializer.errors})

class LoginView(generics.GenericAPIView):
    permission_classes = (AllowAny,)
    serializer_class = LoginSerializer

    def get(self, request, *args, **kwargs):
        return render(request, 'accounts/login.html')

    def post(self, request, *args, **kwargs):
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(username=username, password=password)
        if user:
            login(request, user)
            messages.success(request, 'Login successful!')
            return redirect('home')
        messages.error(request, 'Invalid credentials')
        return render(request, 'accounts/login.html')

class CustomLogoutView(LogoutView):
    http_method_names = ['get', 'post']

    def get(self, request, *args, **kwargs):
        logout(request)
        messages.info(request, 'You have been logged out.')
        return redirect('home')

def profile_page(request):
    """HTML profile page view"""
    from gamification.models import Achievement, Streak
    from quizzes.models import GameSession
    from codebattle.models import Battle
    from django.db.models import Q
    
    if not request.user.is_authenticated:
        return redirect('login')
    
    user = request.user
    
    achievements = Achievement.objects.filter(user=user).select_related('badge').order_by('-earned_at')
    
    xp_per_level = 100
    progress_percentage = min((user.xp % xp_per_level) * 100 / xp_per_level, 100)
    remaining_percentage = 100 - progress_percentage
    xp_to_next_level = xp_per_level - (user.xp % xp_per_level)
    
    streak_obj, _ = Streak.objects.get_or_create(user=user)
    streak = streak_obj.current_streak
    
    recent_sessions = GameSession.objects.filter(
        user=user, completed_at__isnull=False
    ).select_related('quiz', 'quiz__topic').order_by('-completed_at')[:10]
    
    for session in recent_sessions:
        session.percentage = round((session.score / session.total_questions * 100)) if session.total_questions > 0 else 0
    
    total_quizzes = recent_sessions.count()
    total_answers = sum(s.total_questions for s in recent_sessions)
    correct_answers = sum(s.score for s in recent_sessions)
    accuracy = round((correct_answers / total_answers * 100)) if total_answers else 0
    
    code_battles = Battle.objects.filter(
        Q(player1=user) | Q(player2=user),
        status='completed'
    ).count()
    
    multiplayer_games = GameSession.objects.filter(
        user=user,
        mode="multiplayer",
        completed_at__isnull=False
    ).count()
    
    global_rank = User.objects.filter(total_score__gt=user.total_score).count() + 1
    total_users = User.objects.count()
    
    return render(request, 'accounts/profile.html', {
        'user': user,
        'achievements': achievements,
        'progress_percentage': progress_percentage,
        'remaining_percentage': remaining_percentage,
        'xp_to_next_level': xp_to_next_level,
        'streak': streak,
        'recent_sessions': recent_sessions,
        'total_quizzes': total_quizzes,
        'accuracy': accuracy,
        'code_battles': code_battles,
        'multiplayer_games': multiplayer_games,
        'global_rank': global_rank,
        'total_users': total_users,
    })


class ProfileView(generics.RetrieveUpdateAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = UserSerializer
    renderer_classes = [TemplateHTMLRenderer]  # <-- IMPORTANT

    def get(self, request, *args, **kwargs):
        from gamification.models import Achievement, Streak
        from quizzes.models import GameSession
        from codebattle.models import Battle
        from django.db.models import Q

        user = request.user

        achievements = Achievement.objects.filter(user=user).order_by('-earned_at')

        xp_per_level = 100
        progress_percentage = min((user.xp % xp_per_level) * 100 / xp_per_level, 100)
        remaining_percentage = 100 - progress_percentage
        xp_to_next_level = xp_per_level - (user.xp % xp_per_level)

        streak_obj, _ = Streak.objects.get_or_create(user=user)
        streak = streak_obj.current_streak

        recent_sessions = GameSession.objects.filter(
            user=user, completed_at__isnull=False
        ).select_related('quiz', 'quiz__topic').order_by('-completed_at')[:10]

        for session in recent_sessions:
            session.percentage = round((session.score / session.total_questions * 100)) if session.total_questions > 0 else 0

        total_quizzes = recent_sessions.count()
        total_answers = sum(s.total_questions for s in recent_sessions)
        correct_answers = sum(s.score for s in recent_sessions)
        accuracy = round((correct_answers / total_answers * 100)) if total_answers else 0

        code_battles = Battle.objects.filter(
            Q(player1=user) | Q(player2=user),
            status='completed'
        ).count()

        multiplayer_games = GameSession.objects.filter(
            user=user,
            mode="multiplayer",
            completed_at__isnull=False
        ).count()

        global_rank = User.objects.filter(total_score__gt=user.total_score).count() + 1
        total_users = User.objects.count()

        return Response(
            {
                "user": user,
                "achievements": achievements,
                "progress_percentage": progress_percentage,
                "remaining_percentage": remaining_percentage,
                "xp_to_next_level": xp_to_next_level,
                "streak": streak,
                "recent_sessions": recent_sessions,
                "total_quizzes": total_quizzes,
                "accuracy": accuracy,
                "code_battles": code_battles,
                "multiplayer_games": multiplayer_games,
                "global_rank": global_rank,
                "total_users": total_users,
            },
            template_name="accounts/profile.html" 
        )