import json
import time
import threading
import random
from functools import lru_cache

import google.generativeai as genai
from django.conf import settings
from django.db import transaction
from django.db.models.functions import Lower

from .models import Question, Answer, Quiz, Topic
from accounts.models import User


# ==========================
# Gemini Model Utilities
# ==========================

genai.configure(api_key=settings.GEMINI_API_KEY)


@lru_cache(maxsize=4)
def get_gemini_model(model_name: str):
    """
    Cached Gemini model loader so we don't reinitialize models repeatedly.
    """
    return genai.GenerativeModel(model_name)


class GeminiQuestionGenerator:
    def __init__(self):
        # Use gemini-2.5-flash which is available and fast
        self.model_name = "models/gemini-2.5-flash"
        self.model = get_gemini_model(self.model_name)

    def list_available_models(self):
        """Helper method to list available models for debugging."""
        try:
            models = genai.list_models()
            available = [
                m.name
                for m in models
                if hasattr(m, "supported_generation_methods")
                and "generateContent" in m.supported_generation_methods
            ]
            print("Available Gemini models:", available)
            return available
        except Exception as e:
            print(f"Error listing models: {e}")
            return []

    # ==========================
    # Public API
    # ==========================

    def generate_questions(self, topic, difficulty="medium", num_questions=10):
        """
        Main entry: try batch generation first (fast), then fallback to per-question.
        """
        questions_data = []

        try:
            batch_questions = self._generate_questions_batch(
                topic=topic,
                difficulty=difficulty,
                num_questions=num_questions,
            )
            if batch_questions and len(batch_questions) >= num_questions:
                questions_data = batch_questions
            else:
                print(
                    "Batch generation failed or insufficient, "
                    "falling back to individual question generation"
                )
                questions_data = self._generate_questions_individual(
                    topic=topic,
                    difficulty=difficulty,
                    num_questions=num_questions,
                )
        except Exception as e:
            print(f"Batch generation error: {e}, falling back to individual generation")
            questions_data = self._generate_questions_individual(
                topic=topic,
                difficulty=difficulty,
                num_questions=num_questions,
            )

        return questions_data

    def generate_question(self, topic, difficulty="medium"):
        """
        Backward-compatible single question generator.
        """
        questions = self.generate_questions(topic, difficulty, 1)
        return questions[0] if questions else None

    # ==========================
    # Internal helpers
    # ==========================

    def _generate_questions_batch(self, topic, difficulty="medium", num_questions=10):
        """
        Generate multiple questions in a single API call (faster and cheaper).
        Uses streaming + better prompt + cached DB uniqueness check.
        """
        max_retries = 2  # Reduced retries for faster response
        base_delay = 1  # smaller base delay
        max_delay = 3   # cap backoff

        # Load existing questions (normalized) once per batch
        existing_normalized = set(
            Question.objects.annotate(normalized=Lower("question_text"))
            .values_list("normalized", flat=True)
        )

        for attempt in range(max_retries):
            try:
                prompt = f"""
Generate exactly {num_questions} unique multiple-choice aptitude questions
on the topic: {topic}.
Difficulty: {difficulty}.

CRITICAL RULES FOR CODE QUESTIONS:
- If a question asks about code output, behavior, or debugging, you MUST include the COMPLETE CODE in the "question" field string.
- Format code using proper line breaks (use \\n for newlines in the question text).
- Example format: "What will be printed after executing the following Python code?\\n\\ncode = 'hello'\\nprint(code.upper())\\n\\nChoices:"
- DO NOT write "the following code" or "this code snippet" without including the actual code in the text.
- The question must be completely self-contained.

GENERAL RULES:
- ALL questions MUST be original, creative, and non-repeated.
- DO NOT generate common textbook or standard aptitude questions.
- EACH question must focus on a different scenario, concept, or angle.
- Avoid plagiarism and do not copy known questions.
- Questions must be COMPLETE and include all necessary information.

Strict output format: a valid JSON array ONLY, no markdown, no comments:

[
  {{
    "question": "The complete question text with any code embedded using \\n",
    "options": ["Option 1", "Option 2", "Option 3", "Option 4"],
    "correct_answer": "Option 2",
    "explanation": "Very short explanation in one sentence."
  }},
  ...
]

Requirements:
- Exactly {num_questions} objects
- Each has exactly 4 options
- "correct_answer" MUST exactly match one of the options
- No markdown code fences, no extra text
"""

                # Use streaming for faster time-to-first-byte with timeout
                response = self.model.generate_content(
                    prompt, 
                    stream=True,
                    request_options={"timeout": 60}  # 60 second timeout
                )
                chunks = []
                for chunk in response:
                    if hasattr(chunk, "text") and chunk.text:
                        chunks.append(chunk.text)
                response_text = "".join(chunks).strip()

                # First, try direct JSON parse
                try:
                    batch_data = json.loads(response_text)
                except json.JSONDecodeError:
                    # If model accidentally wrapped in ```json ... ``` or ``` ... ```
                    cleaned = response_text

                    cleaned = cleaned.strip()
                    if cleaned.startswith("```json"):
                        cleaned = cleaned[len("```json"):].strip()
                    if cleaned.startswith("```"):
                        cleaned = cleaned[len("```"):].strip()
                    if cleaned.endswith("```"):
                        cleaned = cleaned[:-3].strip()

                    batch_data = json.loads(cleaned)

                if not isinstance(batch_data, list):
                    raise ValueError("Response must be a JSON array of questions")

                valid_questions = []

                for q_data in batch_data:
                    if not isinstance(q_data, dict):
                        continue

                    # Validate required keys
                    if not all(
                        k in q_data
                        for k in ("question", "options", "correct_answer")
                    ):
                        continue

                    question_text = q_data.get("question", "").strip()
                    # Strip whitespace from options
                    options = [opt.strip() for opt in q_data.get("options", []) if isinstance(opt, str)]
                    correct = q_data.get("correct_answer", "").strip()

                    if (
                        not question_text
                        or not isinstance(options, list)
                        or len(options) != 4
                    ):
                        continue

                    if correct not in options:
                        continue

                    # Normalize & check uniqueness
                    normalized = question_text.lower()
                    if normalized not in existing_normalized:
                        existing_normalized.add(normalized)
                        valid_questions.append(
                            {
                                "question": question_text,
                                "options": options,
                                "correct_answer": correct,
                                "explanation": q_data.get("explanation", "").strip(),
                            }
                        )

                    if len(valid_questions) >= num_questions:
                        break

                if len(valid_questions) >= num_questions:
                    return valid_questions[:num_questions]
                else:
                    print(
                        f"Batch attempt {attempt + 1}: "
                        f"only {len(valid_questions)} valid unique questions"
                    )

                    if attempt < max_retries - 1:
                        delay = min(base_delay * (2 ** attempt), max_delay)
                        print(f"Retrying batch generation in {delay} seconds...")
                        time.sleep(delay)

            except json.JSONDecodeError as e:
                print(
                    f"JSON decode error in batch generation attempt {attempt + 1}: {e}"
                )
                if attempt < max_retries - 1:
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    time.sleep(delay)
            except Exception as e:
                error_str = str(e).lower()
                if "429" in error_str or "quota" in error_str or "rate limit" in error_str:
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    print(
                        f"Rate limit hit, retrying batch generation in "
                        f"{delay} seconds..."
                    )
                    time.sleep(delay)
                elif (
                    "404" in error_str
                    or "not found" in error_str
                    or "not supported" in error_str
                ):
                    if self._try_fallback_model():
                        # Try again with new model
                        continue
                    else:
                        raise
                else:
                    print(
                        f"Error in batch generation attempt {attempt + 1}: {e}"
                    )
                    if attempt < max_retries - 1:
                        delay = min(base_delay * (2 ** attempt), max_delay)
                        time.sleep(delay)

        print("Batch generation failed after all retries")
        return []

    def _generate_questions_individual(
        self, topic, difficulty="medium", num_questions=10
    ):
        """
        Fallback: generate questions one-by-one.
        Optimized to avoid repeated DB hits for uniqueness.
        """
        questions_data = []
        max_retries = 2  # Reduced for faster response
        base_delay = 1
        max_delay = 3  # Reduced timeout

        # Load existing questions once
        existing_normalized = set(
            Question.objects.annotate(normalized=Lower("question_text"))
            .values_list("normalized", flat=True)
        )

        for i in range(num_questions):
            attempts = 0

            while attempts < max_retries:
                try:
                    prompt = f"""
Generate ONE highly unique multiple-choice aptitude question
on the topic: {topic}.
Difficulty: {difficulty}.

CRITICAL RULES FOR CODE QUESTIONS:
- If the question asks about code output, behavior, or debugging, you MUST include the COMPLETE CODE in the "question" field string.
- Format code using proper line breaks (use \\n for newlines in the question text).
- Example: "What will be the output?\\n\\nx = 10\\ny = 20\\nprint(x + y)\\n\\nChoices:"
- DO NOT reference "the following code" without including it in the text.
- Question must be fully self-contained.

GENERAL RULES:
- Question must be fully original and not a common textbook or exam question.
- Use a fresh scenario or idea.
- Avoid copying known problems.
- Include all necessary information to answer the question.

Output STRICTLY as JSON (no markdown, no comments):

{{
  "question": "The complete question text with any code embedded using \\n",
  "options": ["Option 1", "Option 2", "Option 3", "Option 4"],
  "correct_answer": "Option 3",
  "explanation": "Very short explanation in one sentence."
}}

Requirements:
- Exactly 4 options
- "correct_answer" MUST exactly match one option text
"""

                    # Streaming with timeout
                    response = self.model.generate_content(
                        prompt, 
                        stream=True,
                        request_options={"timeout": 60}
                    )
                    chunks = []
                    for chunk in response:
                        if hasattr(chunk, "text") and chunk.text:
                            chunks.append(chunk.text)
                    response_text = "".join(chunks).strip()

                    # Try direct JSON parse
                    try:
                        question_data = json.loads(response_text)
                    except json.JSONDecodeError:
                        cleaned = response_text.strip()
                        if cleaned.startswith("```json"):
                            cleaned = cleaned[len("```json"):].strip()
                        if cleaned.startswith("```"):
                            cleaned = cleaned[len("```"):].strip()
                        if cleaned.endswith("```"):
                            cleaned = cleaned[:-3].strip()
                        question_data = json.loads(cleaned)

                    # Validate structure
                    if not all(
                        k in question_data
                        for k in ("question", "options", "correct_answer")
                    ):
                        raise ValueError("Missing required fields in generated question")

                    question_text = question_data["question"].strip()
                    # Strip whitespace from options
                    options = [opt.strip() for opt in question_data["options"] if isinstance(opt, str)]
                    correct = question_data["correct_answer"].strip()

                    if (
                        not question_text
                        or not isinstance(options, list)
                        or len(options) != 4
                    ):
                        raise ValueError("Invalid options format or length")

                    if correct not in options:
                        raise ValueError("Correct answer must be one of the options")

                    normalized = question_text.lower()
                    if normalized in existing_normalized:
                        attempts += 1
                        print(
                            f"Duplicate question detected (normalized), "
                            f"regenerating... (attempt {attempts})"
                        )
                        continue

                    existing_normalized.add(normalized)
                    questions_data.append(
                        {
                            "question": question_text,
                            "options": options,
                            "correct_answer": correct,
                            "explanation": question_data.get(
                                "explanation", ""
                            ).strip(),
                        }
                    )
                    break  # success

                except json.JSONDecodeError as e:
                    print(f"JSON decode error generating question {i + 1}: {e}")
                    attempts += 1
                except Exception as e:
                    error_str = str(e).lower()
                    if "429" in error_str or "quota" in error_str or "rate limit" in error_str:
                        delay = min(base_delay * (2 ** attempts), max_delay)
                        print(
                            f"Rate limit hit for question {i + 1}, "
                            f"retrying in {delay} seconds..."
                        )
                        time.sleep(delay)
                        attempts += 1
                    elif (
                        "404" in error_str
                        or "not found" in error_str
                        or "not supported" in error_str
                    ):
                        if self._try_fallback_model():
                            continue
                        else:
                            attempts += 1
                    else:
                        print(f"Error generating question {i + 1}: {e}")
                        attempts += 1

            if attempts >= max_retries:
                print(
                    f"Failed to generate unique question {i + 1} "
                    f"after {max_retries} attempts. Skipping."
                )
                continue

        if len(questions_data) < num_questions:
            print(
                f"Warning: Only generated {len(questions_data)} "
                f"out of {num_questions} requested questions"
            )

        return questions_data

    def _try_fallback_model(self):
        """
        Try switching to an alternative working model, using cached instances.
        """
        alternative_models = [
            "models/gemini-flash-latest",
            "models/gemini-pro-latest",
            "models/gemini-2.0-flash",
        ]

        for alt_model in alternative_models:
            try:
                test_model = get_gemini_model(alt_model)
                # Quick lightweight test
                resp = test_model.generate_content("test", stream=False)
                if hasattr(resp, "text"):
                    self.model = test_model
                    self.model_name = alt_model
                    print(f"Successfully switched to model: {alt_model}")
                    return True
            except Exception as e:
                print(f"Fallback model {alt_model} failed: {e}")
                continue
        print("No fallback Gemini model worked.")
        return False


# ==========================
# Quiz Generation Service
# ==========================

class QuizGenerationService:
    def __init__(self):
        self.question_generator = GeminiQuestionGenerator()

    def _get_from_db(self, topic, difficulty, num_questions):
        """
        Try to fetch existing unique questions from the database to avoid API calls.
        Returns a list of question data dicts if enough unique questions exist, else None.
        """
        # Find questions from other quizzes with same topic/difficulty
        # We want unique question texts
        candidates = list(Question.objects.filter(
            quiz__topic__name__iexact=topic.name, 
            quiz__difficulty__iexact=difficulty
        ).values('question_text', 'options', 'correct_answer').distinct())
        
        # Simple deduplication by text (case-insensitive)
        unique_candidates = {}
        for q in candidates:
            norm = q['question_text'].lower().strip()
            if norm not in unique_candidates:
                unique_candidates[norm] = {
                    "question": q['question_text'],
                    "options": q['options'],
                    "correct_answer": q['correct_answer']
                }
        
        # Threshold: if we have at least 2x needed questions, reuse them to ensure variety
        # If we have very few, we prefer generating new ones to grow the pool
        if len(unique_candidates) >= num_questions * 2:
             print(f"Reusing {num_questions} questions from DB pool of {len(unique_candidates)}")
             return random.sample(list(unique_candidates.values()), num_questions)
        
        return None

    def generate_quiz(
        self,
        topic_id,
        num_questions=10,
        difficulty="medium",
        user=None,
        timeout=30,
    ):
        """
        Generate a new quiz with AI-generated questions.
        This uses a separate thread with a timeout for safety.
        """
        if not user:
            raise ValueError("User is required to create the quiz")

        topic = Topic.objects.get(id=topic_id)

        result = [None]
        exception = [None]

        # Try to get from DB first
        cached_questions = self._get_from_db(topic, difficulty, num_questions)
        
        if cached_questions:
             result[0] = cached_questions
             # Skip thread creation if we have cached questions
        else:
            def generate():
                try:
                    questions_data = self.question_generator.generate_questions(
                        topic=topic.name,
                        difficulty=difficulty,
                        num_questions=num_questions,
                    )
                    result[0] = questions_data
                except Exception as e:
                    exception[0] = e

            thread = threading.Thread(target=generate, daemon=True)
            thread.start()
            thread.join(timeout)

            if thread.is_alive():
                # We don't forcibly kill the thread, but we stop waiting & abort quiz creation
                raise TimeoutError("Question generation timed out")

            if exception[0]:
                raise exception[0]

        questions_data = result[0]
        if not questions_data:
            raise ValueError("Failed to generate questions for the quiz")

        with transaction.atomic():
            quiz = Quiz.objects.create(
                title=f"{topic.name} Quiz - {difficulty.capitalize()} Level",
                description=(
                    f"AI-generated quiz on {topic.name} "
                    f"with {num_questions} questions."
                ),
                topic=topic,
                created_by=user,
                difficulty=difficulty,
                time_limit=num_questions * 2,  # 2 minutes per question
            )

            for q_data in questions_data:
                Question.objects.create(
                    quiz=quiz,
                    question_text=q_data["question"],
                    question_type="multiple_choice",
                    options=q_data["options"],         # JSONField expected
                    correct_answer=q_data["correct_answer"],
                    points=1,
                    is_ai_generated=True,
                    # If you have explanation field:
                    # explanation=q_data.get("explanation", ""),
                )

            quiz.save()

        return quiz


# ==========================
# Progressive Quiz Generation Service
# ==========================

class ProgressiveQuizGenerationService:
    """
    Generates quizzes progressively: creates initial questions immediately,
    then continues generating remaining questions in the background.
    """
    def __init__(self):
        self.question_generator = GeminiQuestionGenerator()

    def generate_quiz_progressive(
        self,
        topic_id,
        num_questions=10,
        difficulty="medium",
        user=None,
        initial_timeout=30,
        callback=None,
    ):
        """
        Generate quiz with all questions in a single batch.
        No progressive loading - waits for all questions before returning.
        
        Args:
            topic_id: Topic ID
            num_questions: Total number of questions desired
            difficulty: Difficulty level
            user: User creating the quiz
            initial_timeout: Timeout for generation (seconds)
            callback: Optional callback function (not used in batch mode)
        
        Returns:
            Quiz object with all questions
        """
        if not user:
            raise ValueError("User is required to create the quiz")

        topic = Topic.objects.get(id=topic_id)
        
        # Generate ALL questions in one batch
        # Scale timeout based on number of questions (base 30s + 6s per question)
        actual_timeout = min(120, 30 + (num_questions * 6))
        print(f"Batch generating all {num_questions} questions (timeout: {actual_timeout}s)")
        
        # Generate all questions in initial batch
        initial_questions = self._generate_initial_batch(
            topic, difficulty, num_questions, actual_timeout
        )
        
        if not initial_questions:
            raise ValueError("Failed to generate initial questions")
        
        # Create quiz with all questions (no background generation)
        quiz = self._create_quiz_with_questions(
            topic, difficulty, user, num_questions, initial_questions
        )
        
        return quiz
    
    def _generate_initial_batch(self, topic, difficulty, count, timeout):
        """Generate initial batch of questions with timeout."""
        result = [None]
        exception = [None]
        
        def generate():
            try:
                questions_data = self.question_generator.generate_questions(
                    topic=topic.name,
                    difficulty=difficulty,
                    num_questions=count,
                )
                result[0] = questions_data
            except Exception as e:
                exception[0] = e
        
        thread = threading.Thread(target=generate, daemon=True)
        thread.start()
        thread.join(timeout)
        
        if thread.is_alive():
            print(f"Initial batch generation timed out after {timeout}s")
            return None
        
        if exception[0]:
            print(f"Initial batch generation failed: {exception[0]}")
            return None
        
        return result[0]
    
    def _create_quiz_with_questions(self, topic, difficulty, user, total_questions, questions_data):
        """Create quiz and add initial questions."""
        with transaction.atomic():
            quiz = Quiz.objects.create(
                title=f"{topic.name} Quiz - {difficulty.capitalize()} Level",
                description=(
                    f"AI-generated quiz on {topic.name} "
                    f"with {total_questions} questions."
                ),
                topic=topic,
                created_by=user,
                difficulty=difficulty,
                time_limit=total_questions * 2,  # 2 minutes per question
            )
            
            for q_data in questions_data:
                Question.objects.create(
                    quiz=quiz,
                    question_text=q_data["question"],
                    question_type="multiple_choice",
                    options=q_data["options"],
                    correct_answer=q_data["correct_answer"],
                    points=1,
                    is_ai_generated=True,
                )
            
            quiz.save()
        
        return quiz
    
    def _generate_remaining_background(self, quiz_id, topic_name, difficulty, count, callback):
        """Generate remaining questions in background and add to quiz."""
        try:
            print(f"Background: Generating {count} remaining questions...")
            questions_data = self.question_generator.generate_questions(
                topic=topic_name,
                difficulty=difficulty,
                num_questions=count,
            )
            
            if questions_data:
                with transaction.atomic():
                    quiz = Quiz.objects.get(id=quiz_id)
                    for q_data in questions_data:
                        Question.objects.create(
                            quiz=quiz,
                            question_text=q_data["question"],
                            question_type="multiple_choice",
                            options=q_data["options"],
                            correct_answer=q_data["correct_answer"],
                            points=1,
                            is_ai_generated=True,
                        )
                
                print(f"Background: Successfully added {len(questions_data)} questions to quiz {quiz_id}")
                
                # Call callback if provided (for WebSocket notifications)
                if callback:
                    callback(quiz_id, questions_data)
            else:
                print(f"Background: Failed to generate remaining questions for quiz {quiz_id}")
        
        except Exception as e:
            print(f"Background: Error generating remaining questions: {e}")
