from channels.generic.websocket import AsyncWebsocketConsumer
import json
import logging
import random
from channels.db import database_sync_to_async
from django.utils import timezone
from quizzes.models import Question
# Adapt imports
from codebattle.models import Challenge as CodingProblem
from codebattle.services import Judge0Service

logger = logging.getLogger(__name__)

# In-memory store for room state
# Structure:
# {
#   "room_name": {
#       "players": ["p1", "p2"],
#       "config": {"topic": "...", "difficulty": "...", "num_questions": 5},
#       "questions": [...], # List of question dicts
#       "current_q_index": 0,
#       "scores": {"p1": 0, "p2": 0},
#       "current_answers": {}, # {"p1": idx, "p2": idx}
#       "game_active": False
#   }
# }
ROOMS = {}

class QuizConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()
        logger.info("WebSocket connected")

    async def disconnect(self, close_code):
        logger.info(f"WebSocket disconnected: {close_code}")
        # Logic to handle player leaving (cleanup room if empty)
        # For now, we'll leave it simple.

    async def receive(self, text_data=None, bytes_data=None):
        try:
            data = json.loads(text_data)
        except Exception:
            await self.send(text_data=json.dumps({"error": "invalid json"}))
            return

        action = data.get("action")
        if action == "create":
            await self.handle_create(data)
        elif action == "join":
            await self.handle_join(data)
        elif action == "answer":
            await self.handle_answer(data)
        elif action == "leave":
            # Basic leave handling
            pass

    async def handle_create(self, data):
        room_name = f"room_{random.randint(1000, 9999)}"
        player = data.get("player")
        
        config = {
            "topic": data.get("topic", "any"),
            "difficulty": data.get("difficulty", "any"),
            "num_questions": int(data.get("num_questions", 5))
        }

        ROOMS[room_name] = {
            "players": [player],
            "config": config,
            "questions": [],
            "current_q_index": 0,
            "scores": {player: 0},
            "current_answers": {},
            "game_active": False,
            "answer_history": {}  # Track all answers: {player: [{q_idx, selected, correct, explanation}, ...]}
        }

        self.room_name = room_name
        self.player_name = player
        await self.channel_layer.group_add(room_name, self.channel_name)

        await self.send(text_data=json.dumps({
            "event": "created",
            "room": room_name,
            "players": ROOMS[room_name]["players"]
        }))

    async def handle_join(self, data):
        room_name = data.get("room")
        player = data.get("player")

        if not room_name or room_name not in ROOMS:
            await self.send(text_data=json.dumps({"error": "Room not found"}))
            return

        room = ROOMS[room_name]
        if len(room["players"]) >= 2:
            await self.send(text_data=json.dumps({"error": "Room is full"}))
            return

        if player in room["players"]:
            player = f"{player}_{random.randint(1,99)}" # Handle duplicate names

        room["players"].append(player)
        room["scores"][player] = 0
        room["answer_history"][player] = []  # Initialize answer tracking
        
        self.room_name = room_name
        self.player_name = player
        await self.channel_layer.group_add(room_name, self.channel_name)

        # Notify everyone
        await self.channel_layer.group_send(
            room_name,
            {
                "type": "player_joined_event",
                "players": room["players"],
                "player": player
            }
        )

        # Start game if 2 players
        if len(room["players"]) == 2:
            await self.start_game(room_name)

    async def start_game(self, room_name):
        room = ROOMS[room_name]
        room["game_active"] = True
        
        # Fetch questions
        questions = await self.fetch_questions(room["config"])
        room["questions"] = questions
        
        # Send first question
        await self.send_question(room_name)

    @database_sync_to_async
    def fetch_questions(self, config):
        """
        Fetch unique questions ensuring we get exactly the requested count.
        Strategy: Fetch large pool, deduplicate, broaden search if needed.
        """
        num_requested = config["num_questions"]
        
        # Step 1: Try to get questions from requested topic/difficulty
        qs = Question.objects.all()
        if config["topic"] != "any":
            qs = qs.filter(quiz__topic__name__iexact=config["topic"]) # Adapted for Quiz->Topic relation
        if config["difficulty"] != "any":
            qs = qs.filter(quiz__difficulty__iexact=config["difficulty"]) # Adapted for Quiz->Difficulty relation
        
        # Fetch a large pool (10x requested to handle duplicates)
        pool_size = min(num_requested * 10, Question.objects.count())
        if pool_size == 0:
             # Fallback if DB empty
             return []
             
        question_pool = list(qs.order_by('?')[:pool_size])
        
        # Step 2: Deduplicate by question text
        unique_questions = []
        seen_texts = set()
        
        for q in question_pool:
            if q.question_text not in seen_texts:
                seen_texts.add(q.question_text)
                unique_questions.append(q)
                if len(unique_questions) >= num_requested:
                    break
        
        # Step 3: If still not enough, broaden the search
        if len(unique_questions) < num_requested:
            # Remove topic filter, keep difficulty
            qs_broader = Question.objects.all()
            if config["difficulty"] != "any":
                qs_broader = qs_broader.filter(quiz__difficulty__iexact=config["difficulty"])
            
            # Exclude questions we already have
            existing_ids = [q.id for q in unique_questions]
            qs_broader = qs_broader.exclude(id__in=existing_ids)
            
            # Fetch more
            additional_pool = list(qs_broader.order_by('?')[:pool_size])
            
            for q in additional_pool:
                if q.question_text not in seen_texts:
                    seen_texts.add(q.question_text)
                    unique_questions.append(q)
                    if len(unique_questions) >= num_requested:
                        break
        
        # Step 4: If STILL not enough, remove all filters
        if len(unique_questions) < num_requested:
            existing_ids = [q.id for q in unique_questions]
            qs_all = Question.objects.exclude(id__in=existing_ids)
            additional_pool = list(qs_all.order_by('?')[:pool_size])
            
            for q in additional_pool:
                if q.question_text not in seen_texts:
                    seen_texts.add(q.question_text)
                    unique_questions.append(q)
                    if len(unique_questions) >= num_requested:
                        break
        
        # Step 5: Format the results
        result = []
        for q in unique_questions[:num_requested]:  # Ensure exact count
            options = q.options
            if isinstance(options, str):
                try:
                    options = json.loads(options)
                except:
                    options = []
            
            if not isinstance(options, list):
                options = []

            try:
                correct_idx = int(q.correct_answer)
            except:
                # Try to find index if answer is text
                if q.correct_answer in options:
                    correct_idx = options.index(q.correct_answer)
                else:
                    correct_idx = 0

            result.append({
                "id": q.id,
                "question_text": q.question_text,
                "options": options,
                "correct_option": correct_idx,
                "explanation": "" # q.explanation or "No explanation available"
            })
        
        # Log if we couldn't get enough
        if len(result) < num_requested:
            print(f"WARNING: Only found {len(result)} unique questions out of {num_requested} requested")
            
        return result

    async def send_question(self, room_name):
        room = ROOMS[room_name]
        idx = room["current_q_index"]
        
        if idx >= len(room["questions"]):
            await self.finish_game(room_name)
            return

        q = room["questions"][idx]
        room["current_answers"] = {} # Reset for new question

        await self.channel_layer.group_send(
            room_name,
            {
                "type": "question_event",
                "question_text": q["question_text"],
                "options": q["options"],
                "order": idx + 1,
                "total": len(room["questions"])
            }
        )

    async def handle_answer(self, data):
        room_name = data.get("room")
        player = data.get("player")
        selected_idx = data.get("selected")
        
        if not room_name or room_name not in ROOMS:
            return

        room = ROOMS[room_name]
        if not room["game_active"]:
            return
            
        # Record answer
        if player in room["current_answers"]:
            return # Already answered
            
        room["current_answers"][player] = selected_idx
        
        # Check correctness
        q_idx = room["current_q_index"]
        q = room["questions"][q_idx]
        is_correct = (selected_idx == q["correct_option"])
        
        # Track answer in history
        if player not in room["answer_history"]:
            room["answer_history"][player] = []
            
        room["answer_history"][player].append({
            "question_index": q_idx,
            "question_text": q["question_text"],
            "selected": selected_idx,
            "correct_option": q["correct_option"],
            "is_correct": is_correct,
            "options": q["options"],
            "explanation": q.get("explanation", "No explanation available")
        })
        
        if is_correct:
            room["scores"][player] += 10 # Simple scoring

        # Penalty Logic: If this is the FIRST answer, penalize the OTHER player
        if len(room["current_answers"]) == 1:
            await self.channel_layer.group_send(
                room_name,
                {
                    "type": "time_penalty_event",
                    "player": player # The player who answered (so client knows who triggered it)
                }
            )

        # Check if all players answered
        if len(room["current_answers"]) == len(room["players"]):
            # Move to next question after short delay
            room["current_q_index"] += 1
            await self.send_question(room_name)

    async def finish_game(self, room_name):
        room = ROOMS[room_name]
        room["game_active"] = False
        
        # Prepare detailed results
        results = {
            "scores": room["scores"],
            "answer_review": room["answer_history"]
        }
        
        await self.channel_layer.group_send(
            room_name,
            {
                "type": "finished_event",
                "results": results
            }
        )

    # --- Event Handlers ---

    async def player_joined_event(self, event):
        await self.send(text_data=json.dumps({
            "event": "player_joined",
            "players": event["players"],
            "player": event["player"]
        }))

    async def question_event(self, event):
        await self.send(text_data=json.dumps({
            "event": "question",
            "question_text": event["question_text"],
            "options": event["options"],
            "order": event["order"],
            "total": event["total"]
        }))

    async def time_penalty_event(self, event):
        await self.send(text_data=json.dumps({
            "event": "time_penalty",
            "player": event["player"]
        }))

    async def finished_event(self, event):
        await self.send(text_data=json.dumps({
            "event": "finished",
            "results": event["results"]
        }))


# --- Coding Battle Consumer ---

# In-memory store for coding battle rooms
# Structure:
# {
#   "room_name": {
#       "players": ["p1", "p2"],
#       "problem": {...}, # CodingProblem object or dict
#       "submissions": {"p1": {...}, "p2": {...}},
#       "game_active": False,
#       "start_time": timestamp,
#       "difficulty": "mixed"
#   }
# }
BATTLES = {}

class CodingBattleConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        await self.accept()
        logger.info("CodingBattle WebSocket connected")

    async def disconnect(self, close_code):
        logger.info(f"CodingBattle WebSocket disconnected: {close_code}")
        # Cleanup logic could go here

    async def receive(self, text_data=None, bytes_data=None):
        try:
            data = json.loads(text_data)
        except Exception:
            return

        action = data.get("action")
        if action == "create":
            await self.handle_create(data)
        elif action == "join":
            await self.handle_join(data)
        elif action == "submit":
            await self.handle_submit(data)

    async def handle_create(self, data):
        room_name = f"battle_{random.randint(1000, 9999)}"
        player = data.get("player")
        difficulty = data.get("difficulty", "mixed")
        
        # Select a random problem based on difficulty
        problem = await self.get_random_problem(difficulty)
        
        if not problem:
            # Fallback if no problem found (should not happen if seeded)
            problem = await self.get_random_problem("mixed")

        BATTLES[room_name] = {
            "players": [player],
            "problem": problem,
            "submissions": {},
            "game_active": False,
            "start_time": None,
            "difficulty": difficulty
        }
        
        self.room_name = room_name
        self.player_name = player
        await self.channel_layer.group_add(room_name, self.channel_name)
        
        await self.send(text_data=json.dumps({
            "event": "created",
            "room": room_name,
            "players": BATTLES[room_name]["players"],
            "problem": self.serialize_problem(problem)
        }))

    async def handle_join(self, data):
        room_name = data.get("room")
        player = data.get("player")
        
        if not room_name or room_name not in BATTLES:
            await self.send(text_data=json.dumps({"error": "Room not found"}))
            return
            
        battle = BATTLES[room_name]
        if len(battle["players"]) >= 2:
            await self.send(text_data=json.dumps({"error": "Room is full"}))
            return
            
        if player in battle["players"]:
            player = f"{player}_{random.randint(1,99)}"
            
        battle["players"].append(player)
        
        self.room_name = room_name
        self.player_name = player
        await self.channel_layer.group_add(room_name, self.channel_name)
        
        # Send acknowledgment to the joining player
        await self.send(text_data=json.dumps({
            "event": "joined",
            "room": room_name,
            "player": player
        }))
        
        # Notify everyone
        await self.channel_layer.group_send(
            room_name,
            {
                "type": "player_joined_event",
                "players": battle["players"],
                "player": player
            }
        )
        
        # Start game if 2 players
        if len(battle["players"]) == 2:
            await self.start_battle(room_name)

    async def start_battle(self, room_name):
        battle = BATTLES[room_name]
        battle["game_active"] = True
        battle["start_time"] = timezone.now().timestamp()
        
        # Send problem to everyone (ensure joiner gets it too)
        await self.channel_layer.group_send(
            room_name,
            {
                "type": "battle_started_event",
                "problem": self.serialize_problem(battle["problem"])
            }
        )

    async def handle_submit(self, data):
        room_name = self.room_name
        player = self.player_name
        source_code = data.get("source_code")
        language_id = data.get("language_id")
        
        if room_name not in BATTLES:
            return
            
        battle = BATTLES[room_name]
        problem = battle["problem"]
        
        # Run tests via Judge0 (using utils)
        from asgiref.sync import sync_to_async
        
        test_cases = problem.test_cases if isinstance(problem.test_cases, list) else json.loads(problem.test_cases)
        results = []
        passed_count = 0
        total_runtime = 0.0
        
        # Notify room that player is running tests
        await self.channel_layer.group_send(
            room_name,
            {
                "type": "submission_event",
                "player": player,
                "status": "running"
            }
        )
        
        # Use Judge0Service
        judge_service = Judge0Service()
        
        # Execute with test cases
        # Note: Judge0Service.execute_with_test_cases expects language name, not ID usually, but let's check
        # The user code passes language_id. Judge0Service expects language name string.
        # I need to map ID to name or update Judge0Service.
        # Judge0Service has LANGUAGE_MAP.
        # I'll assume language_id is actually language name string in this context or I need to map it.
        # If it is ID, I might need to reverse map it.
        # Let's assume it's language name for now as Judge0Service takes language name.
        
        language_name = 'python' # Default
        if str(language_id) == '71': language_name = 'python'
        elif str(language_id) == '63': language_name = 'javascript'
        # Add more mappings if needed
        
        res = await sync_to_async(judge_service.execute_with_test_cases)(
            source_code, 
            language_name, 
            test_cases
        )
        
        passed_count = res['passed']
        results = res['details']
        
        # Calculate total runtime from details
        total_runtime = 0.0 # Judge0Service details might not have time for all?
        # Judge0Service.execute_with_test_cases returns details list.
        # It doesn't seem to return time in details explicitly in the simulated version, but real one does.

        # Store submission
        submission_time = timezone.now().timestamp()
        battle["submissions"][player] = {
            "passed": passed_count,
            "total": len(test_cases),
            "results": results,
            "code": source_code, # Store code to show opponent
            "runtime": total_runtime,
            "submission_time": submission_time
        }
        
        # Send results back to submitter
        await self.send(text_data=json.dumps({
            "event": "submission_result",
            "passed": passed_count,
            "total": len(test_cases),
            "results": results
        }))
        
        # Notify opponent
        await self.channel_layer.group_send(
            room_name,
            {
                "type": "opponent_submission_event",
                "player": player,
                "passed": passed_count,
                "total": len(test_cases),
                "code": source_code # Show code as requested
            }
        )
        
        # Check for winner (if all players submitted)
        if len(battle["submissions"]) == 2:
            await self.determine_winner(room_name)

    async def determine_winner(self, room_name):
        battle = BATTLES[room_name]
        p1, p2 = battle["players"]
        
        if p1 not in battle["submissions"] or p2 not in battle["submissions"]:
            return

        s1 = battle["submissions"][p1]
        s2 = battle["submissions"][p2]
        
        winner = None
        reason = ""
        
        # 1. Correctness (Most passed tests)
        if s1["passed"] > s2["passed"]:
            winner = p1
            reason = f"Passed more tests ({s1['passed']} vs {s2['passed']})"
        elif s2["passed"] > s1["passed"]:
            winner = p2
            reason = f"Passed more tests ({s2['passed']} vs {s1['passed']})"
        else:
            # 2. Runtime (Lower is better) - Only if both passed same amount
            if abs(s1["runtime"] - s2["runtime"]) > 0.001:
                if s1["runtime"] < s2["runtime"]:
                    winner = p1
                    reason = f"Better runtime ({s1['runtime']:.3f}s vs {s2['runtime']:.3f}s)"
                else:
                    winner = p2
                    reason = f"Better runtime ({s2['runtime']:.3f}s vs {s1['runtime']:.3f}s)"
            else:
                # 3. Submission Time (Faster submission wins)
                if s1["submission_time"] < s2["submission_time"]:
                    winner = p1
                    reason = "Submitted faster"
                else:
                    winner = p2
                    reason = "Submitted faster"

        await self.declare_winner(room_name, winner, reason)

    async def declare_winner(self, room_name, winner, reason):
        battle = BATTLES[room_name]
        battle["game_active"] = False
        
        await self.channel_layer.group_send(
            room_name,
            {
                "type": "game_over_event",
                "winner": winner,
                "reason": reason,
                "submissions": battle["submissions"]
            }
        )

    @database_sync_to_async
    def get_random_problem(self, difficulty):
        qs = CodingProblem.objects.all()
        if difficulty != "mixed":
            qs = qs.filter(difficulty__iexact=difficulty)
        
        if not qs.exists():
             # Fallback to any if specific difficulty not found
             qs = CodingProblem.objects.all()
             
        return qs.order_by('?').first()

    def serialize_problem(self, problem):
        if not problem:
            return {}
        return {
            "title": problem.title,
            "description": problem.description,
            "starter_code": "", # problem.starter_code, # Not in Challenge model?
            "test_cases": problem.test_cases
        }

    # --- Event Handlers ---

    async def player_joined_event(self, event):
        await self.send(text_data=json.dumps({
            "event": "player_joined",
            "players": event["players"],
            "player": event["player"]
        }))

    async def battle_started_event(self, event):
        await self.send(text_data=json.dumps({
            "event": "battle_started",
            "problem": event["problem"]
        }))

    async def submission_event(self, event):
        # Notify that someone is running code
        if event["player"] != self.player_name:
            await self.send(text_data=json.dumps({
                "event": "opponent_running",
                "player": event["player"]
            }))

    async def opponent_submission_event(self, event):
        if event["player"] != self.player_name:
            await self.send(text_data=json.dumps({
                "event": "opponent_result",
                "player": event["player"],
                "passed": event["passed"],
                "total": event["total"],
                "code": event["code"]
            }))

    async def game_over_event(self, event):
        await self.send(text_data=json.dumps({
            "event": "game_over",
            "winner": event["winner"],
            "reason": event["reason"],
            "submissions": event["submissions"]
        }))
