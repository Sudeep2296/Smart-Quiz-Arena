from .models import Badge, Achievement, Streak
from accounts.models import User
from quizzes.models import GameSession
from codebattle.models import Submission
from django.db.models import Count, F
from django.contrib import messages

class AchievementService:
    @staticmethod
    def check_and_award_achievements(user):
        """
        Check all badges and award achievements if criteria are met
        """
        badges = Badge.objects.all()
        newly_awarded = []
        for badge in badges:
            if not Achievement.objects.filter(user=user, badge=badge).exists():
                if AchievementService._check_criteria(user, badge.criteria):
                    achievement = Achievement.objects.create(user=user, badge=badge)
                    newly_awarded.append(achievement)
        return newly_awarded

    @staticmethod
    def _check_criteria(user, criteria):
        """
        Check if user meets the badge criteria
        """
        if 'quizzes_completed' in criteria:
            completed_quizzes = GameSession.objects.filter(
                user=user,
                completed_at__isnull=False
            ).count()
            if completed_quizzes >= criteria['quizzes_completed']:
                return True

        if 'perfect_score' in criteria:
            # Check if user has any perfect score (100%)
            perfect_sessions = GameSession.objects.filter(
                user=user,
                completed_at__isnull=False
            ).filter(score=F('total_questions'))
            if perfect_sessions.exists():
                return True

        if 'high_score' in criteria:
            # Check if user has scored 90% or higher
            high_score_sessions = GameSession.objects.filter(
                user=user,
                completed_at__isnull=False
            ).filter(score__gte=F('total_questions') * 0.9)
            if high_score_sessions.exists():
                return True

        if 'streak' in criteria:
            streak, _ = Streak.objects.get_or_create(user=user)
            if streak.current_streak >= criteria['streak']:
                return True

        if 'level' in criteria:
            if user.level >= criteria['level']:
                return True

        if 'xp' in criteria:
            if user.xp >= criteria['xp']:
                return True

        if 'code_battles_completed' in criteria:
            completed_battles = Submission.objects.filter(
                user=user,
                status__icontains='passed'  # Assuming status contains success status
            ).count()
            if completed_battles >= criteria['code_battles_completed']:
                return True

        return False

    @staticmethod
    def award_achievement_on_quiz_completion(user, game_session, request=None):
        """
        Award achievements specifically after quiz completion
        """
        # Update user progress
        from .models import UserProgress
        from datetime import timedelta
        progress, created = UserProgress.objects.get_or_create(user=user)
        progress.quizzes_completed += 1
        progress.total_score += game_session.score
        session_duration = game_session.completed_at - game_session.started_at
        progress.time_spent += session_duration
        progress.average_score = (progress.total_score / progress.quizzes_completed) if progress.quizzes_completed > 0 else 0
        progress.save()

        # Check for achievements
        newly_awarded = AchievementService.check_and_award_achievements(user)

        # Add messages for newly awarded achievements
        if request and newly_awarded:
            for achievement in newly_awarded:
                messages.success(request, f"🎉 Congratulations! You earned the '{achievement.badge.name}' badge!")

    @staticmethod
    def award_achievement_on_codebattle_completion(user, submission, request=None):
        """
        Award achievements specifically after code battle completion
        """
        # Check for achievements
        newly_awarded = AchievementService.check_and_award_achievements(user)

        # Add messages for newly awarded achievements
        if request and newly_awarded:
            for achievement in newly_awarded:
                messages.success(request, f"🎉 Congratulations! You earned the '{achievement.badge.name}' badge!")
