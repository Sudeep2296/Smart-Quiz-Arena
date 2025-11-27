from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, authenticate, logout, get_user_model
from django.contrib import messages
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from .models import (
    Question, QuizSession, PlayerScore, SessionQuestion
)
# Adapt imports for project structure
from codebattle.models import Challenge as CodingProblem, Battle as CodingBattle, Submission as CodeSubmission
# PlayerSubmission seems unused or alias for CodeSubmission
PlayerSubmission = CodeSubmission 
CustomUser = get_user_model()

from .services import GeminiQuestionGenerator
from django.db.models import Avg, Max, Sum, Q
import os
import json
import subprocess
import time
import re
import requests
import base64
import uuid
import random

import os
import json
import subprocess
import time
import re
import requests
import base64
import uuid
import random

# Configure Gemini API (optional)
try:
    import google.generativeai as genai
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
except ImportError:
    genai = None

# ==================== BASIC VIEWS ====================

# ------------------- SINGLE PLAYER -------------------
@csrf_exempt
def start_single_session(request):
    """Start a new single player session (API)"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            topics = data.get('topics', [])
            difficulty = data.get('difficulty', 'mixed')
            num_questions = int(data.get('num_questions', 5))
            time_limit = int(data.get('time_per_question_seconds', 15))
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        # Create session
        try:
            session = QuizSession.objects.create(
                session_type='single',
                max_players=1,
                time_limit=time_limit,
                difficulty_level=difficulty
            )
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            print(f"ERROR creating session: {error_trace}")
            return JsonResponse({'error': f'Session creation failed: {str(e)}'}, status=500)

        # 1. Get IDs of questions seen by this user in their last 5 sessions
        excluded_ids = []
        if request.user.is_authenticated:
            last_sessions = QuizSession.objects.filter(
                playerscore__player=request.user,
                session_type='single'
            ).order_by('-created_at')[:5]
            
            excluded_ids = SessionQuestion.objects.filter(
                session__in=last_sessions
            ).values_list('question_id', flat=True)
            excluded_ids = list(excluded_ids)

        # 2. Generate/Fetch questions with exclusion logic
        questions_data = generate_mcq_questions(
            num_questions, 
            topics, 
            difficulty, 
            time_limit, 
            user=request.user if request.user.is_authenticated else None,
            excluded_ids=excluded_ids
        )

        question_objects = []
        for q in questions_data:
            # Check if question already exists to avoid duplicates in DB
            # Use db_id if available, otherwise check text
            if 'db_id' in q:
                 try:
                     question_obj = Question.objects.get(id=q['db_id'])
                 except Question.DoesNotExist:
                     # Should not happen if logic is correct, but fallback
                     question_obj = Question.objects.create(
                        question_text=q.get('question_text'),
                        question_type=q.get('question_type', 'multiple_choice'),
                        difficulty=q.get('difficulty', 'medium'),
                        options=q.get('options', []),
                        correct_answer=q.get('correct_answer'),
                        # explanation=q.get('explanation', ''), # explanation not in model yet?
                        # category=q.get('category', ''), # category not in model yet?
                        is_ai_generated=q.get('is_ai_generated', False)
                    )
            else:
                q_text = q.get('question_text')
                existing_q = Question.objects.filter(question_text=q_text).first()
                
                if existing_q:
                    question_obj = existing_q
                else:
                    # Note: Question model fields might need adjustment if category/explanation missing
                    # Based on my view of models.py, explanation/category are NOT in Question model shown earlier?
                    # Wait, looking at models.py view earlier:
                    # Question model has: quiz, question_text, question_type, correct_answer, options, points, is_ai_generated.
                    # It DOES NOT have explanation or category directly? 
                    # Ah, Quiz has topic. Question has quiz.
                    # But the user code assumes Question has category and explanation.
                    # I will create a dummy quiz for these ad-hoc questions if needed, or just create them linked to a default quiz.
                    
                    # For now, I'll try to create without quiz if nullable, but it's ForeignKey...
                    # I might need a default 'General' quiz or topic.
                    
                    # Let's check if I can get a default quiz.
                    default_topic, _ = Topic.objects.get_or_create(name="General")
                    default_user, _ = CustomUser.objects.get_or_create(username="system")
                    default_quiz, _ = Quiz.objects.get_or_create(title="General Pool", defaults={'topic': default_topic, 'created_by': default_user})
                    
                    question_obj = Question.objects.create(
                        quiz=default_quiz,
                        question_text=q.get('question_text'),
                        question_type=q.get('question_type', 'multiple_choice'),
                        # difficulty=q.get('difficulty', 'medium'), # Not in Question model? Quiz has difficulty.
                        options=q.get('options', []),
                        correct_answer=q.get('correct_answer'),
                        # explanation=q.get('explanation', ''),
                        is_ai_generated=q.get('is_ai_generated', False)
                    )
            question_objects.append(question_obj)

        for i, question_obj in enumerate(question_objects):
            SessionQuestion.objects.create(session=session, question=question_obj, order=i)
        
        session.save()

        return JsonResponse({'session_id': session.id})

    return JsonResponse({'error': 'Method not allowed'}, status=405)

# ------------------- OTHER ENDPOINTS -------------------
def generate_question(request):
    """API endpoint to generate a question using Gemini"""
    try:
        model = genai.GenerativeModel('gemini-pro')
        prompt = "Generate a multiple choice quiz question about programming or computer science. Return in JSON format with keys: question_text, options (array of 4 strings), correct_answer (index 0-3), explanation, category, difficulty (easy/medium/hard)"
        response = model.generate_content(prompt)
        question_data = json.loads(response.text)
        
        # Default quiz/topic handling
        from .models import Topic, Quiz
        default_topic, _ = Topic.objects.get_or_create(name=question_data.get('category', 'General'))
        default_user = request.user if request.user.is_authenticated else CustomUser.objects.first()
        default_quiz, _ = Quiz.objects.get_or_create(title=f"Generated - {default_topic.name}", defaults={'topic': default_topic, 'created_by': default_user})

        question = Question.objects.create(
            quiz=default_quiz,
            question_text=question_data['question_text'],
            question_type='multiple_choice',
            # difficulty=question_data['difficulty'], # Not in model
            options=question_data['options'],
            correct_answer=question_data['correct_answer'],
            # explanation=question_data['explanation'], # Not in model
            # category=question_data['category'], # Not in model
            is_ai_generated=True
        )
        return JsonResponse({
            'id': question.id,
            'question_text': question.question_text,
            'options': question.options,
            'time_limit': 15
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def submit_answer(request):
    """API endpoint to submit answer"""
    if request.method == 'POST':
        try:
            import traceback
            
            question_id = request.POST.get('question_id')
            answer = request.POST.get('answer')
            session_id = request.POST.get('session_id')
            
            print(f"DEBUG submit_answer: question_id={question_id}, answer={answer}, session_id={session_id}")
            
            if not question_id or not session_id:
                print(f"ERROR: Missing parameters - question_id={question_id}, session_id={session_id}")
                return JsonResponse({'error': 'Missing question_id or session_id'}, status=400)
            
            question = Question.objects.get(id=question_id)
            print(f"DEBUG: Found question: {question.question_text[:50]}")
            
            # Check correctness (assuming answer is index or text)
            is_correct = False
            if str(answer).isdigit():
                # If answer is index
                idx = int(answer)
                # Check if correct_answer is index or text
                if str(question.correct_answer).isdigit():
                     is_correct = (idx == int(question.correct_answer))
                elif question.options and 0 <= idx < len(question.options):
                     is_correct = (question.options[idx] == question.correct_answer)
            else:
                # If answer is text
                is_correct = (answer == question.correct_answer)

            print(f"DEBUG: is_correct={is_correct}")
            
            if not request.user.is_authenticated:
                user, _ = CustomUser.objects.get_or_create(username='anonymous', defaults={'email': 'anonymous@example.com'})
            else:
                user = request.user
                
            print(f"DEBUG: User={user.username}")
            
            score, _ = PlayerScore.objects.get_or_create(
                player=user,
                session_id=session_id,
                defaults={'score': 0, 'correct_answers': 0, 'total_answers': 0}
            )
            score.total_answers += 1
            if is_correct:
                score.correct_answers += 1
                score.score += 1
            score.save()
            
            print(f"DEBUG: Score updated - score={score.score}, correct={score.correct_answers}, total={score.total_answers}")
            
            session = QuizSession.objects.get(id=session_id)
            print(f"DEBUG: Found session {session.id}, current_index={session.current_question_index}")
            
            # Increment index
            session.current_question_index += 1
            session.save()

            next_q = session.next_question()
            print(f"DEBUG: next_question returned: {next_q}")
            
            response = {'status': 'ok', 'score': score.score}
            if next_q is None:
                print("DEBUG: No more questions, ending session")
                session.end_session()
                per_question = []
                for sq in session.sessionquestion_set.order_by('order'):
                    q = sq.question
                    correct_idx = None
                    # Try to determine correct index
                    if q.options and q.correct_answer in q.options:
                        correct_idx = q.options.index(q.correct_answer)
                    elif str(q.correct_answer).isdigit():
                        correct_idx = int(q.correct_answer)

                    per_question.append({
                        'question_id': q.id,
                        'question_text': q.question_text,
                        'options': q.options,
                        'correct_index': correct_idx,
                        'explanation': '' # q.explanation or ''
                    })
                response['session_finished'] = True
                response['final_summary'] = {
                    'total_questions': score.total_answers,
                    'correct_answers': score.correct_answers,
                    'incorrect_answers': score.total_answers - score.correct_answers,
                    'score': score.score,
                    'accuracy': score.accuracy,
                    'per_question_summary': per_question
                }
            
            print(f"DEBUG: Returning response: {response}")
            return JsonResponse(response)
            
        except Question.DoesNotExist:
            error_trace = traceback.format_exc()
            print(f"ERROR Question.DoesNotExist: {error_trace}")
            return JsonResponse({'error': 'Question not found'}, status=404)
        except QuizSession.DoesNotExist:
            error_trace = traceback.format_exc()
            print(f"ERROR QuizSession.DoesNotExist: {error_trace}")
            return JsonResponse({'error': 'Session not found'}, status=404)
        except Exception as e:
            error_trace = traceback.format_exc()
            print(f"ERROR in submit_answer: {error_trace}")
            return JsonResponse({'error': f'Server error: {str(e)}'}, status=500)
    
    return JsonResponse({'error': 'Invalid request'}, status=400)

@csrf_exempt
def generate_quiz_session(request):
    """API endpoint to generate a complete quiz session with questions"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    # Validation omitted for brevity
    mode = data.get('mode', 'single')
    session_id = data.get('session_id', str(uuid.uuid4()))
    battle_id = data.get('battle_id') if mode == 'multiplayer' else None
    players = data.get('players', []) if mode == 'multiplayer' else []
    num_questions = data.get('num_questions', 5)
    topics = data.get('topics', [])
    difficulty = data.get('difficulty', 'mixed')
    format_type = data.get('format', 'mcq')
    mix = data.get('mix', {'mcq_percent': 80, 'coding_percent': 20})
    time_per_question = data.get('time_per_question_seconds', 30)
    seed = data.get('seed')
    if seed is not None:
        random.seed(seed)
    else:
        seed = random.randint(0, 1000000)
        random.seed(seed)
    if format_type == 'mcq':
        questions = generate_mcq_questions(num_questions, topics, difficulty, time_per_question)
    elif format_type == 'coding':
        questions = generate_coding_questions(num_questions, topics, difficulty, time_per_question)
    elif format_type == 'mixed':
        mcq_count = int(num_questions * (mix.get('mcq_percent', 80) / 100))
        coding_count = num_questions - mcq_count
        mcq_questions = generate_mcq_questions(mcq_count, topics, difficulty, time_per_question)
        coding_questions = generate_coding_questions(coding_count, topics, difficulty, time_per_question)
        questions = mcq_questions + coding_questions
        random.shuffle(questions)
    scoring_rules = {"base_points_correct": 10, "time_bonus_per_second": 1, "penalty_incorrect": 0}
    response = {
        "mode": mode,
        "session_id": session_id,
        "battle_id": battle_id,
        "seed_used": seed,
        "scoring_rules": scoring_rules,
        "questions": questions,
        "final_instructions": "After answering all questions, review your performance and explanations.",
        "per_question_feedback_template": {
            "q_id": "string",
            "user_answer": "string or code",
            "is_correct": True,
            "explanation": "reason why",
            "suggestion": "short tip"
        },
        "final_summary_template": {
            "session_id": session_id,
            "total_questions": num_questions,
            "correct_answers": 0,
            "incorrect_answers": 0,
            "score": 0,
            "per_question_summary": [],
            "overall_advice": "Keep practicing to improve your skills!"
        }
    }
    if mode == 'multiplayer':
        for question in response['questions']:
            if 'hidden_answer' in question:
                del question['hidden_answer']
    return JsonResponse(response)

def fetch_questions_from_api(count, topics, difficulty):
    """Fetch questions from Gemini API when DB is exhausted"""
    if not genai:
        return []
    try:
        model = genai.GenerativeModel('gemini-pro')
        topic_str = "general knowledge"
        if topics and topics != ['']:
            topic_str = ", ".join(topics)
        prompt = f"Generate {count} unique multiple choice quiz questions about {topic_str}. Difficulty: {difficulty}. Return ONLY a JSON array of objects. Each object must have: question_text, options (array of 4 strings), correct_answer (integer index 0-3), explanation, category, difficulty"
        response = model.generate_content(prompt)
        text = response.text
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        questions_data = json.loads(text)
        new_questions = []
        
        # Need default quiz
        from .models import Topic, Quiz
        default_topic, _ = Topic.objects.get_or_create(name=topics[0] if topics else 'General')
        default_user = CustomUser.objects.first()
        default_quiz, _ = Quiz.objects.get_or_create(title=f"Generated - {default_topic.name}", defaults={'topic': default_topic, 'created_by': default_user})

        for q_data in questions_data:
            question = Question.objects.create(
                quiz=default_quiz,
                question_text=q_data['question_text'],
                question_type='multiple_choice',
                # difficulty=q_data.get('difficulty', difficulty),
                options=q_data['options'],
                correct_answer=q_data['correct_answer'],
                # explanation=q_data.get('explanation', ''),
                # category=q_data.get('category', topics[0] if topics else 'General'),
                is_ai_generated=True
            )
            new_questions.append({
                'question_text': question.question_text,
                'question_type': question.question_type,
                'difficulty': difficulty,
                'options': question.options,
                'correct_answer': question.correct_answer,
                'explanation': '',
                'category': default_topic.name,
                'is_ai_generated': True,
                'db_id': question.id
            })
        return new_questions
    except Exception as e:
        print(f"Error fetching from API: {e}")
        return []

def generate_mcq_questions(count, topics, difficulty, time_limit, user=None, excluded_ids=None):
    """Generate multiple choice questions"""
    if excluded_ids is None:
        excluded_ids = []
    
    unique_questions = []
    seen_texts = set()

    # 1. Try to fetch from DB first, respecting exclusions
    query = Q(question_type='multiple_choice')
    
    # Filter by topics if provided
    if topics and len(topics) > 0 and topics != ['']:
        topic_query = Q()
        for topic in topics:
            topic_query |= Q(quiz__topic__name__icontains=topic) | Q(question_text__icontains=topic)
        query &= topic_query
    
    # Filter by difficulty if provided and not mixed
    if difficulty != 'mixed':
        # Difficulty is on Quiz, not Question in current model
        query &= Q(quiz__difficulty=difficulty)

    # Exclude previously seen questions
    if excluded_ids:
        query &= ~Q(id__in=excluded_ids)

    # Fetch random questions from DB
    db_questions = list(Question.objects.filter(query).order_by('?')[:count])
    
    for q in db_questions:
        unique_questions.append({
            'question_text': q.question_text,
            'question_type': q.question_type,
            'difficulty': q.quiz.difficulty,
            'options': q.options,
            'correct_answer': q.correct_answer,
            'explanation': '', # q.explanation,
            'category': q.quiz.topic.name,
            'is_ai_generated': q.is_ai_generated,
            'db_id': q.id
        })
        seen_texts.add(q.question_text)

    # 2. If not enough questions, generate via AI (Gemini)
    if len(unique_questions) < count:
        needed = count - len(unique_questions)
        try:
            generator = GeminiQuestionGenerator()
            topic_str = ", ".join(topics) if topics else "General Knowledge"
            
            # Batch generate questions
            ai_questions = generator.generate_questions(
                topic=topic_str,
                num_questions=needed,
                difficulty=difficulty
            )
            
            for q_data in ai_questions:
                # Check for duplicates against seen_texts
                if q_data.get('question') not in seen_texts:
                    # Format options
                    options = q_data.get('options', [])
                    correct_ans = q_data.get('correct_answer')
                    
                    # Ensure options is a list of strings
                    if isinstance(options, str):
                        try:
                            options = json.loads(options)
                        except:
                            options = [options]
                            
                    unique_questions.append({
                        'question_text': q_data.get('question'),
                        'question_type': 'multiple_choice',
                        'difficulty': difficulty if difficulty != 'mixed' else 'medium',
                        'options': options,
                        'correct_answer': correct_ans,
                        'explanation': q_data.get('explanation'),
                        'category': topics[0] if topics else 'General',
                        'is_ai_generated': True
                    })
                    seen_texts.add(q_data.get('question'))
                    if len(unique_questions) >= count:
                        break
        except Exception as e:
            import traceback
            print(f"AI Generation Error: {e}")
            print(traceback.format_exc())
            # Fallback: fetch more from DB ignoring exclusions if absolutely necessary
            if len(unique_questions) < count:
                print("DEBUG: Falling back to DB questions (ignoring exclusions)")
                remaining = count - len(unique_questions)
                fallback_query = Q(question_type='multiple_choice')
                if topics:
                    t_q = Q()
                    for t in topics:
                        t_q |= Q(quiz__topic__name__icontains=t)
                    fallback_query &= t_q
                
                more_db = list(Question.objects.filter(fallback_query).exclude(id__in=[q.get('db_id') for q in unique_questions if 'db_id' in q]).order_by('?')[:remaining])
                for q in more_db:
                    unique_questions.append({
                        'question_text': q.question_text,
                        'question_type': q.question_type,
                        'difficulty': q.quiz.difficulty,
                        'options': q.options,
                        'correct_answer': q.correct_answer,
                        'explanation': '',
                        'category': q.quiz.topic.name,
                        'is_ai_generated': q.is_ai_generated,
                        'db_id': q.id
                    })

    # 3. ABSOLUTE FALLBACK: If we still don't have enough questions, use hardcoded ones
    if len(unique_questions) < count:
        print("DEBUG: Using hardcoded fallback questions")
        needed = count - len(unique_questions)
        fallback_pool = get_all_mcq_questions() # This now includes DB questions too
        
        # Shuffle and pick
        random.shuffle(fallback_pool)
        
        for q in fallback_pool:
            if q['question_text'] not in seen_texts:
                unique_questions.append({
                    'question_text': q['question_text'],
                    'question_type': 'multiple_choice',
                    'difficulty': q.get('difficulty', 'medium'),
                    'options': q.get('options', []),
                    'correct_answer': q.get('correct_answer'),
                    'explanation': q.get('explanation', ''),
                    'category': q.get('category', 'General'),
                    'is_ai_generated': False
                })
                seen_texts.add(q['question_text'])
                if len(unique_questions) >= count:
                    break
                    
    # 4. Emergency Fallback: If still not enough (e.g. empty DB and AI fail), repeat questions
    while len(unique_questions) < count and len(unique_questions) > 0:
        q = unique_questions[0] # Just duplicate the first one
        unique_questions.append(q.copy())

    return unique_questions[:count]

def generate_coding_questions(count, topics, difficulty, time_limit):
    """Generate coding questions"""
    questions = []
    available_questions = get_all_coding_questions()
    if topics and len(topics) > 0 and topics != ['']:
        available_questions = [q for q in available_questions if any(topic.lower() in q.get('topic', '').lower() for topic in topics)]
    if difficulty != 'mixed':
        available_questions = [q for q in available_questions if q.get('difficulty') == difficulty]
    
    # Fallback if no questions match filter
    if not available_questions:
        available_questions = get_all_coding_questions()
        
    selected_questions = random.sample(available_questions, min(count, len(available_questions)))
    for q_data in selected_questions:
        question = {
            "q_id": f"coding_{uuid.uuid4().hex[:8]}",
            "type": "coding",
            "topic": q_data.get('topic', 'Programming'),
            "difficulty": q_data.get('difficulty', 'medium'),
            "time_limit_seconds": time_limit,
            "payload": {
                "description": q_data['description'],
                "input_description": q_data.get('input_description', ''),
                "output_description": q_data.get('output_description', ''),
                "constraints": q_data.get('constraints', ''),
                "function_signature": q_data.get('function_signature'),
                "allowed_languages": q_data.get('allowed_languages', ["python", "javascript"]),
                "sample_tests": q_data.get('sample_tests', [])
            },
            "reveal_after_submission": True,
            "hidden_answer": {
                "reference_solution_notes": q_data.get('reference_solution_notes', ''),
                "canonical_tests": q_data.get('canonical_tests', []),
                "hidden_tests": q_data.get('hidden_tests', [])
            }
        }
        questions.append(question)
    return questions

def get_all_mcq_questions():
    """Get all available MCQ questions (fallback + AI generated)"""
    fallback_questions = [
        {
            'question_text': 'What is Python?',
            'options': ['A programming language', 'A snake', 'A database', 'A web framework'],
            'correct_answer': 0,
            'explanation': 'Python is a high-level programming language.',
            'category': 'Programming',
            'difficulty': 'easy'
        },
        {
            'question_text': 'Which of these is NOT a valid variable name in Python?',
            'options': ['my_var', '2var', '_var', 'var2'],
            'correct_answer': 1,
            'explanation': 'Variable names cannot start with a number.',
            'category': 'Programming',
            'difficulty': 'easy'
        },
        {
            'question_text': 'What does HTML stand for?',
            'options': ['Hyper Text Markup Language', 'High Tech Modern Language', 'Hyper Transfer Mode Link', 'Home Tool Markup Language'],
            'correct_answer': 0,
            'explanation': 'HTML stands for Hyper Text Markup Language.',
            'category': 'Web Development',
            'difficulty': 'easy'
        },
        {
            'question_text': 'Which data structure uses LIFO?',
            'options': ['Queue', 'Stack', 'Tree', 'Graph'],
            'correct_answer': 1,
            'explanation': 'Stack uses Last In First Out (LIFO).',
            'category': 'Computer Science',
            'difficulty': 'medium'
        },
        {
            'question_text': 'What is the time complexity of binary search?',
            'options': ['O(n)', 'O(n^2)', 'O(log n)', 'O(1)'],
            'correct_answer': 2,
            'explanation': 'Binary search halves the search space each step, so it is O(log n).',
            'category': 'Algorithms',
            'difficulty': 'medium'
        }
    ]
    try:
        from .models import Question
        db_questions = Question.objects.filter(question_type='multiple_choice')
        for q in db_questions:
            fallback_questions.append({
                'question_text': q.question_text,
                'options': q.options,
                'correct_answer': q.correct_answer,
                'explanation': '', # q.explanation or 'No explanation available.',
                'category': q.quiz.topic.name if q.quiz and q.quiz.topic else 'General',
                'difficulty': q.quiz.difficulty if q.quiz else 'medium'
            })
    except:
        pass
    return fallback_questions

def get_all_coding_questions():
    """Get all available coding questions"""
    # Fetch from DB if possible
    coding_questions = []
    try:
        from codebattle.models import Challenge
        challenges = Challenge.objects.all()
        for c in challenges:
            coding_questions.append({
                'description': c.description,
                'input_description': '',
                'output_description': '',
                'constraints': '',
                'function_signature': '', # Need to store this in model?
                'allowed_languages': ['python'],
                'topic': 'Programming',
                'difficulty': c.difficulty,
                'sample_tests': [], # c.test_cases
                'reference_solution_notes': '',
                'canonical_tests': c.test_cases,
                'hidden_tests': []
            })
    except:
        pass

    if not coding_questions:
        coding_questions = [
            {
                'description': 'Write a function that reverses a string.',
                'input_description': 'A string s',
                'output_description': 'The reversed string',
                'constraints': '1 <= len(s) <= 1000',
                'function_signature': 'def reverse_string(s: str) -> str:',
                'allowed_languages': ['python', 'javascript'],
                'topic': 'String Manipulation',
                'difficulty': 'easy',
                'sample_tests': [
                    {'input': '"hello"', 'expected_output': '"olleh"'}
                ]
            },
            {
                'description': 'Write a function that checks if a number is even.',
                'input_description': 'An integer n',
                'output_description': 'True if even, False otherwise',
                'constraints': '-10^9 <= n <= 10^9',
                'function_signature': 'def is_even(n: int) -> bool:',
                'allowed_languages': ['python', 'javascript'],
                'topic': 'Math',
                'difficulty': 'easy',
                'sample_tests': [
                    {'input': '2', 'expected_output': 'True'},
                    {'input': '3', 'expected_output': 'False'}
                ]
            },
            {
                'description': 'Write a function to calculate factorial of n.',
                'input_description': 'An integer n >= 0',
                'output_description': 'Factorial of n',
                'constraints': '0 <= n <= 20',
                'function_signature': 'def factorial(n: int) -> int:',
                'allowed_languages': ['python', 'javascript'],
                'topic': 'Math',
                'difficulty': 'medium',
                'sample_tests': [
                    {'input': '5', 'expected_output': '120'},
                    {'input': '0', 'expected_output': '1'}
                ]
            }
        ]
    return coding_questions

@csrf_exempt
def get_next_question(request, session_id):
    """Return the next question for a quiz session (simple implementation)."""
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    try:
        session = QuizSession.objects.get(id=session_id)
        q = session.get_current_question()
        if not q:
            # If no question found at current index, check if session is finished or empty
            if session.current_question_index >= session.sessionquestion_set.count():
                 return JsonResponse({'error': 'Session finished'}, status=404)
            return JsonResponse({'error': 'No question found'}, status=404)
        return JsonResponse({
            'question_id': q.id,
            'question_text': q.question_text,
            'options': q.options,
            'time_limit': session.time_limit,
            'difficulty': q.quiz.difficulty if q.quiz else 'medium',
            'category': q.quiz.topic.name if q.quiz and q.quiz.topic else 'General',
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
