from django.urls import path
from . import views
from . import api_views

urlpatterns = [
    path('', views.quiz_list, name='quiz_list'),
    path('single-player/', views.single_player, name='single_player'),
    path('<int:quiz_id>/start/', views.start_single_player_session, name='start_single_player_session'),
    path('<int:quiz_id>/take/', views.take_quiz, name='take_quiz'),
    path('<int:quiz_id>/submit/', views.submit_quiz, name='submit_quiz'),
    path('<int:quiz_id>/results/', views.quiz_results, name='quiz_results'),
    path('create/', views.create_quiz, name='create_quiz'),
    path('generate/', views.generate_quiz, name='generate_quiz'),
    path('topics/', views.TopicListCreateView.as_view(), name='topic-list'),
    path('quizzes/', views.QuizListCreateView.as_view(), name='quiz-list'),
    path('quizzes/<int:pk>/', views.QuizDetailView.as_view(), name='quiz-detail'),
    path('questions/', views.QuestionListCreateView.as_view(), name='question-list'),
    path('sessions/', views.GameSessionListCreateView.as_view(), name='session-list'),
    path('unique-questions/', views.unique_questions, name='unique_questions'),
    
    # New API endpoints
    path('api/start-session/', api_views.start_single_session, name='api_start_session'),
    path('api/submit-answer/', api_views.submit_answer, name='api_submit_answer'),
    path('api/generate-session/', api_views.generate_quiz_session, name='api_generate_session'),
    path('api/generate-question/', api_views.generate_question, name='api_generate_question'),
    path('api/next-question/<int:session_id>/', api_views.get_next_question, name='api_next_question'),
]
