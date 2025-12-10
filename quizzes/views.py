from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.utils import timezone
import json
from .models import Topic, Quiz, Question, Answer, GameSession
from .serializers import TopicSerializer, QuizSerializer, QuestionSerializer, GameSessionSerializer
from .services import GeminiQuestionGenerator
from gamification.services import AchievementService


def _determine_game_mode(quiz):
    """Helper function to determine if a quiz is part of a multiplayer session."""
    try:
        from multiplayer.models import Room
        room = Room.objects.filter(quiz=quiz, is_active=True).first()
        return 'multiplayer' if room else 'single'
    except Exception:
        return 'single'

@login_required
def quiz_list(request):
    quizzes = Quiz.objects.all()
    topics = Topic.objects.all()

    # Apply filters
    topic_id = request.GET.get('topic')
    difficulty = request.GET.get('difficulty')

    if topic_id:
        quizzes = quizzes.filter(topic_id=topic_id)
    if difficulty:
        quizzes = quizzes.filter(difficulty=difficulty)

    return render(request, 'quiz_list.html', {
        'quizzes': quizzes,
        'topics': topics,
        'request': request
    })

@login_required
def start_single_player_session(request, quiz_id):
    """Start a single player game session"""
    quiz = get_object_or_404(Quiz, id=quiz_id)
    
    # Check if there's an active session for this quiz
    active_session = GameSession.objects.filter(
        user=request.user,
        quiz=quiz,
        completed_at__isnull=True,
        mode='single'
    ).first()
    
    if not active_session:
        # Create new game session
        GameSession.objects.create(
            user=request.user,
            quiz=quiz,
            mode='single',
            total_questions=quiz.questions.count()
        )
    
    # Redirect to take quiz
    return redirect('take_quiz', quiz_id=quiz_id)

@login_required
def take_quiz(request, quiz_id):
    quiz = get_object_or_404(Quiz, id=quiz_id)
    
    # Check if quiz has questions - use count() for more reliable check
    question_count = quiz.questions.count()
    if question_count == 0:
        from django.contrib import messages
        messages.warning(request, 'This quiz does not have any questions yet. Please try another quiz.')
        # Clean up associated game sessions before deleting
        GameSession.objects.filter(quiz=quiz).delete()
        # Also delete the invalid quiz to prevent future issues
        quiz.delete()
        return redirect('quiz_list')
    
    questions = quiz.questions.all()
    
    # Ensure there's an active session (single or multiplayer)
    active_session = GameSession.objects.filter(
        user=request.user,
        quiz=quiz,
        completed_at__isnull=True
    ).first()
    
    if not active_session:
        # Create session if it doesn't exist (fallback for direct access)
        mode = _determine_game_mode(quiz)
        
        GameSession.objects.create(
            user=request.user,
            quiz=quiz,
            mode=mode,
            total_questions=question_count
        )
    
    # Build questions JSON - ensure we have questions
    questions_list = []
    for q in questions:
        if q.options:  # Only include questions with options
            questions_list.append({
                'id': q.id,
                'question_text': q.question_text,
                'question_type': q.question_type,
                'answers': [{'id': f"{q.id}_{i}", 'answer_text': option} for i, option in enumerate(q.options)]
            })
    
    # Double check - if no valid questions, redirect
    if not questions_list:
        from django.contrib import messages
        messages.warning(request, 'This quiz does not have valid questions. Please try another quiz.')
        # Clean up associated game sessions before deleting
        GameSession.objects.filter(quiz=quiz).delete()
        quiz.delete()
        return redirect('quiz_list')
    
    questions_json = json.dumps(questions_list)
    
    # Get expected total questions from game session
    expected_questions = active_session.total_questions if active_session else len(questions_list)
    
    return render(request, 'take_quiz.html', {
        'quiz': quiz,
        'questions_json': questions_json,
        'expected_questions': expected_questions,
        'game_session': active_session
    })

@csrf_exempt
@login_required
def submit_quiz(request, quiz_id):
    if request.method == 'POST':
        data = json.loads(request.body)
        answers = data.get('answers', {})

        quiz = get_object_or_404(Quiz, id=quiz_id)
        score = 0
        total_questions = quiz.questions.count()
        user_answers_dict = {}  # Store user's selected answers with question text

        for question in quiz.questions.all():
            user_answer = answers.get(str(question.id))
            selected_option_text = None
            is_correct = False
            
            if user_answer:
                # For AI-generated quizzes, check against the correct_answer field
                if question.correct_answer:
                    # Extract the option text from the answer ID (format: "question_id_index")
                    try:
                        question_id, option_index = user_answer.split('_')
                        option_index = int(option_index)
                        if question.options and 0 <= option_index < len(question.options):
                            selected_option_text = question.options[option_index]
                            if selected_option_text == question.correct_answer:
                                score += 1
                                is_correct = True
                    except (ValueError, IndexError):
                        pass
                else:
                    # Fallback to Answer model if it exists
                    correct_answers = question.answers.filter(is_correct=True)
                    if correct_answers.exists():
                        correct_answer_ids = set(str(a.id) for a in correct_answers)
                        if user_answer in correct_answer_ids:
                            score += 1
                            is_correct = True
                        # Get the selected answer text
                        try:
                            answer_obj = question.answers.get(id=user_answer)
                            selected_option_text = answer_obj.answer_text
                        except:
                            pass
            
            # Store user's answer for this question
            user_answers_dict[str(question.id)] = {
                'selected': selected_option_text,
                'is_correct': is_correct
            }

        # Get or create game session (should exist from take_quiz or multiplayer room)
        game_session = GameSession.objects.filter(
            user=request.user,
            quiz=quiz,
            completed_at__isnull=True
        ).order_by('-started_at').first()
        
        if not game_session:
            # Create game session if it doesn't exist (fallback)
            mode = _determine_game_mode(quiz)
            
            game_session = GameSession.objects.create(
                user=request.user,
                quiz=quiz,
                score=score,
                total_questions=total_questions,
                mode=mode,
                user_answers=user_answers_dict
            )
        else:
            # Update existing session
            game_session.score = score
            game_session.total_questions = total_questions
            game_session.completed_at = timezone.now()
            game_session.user_answers = user_answers_dict  # Store user answers
            game_session.save()

        # Update user progress only if this is the first completion of this quiz
        user = request.user
        previous_completions = GameSession.objects.filter(
            user=user,
            quiz=quiz,
            completed_at__isnull=False
        ).exclude(id=game_session.id)

        if not previous_completions.exists():
            # First time completing this quiz, update score
            user.total_score += score
            user.xp += score * 10
            user.level = user.total_score // 100 + 1
            user.save()

            # Update streak
            from gamification.models import Streak
            from datetime import date
            streak, created = Streak.objects.get_or_create(user=user)
            if streak.last_activity != date.today():
                streak.current_streak += 1
                if streak.current_streak > streak.longest_streak:
                    streak.longest_streak = streak.current_streak
            streak.save()

        # Award achievements
        AchievementService.award_achievement_on_quiz_completion(user, game_session, request)

        return JsonResponse({
            'success': True,
            'score': score,
            'total': total_questions,
            'redirect_url': f'/quizzes/{quiz_id}/results/'
        })

    return JsonResponse({'success': False})

@login_required
def generate_quiz(request):
    if request.method == 'POST':
        topic_id = request.POST.get('topic')
        difficulty = request.POST.get('difficulty')
        num_questions = int(request.POST.get('num_questions', 10))

        topic = get_object_or_404(Topic, id=topic_id)

        # Generate quiz progressively using the new service
        try:
            from quizzes.services import ProgressiveQuizGenerationService
            quiz_service = ProgressiveQuizGenerationService()
            
            # Generate quiz with adaptive initial batch; rest will generate in background
            quiz = quiz_service.generate_quiz_progressive(
                topic_id=topic_id,
                num_questions=num_questions,
                difficulty=difficulty,
                user=request.user,
                initial_timeout=30  # 30 seconds for adaptive batch size
            )
            
            # Create game session for single player mode
            GameSession.objects.create(
                user=request.user,
                quiz=quiz,
                mode='single',
                total_questions=num_questions  # Use requested count, not current count
            )
            
            # Redirect to take quiz immediately with initial questions
            return redirect('take_quiz', quiz_id=quiz.id)
            
        except Exception as e:
            # If there's an error, show error message
            from django.contrib import messages
            messages.error(request, f'Error generating quiz: {str(e)}. Please try again.')
            return redirect('single_player')

    # If GET request, redirect to home (shouldn't happen normally)
    return redirect('home')

@login_required
def quiz_results(request, quiz_id):
    quiz = get_object_or_404(Quiz, id=quiz_id)
    # Get the most recent completed session for this quiz (single or multiplayer)
    game_session = GameSession.objects.filter(
        user=request.user,
        quiz=quiz,
        completed_at__isnull=False
    ).order_by('-completed_at').first()

    # If no completed session, try to get the most recent session regardless of completion status
    if not game_session:
        game_session = GameSession.objects.filter(
            user=request.user,
            quiz=quiz
        ).order_by('-started_at').first()

    # If still no session found, return error
    if not game_session:
        from django.contrib import messages
        messages.error(request, 'No game session found for this quiz.')
        return redirect('quiz_list')

    # Calculate percentage
    percentage = (game_session.score / game_session.total_questions) * 100 if game_session.total_questions > 0 else 0

    # Calculate incorrect answers
    incorrect_answers = game_session.total_questions - game_session.score

    # Determine performance message
    if percentage >= 90:
        performance = "Excellent!"
        badge_class = "success"
    elif percentage >= 70:
        performance = "Good job!"
        badge_class = "primary"
    elif percentage >= 50:
        performance = "Keep practicing!"
        badge_class = "warning"
    else:
        performance = "Need more practice"
        badge_class = "danger"

    # Get questions with answers for review
    user_answers = game_session.user_answers or {}
    questions = []
    for question in quiz.questions.all():
        question_id = str(question.id)
        user_answer_data = user_answers.get(question_id, {})
        user_selected = user_answer_data.get('selected', None)
        is_correct = user_answer_data.get('is_correct', False)

        questions.append({
            'question': question,
            'correct_answer': question.correct_answer,
            'options': question.options,
            'user_selected': user_selected,
            'is_correct': is_correct
        })

    # For multiplayer, get ALL players' results (including current user)
    all_sessions = []
    if game_session.mode == 'multiplayer':
        all_sessions_queryset = GameSession.objects.filter(
            quiz=quiz,
            completed_at__isnull=False
        ).order_by('-score', 'completed_at')  # Sort by score desc, then by completion time

        # Calculate percentage and rank for each session
        for rank, session in enumerate(all_sessions_queryset, start=1):
            session_percentage = (session.score / session.total_questions) * 100 if session.total_questions > 0 else 0
            session.percentage = round(session_percentage, 1)
            session.rank = rank
            session.is_current_user = (session.user == request.user)
            all_sessions.append(session)

    context = {
        'quiz': quiz,
        'game_session': game_session,
        'percentage': round(percentage, 1),
        'performance': performance,
        'badge_class': badge_class,
        'incorrect_answers': incorrect_answers,
        'questions': questions,
        'all_sessions': all_sessions,
    }

    return render(request, 'quiz_results.html', context)
@login_required
def single_player(request):
    topics = Topic.objects.all()
    return render(request, 'single_player.html', {'topics': topics})

@login_required
def create_quiz(request):
    if request.method == 'POST':
        # Handle quiz creation form
        pass
    topics = Topic.objects.all()
    return render(request, 'create_quiz.html', {'topics': topics})

class TopicListCreateView(generics.ListCreateAPIView):
    queryset = Topic.objects.all()
    serializer_class = TopicSerializer
    permission_classes = [IsAuthenticated]

class QuizListCreateView(generics.ListCreateAPIView):
    queryset = Quiz.objects.all()
    serializer_class = QuizSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

class QuizDetailView(generics.RetrieveAPIView):
    queryset = Quiz.objects.all()
    serializer_class = QuizSerializer
    permission_classes = [IsAuthenticated]

class QuestionListCreateView(generics.ListCreateAPIView):
    queryset = Question.objects.all()
    serializer_class = QuestionSerializer
    permission_classes = [IsAuthenticated]

class GameSessionListCreateView(generics.ListCreateAPIView):
    queryset = GameSession.objects.all()
    serializer_class = GameSessionSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

@login_required
def unique_questions(request):
    """
    View to list unique questions across all topics and sessions.
    """
    # Get distinct question texts
    unique_questions = Question.objects.values('question_text').distinct()

    # Optional: Filter by topic if provided
    topic_id = request.GET.get('topic')
    if topic_id:
        unique_questions = unique_questions.filter(quiz__topic_id=topic_id)

    # Convert to list for template
    questions_list = list(unique_questions)

    # Get topics for filter dropdown
    topics = Topic.objects.all()

    context = {
        'unique_questions': questions_list,
        'topics': topics,
        'selected_topic': topic_id,
    }

    return render(request, 'unique_questions.html', context)
