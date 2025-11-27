from channels.generic.websocket import AsyncWebsocketConsumer
import json
from .models import Room, Player
from .serializers import RoomSerializer
from asgiref.sync import sync_to_async
from channels.db import database_sync_to_async
from django.core.exceptions import ObjectDoesNotExist
import asyncio
from django.utils import timezone

class QuizRoomConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_code = self.scope['url_route']['kwargs']['room_code']
        self.room_group_name = f'quiz_room_{self.room_code}'
        self.user = self.scope['user']

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

        # Load room
        self.room = await self.get_room_by_code(self.room_code)
        if not self.room:
            await self.send(json.dumps({
                "type": "error",
                "message": "Room not found or inactive"
            }))
            await self.close()
            return

        # Send current room state to the new client
        room_data = await self.get_room_data(self.room.id)
        await self.send(json.dumps({
            "type": "room_state",
            "room": room_data
        }))

    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            await self.send(json.dumps({"type": "error", "message": "Invalid JSON"}))
            return

        user = self.scope["user"]
        if not user.is_authenticated:
            await self.send(json.dumps({"type": "error", "message": "Authentication required"}))
            return

        msg_type = data.get("type")

        if msg_type == "toggle_ready":
            await self.handle_toggle_ready(user, data)
        elif msg_type == "start_game":
            await self.handle_start_game(user, data)
        elif msg_type == "leave_room":
            await self.handle_leave_room(user, data)

    async def handle_toggle_ready(self, user, data):
        room_id = data.get('room_id')
        if not room_id:
            await self.send(json.dumps({"type": "error", "message": "Room ID required"}))
            return

        try:
            room = await self.get_room_by_id(room_id)
            player = await self.get_player(user.id, room_id)

            if not player:
                await self.send(json.dumps({"type": "error", "message": "Player not in room"}))
                return

            # Toggle ready status
            player.is_ready = not player.is_ready
            await self.save_player(player)

            # Broadcast the change
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'player_ready',
                    'message': f'{user.username} is {"ready" if player.is_ready else "not ready"}',
                    'room': await self.get_room_data(room_id)
                }
            )

        except Exception as e:
            await self.send(json.dumps({"type": "error", "message": str(e)}))

    async def handle_start_game(self, user, data):
        room_id = data.get('room_id')
        if not room_id:
            await self.send(json.dumps({"type": "error", "message": "Room ID required"}))
            return

        try:
            room = await self.get_room_by_id(room_id)
            player = await self.get_player(user.id, room_id)

            if not player:
                await self.send(json.dumps({"type": "error", "message": "Player not in room"}))
                return

            # Check if user is host
            if room.host_id != user.id:
                await self.send(json.dumps({"type": "error", "message": "Only host can start the game"}))
                return

            # Check if all players are ready
            players = await self.get_room_players(room_id)
            if not all(p.is_ready for p in players):
                await self.send(json.dumps({"type": "error", "message": "All players must be ready to start"}))
                return

            # Check minimum players
            if len(players) < 2:
                await self.send(json.dumps({"type": "error", "message": "Need at least 2 players to start"}))
                return

            # Generate quiz and start game
            from quizzes.services import QuizGenerationService
            quiz_service = QuizGenerationService()
            quiz = await self.generate_quiz(room.topic_id, room.num_questions, room.level, user)

            # Update room state
            room.quiz_id = quiz.id
            room.quiz_state = 'active'
            room.started_at = timezone.now()
            await self.save_room(room)

            # Broadcast game started
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'game_started',
                    'message': 'Game started!',
                    'quiz_id': quiz.id
                }
            )

        except Exception as e:
            await self.send(json.dumps({"type": "error", "message": str(e)}))

    async def handle_leave_room(self, user, data):
        room_id = data.get('room_id')
        if not room_id:
            await self.send(json.dumps({"type": "error", "message": "Room ID required"}))
            return

        try:
            room = await self.get_room_by_id(room_id)
            player = await self.get_player(user.id, room_id)

            if not player:
                await self.send(json.dumps({"type": "error", "message": "Player not in room"}))
                return

            # If player is host and there are other players, assign new host
            players = await self.get_room_players(room_id)
            if len(players) > 1 and room.host_id == user.id:
                # Assign new host (first non-leaving player)
                new_host = next(p for p in players if p.user_id != user.id)
                room.host_id = new_host.user_id
                await self.save_room(room)

            # Remove player
            await self.delete_player(player)

            # If room is empty, delete it
            remaining_players = await self.get_room_players(room_id)
            if len(remaining_players) == 0:
                await self.delete_room(room)
            else:
                # Broadcast player left
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        'type': 'player_left',
                        'message': f'{user.username} left the room',
                        'room': await self.get_room_data(room_id)
                    }
                )

            await self.send(json.dumps({"type": "success", "message": "Left room successfully"}))

        except Exception as e:
            await self.send(json.dumps({"type": "error", "message": str(e)}))

    # Event handlers for group messages
    async def player_joined(self, event):
        await self.send(json.dumps({
            'type': 'player_joined',
            'message': event['message'],
            'room': event['room']
        }))

    async def player_ready(self, event):
        await self.send(json.dumps({
            'type': 'player_ready',
            'message': event['message'],
            'room': event['room']
        }))

    async def player_left(self, event):
        await self.send(json.dumps({
            'type': 'player_left',
            'message': event['message'],
            'room': event['room']
        }))

    async def game_started(self, event):
        await self.send(json.dumps({
            'type': 'game_started',
            'message': event['message'],
            'quiz_id': event['quiz_id']
        }))

    # Database helpers
    @database_sync_to_async
    def get_room_by_code(self, code):
        try:
            return Room.objects.get(room_code=code, is_active=True)
        except Room.DoesNotExist:
            return None

    @database_sync_to_async
    def get_room_by_id(self, room_id):
        try:
            return Room.objects.get(id=room_id)
        except Room.DoesNotExist:
            return None

    @database_sync_to_async
    def get_room_data(self, room_id):
        room = Room.objects.get(id=room_id)
        return RoomSerializer(room).data

    @database_sync_to_async
    def get_room_players(self, room_id):
        room = Room.objects.get(id=room_id)
        return list(room.player_set.all())

    @database_sync_to_async
    def get_player(self, user_id, room_id):
        try:
            return Player.objects.get(user_id=user_id, room_id=room_id)
        except Player.DoesNotExist:
            return None

    @database_sync_to_async
    def save_player(self, player):
        player.save()

    @database_sync_to_async
    def save_room(self, room):
        room.save()

    @database_sync_to_async
    def delete_player(self, player):
        player.delete()

    @database_sync_to_async
    def delete_room(self, room):
        room.delete()

    @database_sync_to_async
    def generate_quiz(self, topic_id, num_questions, difficulty, user):
        from quizzes.services import QuizGenerationService
        quiz_service = QuizGenerationService()
        return quiz_service.generate_quiz(
            topic_id=topic_id,
            num_questions=num_questions,
            difficulty=difficulty,
            user=user
        )

class GeoGuessrQuizConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.room_code = self.scope['url_route']['kwargs']['room_code']
        self.quiz_group_name = f'quiz_room_{self.room_code}'
        self.user = self.scope['user']

        # Per-connection state
        self.answered_players = set()
        self.timer_task = None
        self.current_timer_duration = None
        self.total_players = 0

        # Join quiz group
        await self.channel_layer.group_add(
            self.quiz_group_name,
            self.channel_name
        )

        await self.accept()

        # Load room
        self.room = await self.get_room_by_code(self.room_code)
        if not self.room:
            await self.send(json.dumps({
                "type": "error",
                "message": "Room not found or inactive"
            }))
            await self.close()
            return

        self.quiz_id = self.room.quiz_id
        players = await self.get_room_players(self.room.id)
        self.total_players = len(players)

        if self.quiz_id and self.room.started_at:
            quiz_data = await self.get_quiz_data(self.quiz_id)
            current_q = self.room.current_question or 0

            # Initial payload to this client
            await self.send(json.dumps({
                "type": "quiz_start",
                "quiz": quiz_data,
                "total_players": self.total_players,
                "current_question": current_q,
                "timer_duration": self.room.timer_duration
            }))

            # If this is the first question and round not started yet -> start it
            if self.room.round_state in (None, "", "idle"):
                await self.start_question_timer(current_q)
        else:
            # Game not started yet
            await self.send(json.dumps({
                "type": "waiting_for_game",
                "message": "Waiting for the host to start the game..."
            }))

        # Notify others that a player joined the quiz
        if self.user.is_authenticated:
            await self.channel_layer.group_send(
                self.quiz_group_name,
                {
                    "type": "player_joined_quiz",
                    "user": self.user.username,
                    "total_players": self.total_players
                }
            )

    async def disconnect(self, close_code):
        # Cancel timer task if running
        if self.timer_task and not self.timer_task.done():
            self.timer_task.cancel()

        # Leave quiz group
        await self.channel_layer.group_discard(
            self.quiz_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            await self.send(json.dumps({"type": "error", "message": "Invalid JSON"}))
            return

        user = self.scope["user"]
        if not user.is_authenticated:
            await self.send(json.dumps({"type": "error", "message": "Authentication required"}))
            return

        msg_type = data.get("type")

        if msg_type == "submit_answer":
            await self.handle_submit_answer(user, data)
        elif msg_type == "time_up":
            # Client can signal when their local time hits zero,
            # but server remains authoritative.
            room = await self.get_room_by_code(self.room_code)
            if room and room.round_state == "active":
                await self.end_round_normal(room.id, room.current_question or 0)

    # -------------------------------------------------------------------------
    #  ROUND / TIMER LOGIC
    # -------------------------------------------------------------------------

    async def start_question_timer(self, question_index: int):
        """
        Start the timer and broadcast a new question to all players.
        """
        room = await self.get_room_by_code(self.room_code)
        if not room or not room.quiz_id:
            return

        # Set round active in DB
        room = await self.set_round_active(room.id)

        # Reset in-memory state
        self.answered_players.clear()
        self.current_timer_duration = room.timer_duration  # e.g., 20 seconds

        # Clear previous answers for all players in the room
        await self.clear_player_answers(room.id)

        # Get question data
        quiz_data = await self.get_quiz_data(room.quiz_id)
        questions = quiz_data.get("questions", [])
        if question_index >= len(questions):
            return

        question = questions[question_index]

        # Tell everyone a new question started
        await self.channel_layer.group_send(
            self.quiz_group_name,
            {
                "type": "new_question",
                "question_index": question_index,
                "question": question,
                "timer_duration": self.current_timer_duration,
            }
        )

        # Start a background timer
        self.timer_task = asyncio.create_task(
            self.broadcast_timer(room.id, question_index, self.current_timer_duration)
        )

    async def broadcast_timer(self, room_id: int, question_index: int, duration: int):
        """
        Broadcast timer updates every second. When it hits 0, end the round
        if it's still active.
        """
        try:
            for remaining in range(duration, -1, -1):
                # Broadcast to all clients
                await self.channel_layer.group_send(
                    self.quiz_group_name,
                    {
                        "type": "timer",
                        "remaining": remaining,
                    }
                )

                if remaining == 0:
                    room = await self.get_room_by_id(room_id)
                    if room and room.round_state == "active":
                        await self.end_round_normal(room_id, question_index)
                    break

                await asyncio.sleep(1)
        except asyncio.CancelledError:
            # Timer cancelled because round ended early
            return

    async def handle_submit_answer(self, user, data: dict):
        """
        Handle answer submission from a player:
        - Save their answer & time_used
        - GeoGuessr-style: On first answer, clamp effective timer
        - When all players answered -> end round immediately
        """
        question_index = data.get("question_index")
        answer = data.get("answer")

        if question_index is None or answer is None:
            await self.send(json.dumps({
                "type": "error",
                "message": "Question index and answer required"
            }))
            return

        room = await self.get_room_by_code(self.room_code)
        if not room or room.round_state != "active":
            await self.send(json.dumps({"type": "error", "message": "Round has ended"}))
            return

        # Calculate time used
        now = timezone.now()
        if room.round_start_time:
            time_used = int((now - room.round_start_time).total_seconds())
        else:
            time_used = 0

        # Save the player's answer + increment answered count in DB
        await self.set_player_answer(room.id, user.id, answer, time_used)
        self.answered_players.add(user.username)

        # GeoGuessr-style timer reduction: first answer clamps max duration
        if len(self.answered_players) == 1:
            # Effective max duration for everyone = time_used so far
            # e.g., if first player answered at 7 seconds, others effectively
            # only have 7 seconds window from question start.
            effective_duration = max(0, time_used)
            # Cancel previous timer and restart only for the remaining time
            if self.timer_task and not self.timer_task.done():
                self.timer_task.cancel()

            self.current_timer_duration = effective_duration or 1  # avoid 0
            self.timer_task = asyncio.create_task(
                self.broadcast_timer(room.id, question_index, self.current_timer_duration)
            )

            # Inform all players that timer has been reduced
            await self.channel_layer.group_send(
                self.quiz_group_name,
                {
                    "type": "timer_reduced",
                    "new_duration": self.current_timer_duration,
                    "triggered_by": user.username,
                }
            )

        # Notify all that someone answered
        await self.channel_layer.group_send(
            self.quiz_group_name,
            {
                "type": "player_answered",
                "user": user.username,
                "question_index": question_index,
                "answered_count": len(self.answered_players),
                "total_players": self.total_players,
                "time_used": time_used,
            }
        )

        # If all players answered, end the round immediately
        if len(self.answered_players) >= self.total_players:
            await self.end_round_immediately(room.id, question_index)

    async def end_round_immediately(self, room_id: int, question_index: int):
        """
        Called when all players have answered early.
        """
        if self.timer_task and not self.timer_task.done():
            self.timer_task.cancel()

        await self.end_round_common(room_id, question_index)

    async def end_round_normal(self, room_id: int, question_index: int):
        """
        Called when timer hits zero.
        """
        # Set round state to complete in DB
        await self.set_round_state(room_id, "complete")
        await self.end_round_common(room_id, question_index)

    async def end_round_common(self, room_id: int, question_index: int):
        """
        Shared logic to compute results, broadcast them, and start review timer.
        """
        # Put room into "review" state
        await self.set_round_state(room_id, "review")

        # Compute results in DB-safe helper (includes scoring)
        correct_answer, player_results, leaderboard = await self.compute_round_results(
            room_id, question_index
        )

        # Broadcast round results (everyone sees answers + scores)
        await self.channel_layer.group_send(
            self.quiz_group_name,
            {
                "type": "round_result",
                "question_index": question_index,
                "correct_answer": correct_answer,
                "player_results": player_results,
                "leaderboard": leaderboard,
                "review_duration": 5,  # 5 seconds to review answers
            }
        )

        # 5-second review phase
        await self.start_review_phase(room_id, question_index)

    async def start_review_phase(self, room_id: int, question_index: int):
        """
        5 seconds where players can see answers, then move to next question.
        """
        # Notify review start
        await self.channel_layer.group_send(
            self.quiz_group_name,
            {
                "type": "review_start",
                "duration": 5,
            }
        )

        await asyncio.sleep(5)

        # Notify review end
        await self.channel_layer.group_send(
            self.quiz_group_name,
            {
                "type": "review_end",
            }
        )

        # Move to next question or finish quiz
        await self.move_to_next_question(room_id, question_index)

    async def move_to_next_question(self, room_id: int, current_question_index: int):
        room = await self.get_room_by_id(room_id)
        if not room or not room.quiz_id:
            return

        quiz_data = await self.get_quiz_data(room.quiz_id)
        questions = quiz_data.get("questions", [])
        next_index = current_question_index + 1

        if next_index >= len(questions):
            # Quiz finished
            await self.set_quiz_finished(room_id)
            final_leaderboard = await self.get_final_leaderboard(room_id)

            # Update user progress and streaks for all players
            players = await self.get_room_players(room_id)
            for player in players:
                score = player.score or 0
                await self.update_user_progress(player.user_id, score)
                await self.update_streak(player.user_id)

            await self.channel_layer.group_send(
                self.quiz_group_name,
                {
                    "type": "quiz_finished",
                    "message": "Quiz completed!",
                    "final_leaderboard": final_leaderboard,
                }
            )
        else:
            # Update current question in DB
            await self.set_current_question(room_id, next_index)
            # Start next question
            await self.start_question_timer(next_index)

    # -------------------------------------------------------------------------
    #  EVENT HANDLERS (group messages -> client)
    # -------------------------------------------------------------------------

    async def player_joined_quiz(self, event):
        await self.send(json.dumps({
            "type": "player_joined_quiz",
            "user": event["user"],
            "total_players": event["total_players"],
        }))

    async def timer(self, event):
        await self.send(json.dumps({
            "type": "timer",
            "remaining": event["remaining"],
        }))

    async def timer_reduced(self, event):
        await self.send(json.dumps({
            "type": "timer_reduced",
            "new_duration": event["new_duration"],
            "triggered_by": event["triggered_by"],
        }))

    async def new_question(self, event):
        await self.send(json.dumps({
            "type": "new_question",
            "question_index": event["question_index"],
            "question": event["question"],
            "timer_duration": event["timer_duration"],
        }))

    async def player_answered(self, event):
        await self.send(json.dumps({
            "type": "player_answered",
            "user": event["user"],
            "question_index": event["question_index"],
            "answered_count": event["answered_count"],
            "total_players": event["total_players"],
            "time_used": event["time_used"],
        }))

    async def round_result(self, event):
        await self.send(json.dumps({
            "type": "round_result",
            "question_index": event["question_index"],
            "correct_answer": event["correct_answer"],
            "player_results": event["player_results"],
            "leaderboard": event["leaderboard"],
            "review_duration": event["review_duration"],
        }))

    async def review_start(self, event):
        await self.send(json.dumps({
            "type": "review_start",
            "duration": event["duration"],
        }))

    async def review_end(self, event):
        await self.send(json.dumps({
            "type": "review_end",
        }))

    async def quiz_finished(self, event):
        await self.send(json.dumps({
            "type": "quiz_finished",
            "message": event["message"],
            "final_leaderboard": event.get("final_leaderboard", []),
        }))

    # -------------------------------------------------------------------------
    #  DB HELPERS (ALL ORM WRAPPED)
    # -------------------------------------------------------------------------

    @database_sync_to_async
    def get_room_by_code(self, code):
        try:
            return Room.objects.get(room_code=code, is_active=True)
        except Room.DoesNotExist:
            return None

    @database_sync_to_async
    def get_room_by_id(self, room_id):
        try:
            return Room.objects.get(id=room_id)
        except Room.DoesNotExist:
            return None

    @database_sync_to_async
    def get_room_players(self, room_id):
        room = Room.objects.get(id=room_id)
        return list(room.player_set.all())

    @database_sync_to_async
    def set_round_active(self, room_id):
        room = Room.objects.get(id=room_id)
        room.round_start_time = timezone.now()
        room.round_state = "active"
        room.answered_count = 0
        room.save()
        return room

    @database_sync_to_async
    def set_round_state(self, room_id, state: str):
        room = Room.objects.get(id=room_id)
        room.round_state = state
        room.save()

    @database_sync_to_async
    def set_player_answer(self, room_id, user_id, answer, time_used: int):
        room = Room.objects.get(id=room_id)
        player = Player.objects.get(room=room, user_id=user_id)
        player.current_answer = answer
        player.answer_timestamp = timezone.now()
        player.answer_time_used = time_used
        player.save()

        room.answered_count = (room.answered_count or 0) + 1
        room.save()

    @database_sync_to_async
    def clear_player_answers(self, room_id):
        room = Room.objects.get(id=room_id)
        for p in room.player_set.all():
            p.current_answer = None
            p.answer_timestamp = None
            p.answer_time_used = 0
            p.save()

    @database_sync_to_async
    def get_quiz_data(self, quiz_id):
        from quizzes.models import Quiz
        quiz = Quiz.objects.get(id=quiz_id)
        questions = []
        for q in quiz.questions.all():
            if q.options:
                questions.append({
                    "id": q.id,
                    "question_text": q.question_text,
                    "question_type": q.question_type,
                    "answers": [
                        {"id": f"{q.id}_{i}", "answer_text": option}
                        for i, option in enumerate(q.options)
                    ],
                })

        return {
            "id": quiz.id,
            "title": quiz.title,
            "questions": questions,
            "time_limit": quiz.time_limit,
        }

    @database_sync_to_async
    def compute_round_results(self, room_id, question_index):
        """
        Compute correct answer, each player's result, and leaderboard.
        Also update scores.
        """
        from quizzes.models import Quiz

        room = Room.objects.get(id=room_id)
        quiz = Quiz.objects.get(id=room.quiz_id)
        question = quiz.questions.all()[question_index]
        correct_answer = question.correct_answer

        players = list(room.player_set.all())
        player_results = []
        leaderboard = []

        # Effective max duration for speed bonus:
        effective_duration = room.timer_duration or 1

        for player in players:
            selected = player.current_answer
            answer_time = player.answer_time_used or 0
            is_correct = (selected == correct_answer) if selected is not None else False

            score_gained = 0
            if is_correct:
                base_score = 100
                # Speed bonus: faster = higher bonus
                ratio = min(1.0, answer_time / float(effective_duration)) if effective_duration > 0 else 1.0
                speed_bonus = max(0, 100 - int(ratio * 100))
                score_gained = base_score + speed_bonus
                player.score = (player.score or 0) + score_gained
                player.save()

            player_results.append({
                "user": player.user.username,
                "selected": selected,
                "is_correct": is_correct,
                "answer_time": answer_time,
                "score_gained": score_gained,
            })
            leaderboard.append({
                "user": player.user.username,
                "score": player.score or 0,
            })

        leaderboard.sort(key=lambda x: x["score"], reverse=True)
        return correct_answer, player_results, leaderboard

    @database_sync_to_async
    def set_current_question(self, room_id, index: int):
        room = Room.objects.get(id=room_id)
        room.current_question = index
        room.round_state = "idle"
        room.save()

    @database_sync_to_async
    def set_quiz_finished(self, room_id):
        room = Room.objects.get(id=room_id)
        room.quiz_state = "finished"
        room.round_state = "finished"
        room.save()

    @database_sync_to_async
    def get_final_leaderboard(self, room_id):
        room = Room.objects.get(id=room_id)
        players = list(room.player_set.all())
        board = [
            {"user": p.user.username, "score": p.score or 0}
            for p in players
        ]
        board.sort(key=lambda x: x["score"], reverse=True)
        return board

    @database_sync_to_async
    def update_user_progress(self, user_id, score):
        from accounts.models import User
        from gamification.models import UserProgress
        user = User.objects.get(id=user_id)
        progress, created = UserProgress.objects.get_or_create(user=user)
        progress.total_score += score
        progress.quizzes_completed += 1
        progress.xp += score * 10
        progress.level = progress.total_score // 100 + 1
        progress.save()

    @database_sync_to_async
    def update_streak(self, user_id):
        from gamification.models import Streak
        from django.utils import timezone
        streak, created = Streak.objects.get_or_create(user_id=user_id)
        streak.current_streak += 1
        if streak.current_streak > streak.longest_streak:
            streak.longest_streak = streak.current_streak
        streak.last_activity = timezone.now()
        streak.save()
