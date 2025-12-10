from channels.generic.websocket import AsyncWebsocketConsumer
import json
import asyncio
from .models import Battle, Submission, Challenge
from .services import Judge0Service
from channels.db import database_sync_to_async
from django.utils import timezone
from asgiref.sync import sync_to_async
from django.contrib.auth.models import User
from datetime import date

class CodeBattleConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.battle_code = self.scope['url_route']['kwargs'].get('battle_code')
        self.battle_id = None
        if self.battle_code:
            battle = await self.get_battle_by_code(self.battle_code)
            if battle:
                self.battle_id = battle.id
                self.battle_group_name = f'battle_{self.battle_id}'
            else:
                # Invalid code, perhaps disconnect or handle error
                await self.close()
                return
        else:
            self.battle_group_name = 'codebattle_lobby'
        self.user = self.scope['user']

        # Join group
        await self.channel_layer.group_add(
            self.battle_group_name,
            self.channel_name
        )

        await self.accept()

        if self.battle_id:
            # Send initial battle state with players
            battle_data = await self.get_battle_data(self.battle_id)
            players = []
            if battle_data['player1']:
                players.append({'username': battle_data['player1']})
            if battle_data['player2']:
                players.append({'username': battle_data['player2']})
            await self.send(json.dumps({
                "type": "initial_state",
                "battle": battle_data,
                "players": players
            }))
        else:
            # Lobby connection
            await self.send(json.dumps({
                "type": "connected",
                "message": "Connected to Coding Challenge Lobby"
            }))

    async def disconnect(self, close_code):
        # stop typing broadcast when leaving
        if self.battle_id:
            await self.channel_layer.group_send(
                self.battle_group_name,
                {
                    "type": "stop_typing",
                    "username": self.scope["user"].username
                }
            )

        await self.channel_layer.group_discard(
            self.battle_group_name,
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

        # SAFE TYPING SYNC (NO CHEATING)
        if msg_type == "typing":
            await self.channel_layer.group_send(
                self.battle_group_name,
                {
                    "type": "typing",
                    "username": user.username
                }
            )
            return

        if msg_type == "stop_typing":
            await self.channel_layer.group_send(
                self.battle_group_name,
                {
                    "type": "stop_typing",
                    "username": user.username
                }
            )
            return

        if self.battle_id:
            # Battle-specific messages
            if msg_type == "submit_code":
                await self.handle_submit_code(user, data)
            elif msg_type == "start_battle":
                await self.handle_start_battle(user, data)
            elif msg_type == "end_battle":
                await self.handle_end_battle(user, data)
            elif msg_type == "run_code":
                await self.handle_run_code(user, data)
        if msg_type == "set_ready":
            await self.handle_set_ready(user, data)
        elif msg_type == "tab_switch_warning":
            await self.channel_layer.group_send(
                self.battle_group_name,
                {
                    "type": "tab_warning",
                    "username": user.username
                }
            )
        else:
            # Lobby messages
            if msg_type == "get_challenges":
                await self.handle_get_challenges(user, data)
            elif msg_type == "create_battle":
                await self.handle_create_battle(user, data)
            elif msg_type == "join_battle":
                await self.handle_join_battle(user, data)
            elif msg_type == "join_battle_by_code":
                await self.handle_join_battle_by_code(user, data)
            elif msg_type == "leave_battle":
                await self.handle_leave_battle(user, data)
            elif msg_type == "load_challenge":
                await self.handle_load_challenge(user, data)

    async def handle_get_challenges(self, user, data):
        challenges = await self.get_challenges()
        await self.send(json.dumps({
            "type": "challenges_list",
            "challenges": challenges
        }))

    async def handle_create_battle(self, user, data):
        num_questions = data.get('num_questions', 5)
        level = data.get('level', 'medium')

        # Get random challenges based on level
        challenges = await self.get_challenges_by_level(level, num_questions)
        if not challenges:
            await self.send(json.dumps({"type": "error", "message": "No challenges available for this level"}))
            return

        # Create battle with challenges
        battle = await self.create_battle_with_challenges(user, challenges, num_questions, level)

        # Switch to battle room
        await self.channel_layer.group_discard(
            self.battle_group_name,
            self.channel_name
        )
        self.battle_group_name = f'battle_{battle.id}'
        await self.channel_layer.group_add(
            self.battle_group_name,
            self.channel_name
        )

        # Get battle data
        battle_data = await self.get_battle_data(battle.id)

        await self.send(json.dumps({
            "type": "battle_joined",
            "battle": battle_data
        }))

    async def handle_join_battle(self, user, data):
        challenge_id = data.get('challenge_id')
        if not challenge_id:
            await self.send(json.dumps({"type": "error", "message": "Challenge ID required"}))
            return

        battle = await self.join_or_create_battle(user, challenge_id)
        if battle:
            # Switch to battle room
            await self.channel_layer.group_discard(
                self.battle_group_name,
                self.channel_name
            )
            self.battle_group_name = f'battle_{battle.id}'
            await self.channel_layer.group_add(
                self.battle_group_name,
                self.channel_name
            )

            # Get fresh battle data after potential update
            battle_data = await self.get_battle_data(battle.id)

            await self.send(json.dumps({
                "type": "battle_joined",
                "battle": battle_data
            }))

            # Battle will start when explicitly triggered (not automatically when both players join)
            # Players need to wait in the room until ready

    async def handle_join_battle_by_code(self, user, data):
        battle_code = data.get('battle_code')
        if not battle_code:
            await self.send(json.dumps({"type": "error", "message": "Battle code required"}))
            return

        battle = await self.join_battle_by_code(user, battle_code)
        if battle:
            # Switch to battle room
            await self.channel_layer.group_discard(
                self.battle_group_name,
                self.channel_name
            )
            self.battle_group_name = f'battle_{battle.id}'
            await self.channel_layer.group_add(
                self.battle_group_name,
                self.channel_name
            )

            # Get fresh battle data after potential update
            battle_data = await self.get_battle_data(battle.id)

            await self.send(json.dumps({
                "type": "battle_joined",
                "battle": battle_data
            }))

            # Prepare players list
            players = []
            if battle_data['player1']:
                players.append({'username': battle_data['player1']})
            if battle_data['player2']:
                players.append({'username': battle_data['player2']})

            # Broadcast to other player that someone joined
            await self.channel_layer.group_send(
                self.battle_group_name,
                {
                    'type': 'player_joined',
                    'battle': battle_data,
                    'player': user.username,
                    'players': players
                }
            )

            # Send battle data update to all players in room
            await self.channel_layer.group_send(
                self.battle_group_name,
                {
                    'type': 'battle_data_update',
                    'battle': battle_data
                }
            )
        else:
            await self.send(json.dumps({
                "type": "error",
                "message": "Could not join battle. Battle may be full or not exist."
            }))

    async def handle_set_ready(self, user, data):
        ready = data.get('ready', True)
        await self.set_player_ready(self.battle_id, user, ready)

        # Get updated battle data
        battle_data = await self.get_battle_data(self.battle_id)

        # Broadcast ready status update
        await self.channel_layer.group_send(
            self.battle_group_name,
            {
                'type': 'ready_status_update',
                'battle': battle_data,
                'player': user.username,
                'ready': ready
            }
        )

        await self.send(json.dumps({
            "type": "ready_updated",
            "ready": ready,
            "battle": battle_data
        }))

    async def handle_leave_battle(self, user, data):
        # Leave current battle
        battle_code = self.battle_code
        await self.channel_layer.group_discard(
            self.battle_group_name,
            self.channel_name
        )
        self.battle_group_name = 'codebattle_lobby'
        await self.channel_layer.group_add(
            self.battle_group_name,
            self.channel_name
        )
        await self.send(json.dumps({
            "type": "left_battle"
        }))

        # Broadcast to the battle group that player left
        if battle_code:
            battle = await self.get_battle_by_code(battle_code)
            if battle:
                # Switch to battle group name using ID
                battle_group = f'battle_{battle.id}'
                players = []
                if battle.player1:
                    players.append({'username': battle.player1.username})
                if battle.player2 and battle.player2 != user:
                    players.append({'username': battle.player2.username})

                await self.channel_layer.group_send(
                    battle_group,
                    {
                        'type': 'player_left',
                        'username': user.username,
                        'players': players
                    }
                )

    async def handle_load_challenge(self, user, data):
        challenge_id = data.get('challenge_id')
        if not challenge_id:
            await self.send(json.dumps({"type": "error", "message": "Challenge ID required"}))
            return

        challenge = await self.get_challenge(challenge_id)
        if challenge:
            challenge_data = {
                'id': challenge.id,
                'title': challenge.title,
                'description': challenge.description,
                'problem_statement': challenge.problem_statement,
                'sample_io': challenge.sample_io,
                'difficulty': challenge.difficulty,
                'time_limit': challenge.time_limit
            }
            await self.send(json.dumps({
                "type": "challenge_loaded",
                "challenge": challenge_data
            }))
        else:
            await self.send(json.dumps({
                "type": "error",
                "message": "Challenge not found"
            }))

    async def handle_run_code(self, user, data):
        code = data.get('code')
        language = data.get('language')
        if not code or not language:
            await self.send(json.dumps({"type": "error", "message": "Code and language required"}))
            return

        # Broadcast to opponent that player is running code
        await self.channel_layer.group_send(
            self.battle_group_name,
            {
                'type': 'opponent_running_code',
                'username': user.username,
            }
        )

        # Get sample input from current challenge
        battle = await self.get_battle(self.battle_id)
        challenges = await sync_to_async(lambda b: list(b.challenges.all()))(battle)
        
        # Check if current challenge index is valid
        if battle.current_challenge_index >= len(challenges):
            await self.send(json.dumps({
                "type": "error", 
                "message": "All challenges have been completed. Battle is ending."
            }))
            return
        
        current_challenge = challenges[battle.current_challenge_index]
        sample_io = current_challenge.sample_io
        stdin = self.extract_sample_input(sample_io) if sample_io else ''

        # Execute with Judge0 using the new run_code method
        judge_service = Judge0Service()
        result = await sync_to_async(judge_service.run_code)(code, language, stdin)

        await self.send(json.dumps({
            "type": "code_result",
            "result": {
                "output": result['output'],
                "error": result['error'],
                "time": result['time'],
                "memory": result['memory']
            }
        }))

    async def handle_submit_code(self, user, data):
        code = data.get('code')
        # Allow empty code if it's a timeout signal
        is_timeout = data.get('is_timeout', False)
        if is_timeout and code is None:
            code = "" 
            
        language = data.get('language')
        if code is None or not language:
            await self.send(json.dumps({"type": "error", "message": "Code and language required"}))
            return

        # Get battle and current challenge
        battle = await self.get_battle(self.battle_id)
        
        try:
            current_challenge, test_cases = await self.get_current_challenge_and_test_cases(self.battle_id)
        except ValueError as e:
            # No more challenges available
            await self.send(json.dumps({
                "type": "error", 
                "message": f"All challenges have been completed. Battle is ending."
            }))
            return

        # Execute with Judge0
        judge_service = Judge0Service()
        result = await sync_to_async(judge_service.execute_with_test_cases)(code, language, test_cases)

        # Determine status
        print(f"\n=== CODE SUBMISSION DEBUG ===")
        print(f"User: {user.username}")
        print(f"Result: {result}")
        if result['passed'] == result['total']:
            status = 'accepted'
        elif any(detail.get('error') == 'Compilation error' for detail in result['details']):
            status = 'compilation_error'
        elif any(detail.get('error') == 'Time limit exceeded' for detail in result['details']):
            status = 'time_limit'
        else:
            status = 'wrong_answer'
        print(f"Status determined: {status}")
        print(f"Passed: {result['passed']}/{result['total']}")

        # Override status if it was a timeout and didn't pass
        if is_timeout and status != 'accepted':
            status = 'time_limit'
            print(f"Submission flagged as timeout. Forced status to: {status}")

        # Create submission with results
        submission = await self.create_submission_with_results(user, self.battle_id, current_challenge, code, language, status, result)

        # Calculate score (passed tests * 10 - execution time bonus)
        score = result['passed'] * 10
        if status == 'accepted':
            # Bonus for faster execution (assume average time)
            avg_time = sum(detail.get('time', 0) for detail in result['details']) / len(result['details'])
            score += max(0, 10 - int(avg_time * 100))  # Bonus up to 10 points

        # Update battle scores
        await self.update_battle_scores(self.battle_id, user, score)

        # Get updated battle data
        battle_data = await self.get_battle_data_with_scores(self.battle_id)

        # Prepare result summary
        result_summary = f"{result['passed']}/{result['total']} tests passed - {status}"

        # Send to submitter
        await self.send(json.dumps({
            "type": "submission_result",
            "result": result_summary,
            "status": status,
            "passed": result['passed'],
            "total": result['total'],
            "details": result['details']
        }))

        # Broadcast to group (opponent sees submission)
        await self.channel_layer.group_send(
            self.battle_group_name,
            {
                'type': 'opponent_submission',
                "username": user.username,
                "result": result_summary,
                "passed": result['passed'],
                "total": result['total'],
                "scores": battle_data['scores']
            }
        )

        # Broadcast score update
        await self.channel_layer.group_send(
            self.battle_group_name,
            {
                'type': 'battle_update',
                'scores': battle_data['scores']
            }
        )

        # Check if this is the first person to solve this question
        print(f"\n=== WINNER CHECK ===")
        print(f"Status: {status}")
        if status == 'accepted':
            print(f"Checking for winner... Challenge index: {battle_data['current_challenge_index']}")
            battle_updated = await self.check_and_set_question_winner(self.battle_id, battle_data['current_challenge_index'], user)
            print(f"Battle updated (is first winner): {battle_updated}")
            if battle_updated:
                # This player is the first to solve this question!
                print(f"✅ Broadcasting question_winner event for {user.username}")
                await self.channel_layer.group_send(
                    self.battle_group_name,
                    {
                        'type': 'question_winner',
                        'username': user.username,
                        'challenge_index': battle_data['current_challenge_index'],
                        'scores': battle_data['scores']
                    }
                )
                
                # Schedule automatic progression to next question after 5 seconds
                print(f"🚀 Scheduling auto-progression in 5 seconds...")
                asyncio.create_task(self.auto_progress_question(self.battle_id))
            else:
                print(f"❌ User {user.username} is not the first winner")
        else:
            print(f"Status is not 'accepted', skipping winner check")
            # Check if all players have finished (e.g. both timed out)
            should_progress = await self.check_if_all_players_finished(self.battle_id, battle_data['current_challenge_index'])
            if should_progress:
                print(f"⌛ All players finished (or timed out). Scheduling auto-progression...")
                asyncio.create_task(self.auto_progress_question(self.battle_id, battle_data['current_challenge_index']))

        
    async def handle_start_battle(self, user, data):
        # Only the host (player1) can start the battle
        battle = await self.get_battle(self.battle_id)
        if battle.player1 != user:
            await self.send(json.dumps({"type": "error", "message": "Only the host can start the battle"}))
            return

        await self.start_battle(self.battle_id)

        # Get updated battle data after starting
        battle_data = await self.get_battle_data(self.battle_id)

        await self.channel_layer.group_send(
            self.battle_group_name,
            {
                'type': 'battle_started',
                'battle': battle_data
            }
        )

    async def handle_end_battle(self, user, data):
        # End battle and compute results
        battle_data = await self.get_battle_data_with_scores(self.battle_id)
        scores = battle_data['scores']

        # Determine winner
        player1_score = scores.get(battle_data['player1'], 0)
        player2_score = scores.get(battle_data['player2'], 0) if battle_data['player2'] else 0

        if player1_score > player2_score:
            winner = battle_data['player1']
        elif player2_score > player1_score:
            winner = battle_data['player2']
        else:
            winner = 'tie'

        # Update battle
        await self.end_battle(self.battle_id, winner)

        results = {
            'winner': winner,
            'scores': scores
        }

        await self.channel_layer.group_send(
            self.battle_group_name,
            {
                'type': 'battle_ended',
                'results': results
            }
        )

    async def battle_update(self, event):
        await self.send(json.dumps({
            'type': 'battle_update',
            'scores': event['scores']
        }))

    async def battle_started(self, event):
        await self.send(json.dumps({
            'type': 'battle_started',
            'battle': event['battle']
        }))

    async def player_left(self, event):
        await self.send(json.dumps({
            'type': 'player_left',
            'username': event['username'],
            'players': event.get('players', [])
        }))

    async def battle_ended(self, event):
        await self.send(json.dumps({
            'type': 'ended',
            'results': event['results']
        }))

    async def player_joined(self, event):
        await self.send(json.dumps({
            'type': 'player_joined',
            'username': event['player'],
            'battle': event['battle'],
            'players': event.get('players', [])
        }))

    async def battle_data_update(self, event):
        await self.send(json.dumps({
            'type': 'battle_data_update',
            'battle': event['battle'],
            'players': event.get('players', [])
        }))

    async def ready_status_update(self, event):
        await self.send(json.dumps({
            'type': 'ready_status_update',
            'battle': event['battle'],
            'player': event['player'],
            'ready': event['ready']
        }))

    async def opponent_submission(self, event):
        await self.send(json.dumps({
            'type': 'opponent_submission',
            'username': event['username'],
            'result': event['result'],
            'passed': event['passed'],
            'total': event['total'],
            'scores': event['scores']
        }))

    async def next_challenge(self, event):
        await self.send(json.dumps({
            'type': 'next_challenge',
            'battle': event['battle']
        }))

    async def opponent_running_code(self, event):
        await self.send(json.dumps({
            'type': 'opponent_running_code',
            'username': event['username']
        }))

    async def question_winner(self, event):
        await self.send(json.dumps({
            'type': 'question_winner',
            'username': event['username'],
            'challenge_index': event['challenge_index'],
            'scores': event['scores']
        }))

    # =======================================================
    # ⚡️ TYPING BROADCAST HANDLERS (NO CODE LEAKING)
    # =======================================================
    async def typing(self, event):
        await self.send(json.dumps({
            "type": "typing",
            "username": event["username"]
        }))

    async def stop_typing(self, event):
        await self.send(json.dumps({
            "type": "stop_typing",
            "username": event["username"]
        }))

    async def tab_warning(self, event):
        await self.send(json.dumps({
            "type": "tab_warning",
            "username": event["username"]
        }))
    # =======================================================

    @database_sync_to_async
    def get_battle(self, battle_id):
        return Battle.objects.select_related('player1', 'player2').get(id=battle_id)

    @database_sync_to_async
    def get_battle_data(self, battle_id):
        battle = Battle.objects.get(id=battle_id)
        challenges = list(battle.challenges.all().values('id', 'title', 'description', 'problem_statement', 'sample_io', 'difficulty', 'time_limit'))
        current_challenge = challenges[battle.current_challenge_index] if challenges and battle.current_challenge_index < len(challenges) else None
        return {
            'id': battle.id,
            'player1': battle.player1.username,
            'player2': battle.player2.username if battle.player2 else None,
            'player1_ready': battle.player1_ready,
            'player2_ready': battle.player2_ready if battle.player2 else False,
            'challenges': challenges,
            'current_challenge': current_challenge,
            'current_challenge_index': battle.current_challenge_index,
            'status': battle.status,
            'battle_code': battle.battle_code,
            'scores': battle.scores or {},
            'started_at': battle.started_at.isoformat() if battle.started_at else None,
        }

    @database_sync_to_async
    def get_battle_data_by_code(self, battle_code):
        battle = Battle.objects.get(battle_code=battle_code.upper())
        challenges = list(battle.challenges.all().values('id', 'title', 'description', 'problem_statement', 'sample_io', 'difficulty', 'time_limit'))
        current_challenge = challenges[battle.current_challenge_index] if challenges and battle.current_challenge_index < len(challenges) else None
        return {
            'id': battle.id,
            'player1': battle.player1.username,
            'player2': battle.player2.username if battle.player2 else None,
            'player1_ready': battle.player1_ready,
            'player2_ready': battle.player2_ready if battle.player2 else False,
            'challenges': challenges,
            'current_challenge': current_challenge,
            'current_challenge_index': battle.current_challenge_index,
            'status': battle.status,
            'battle_code': battle.battle_code,
            'scores': battle.scores or {},
            'started_at': battle.started_at.isoformat() if battle.started_at else None,
        }

    @database_sync_to_async
    def get_battle_by_code(self, battle_code):
        try:
            return Battle.objects.get(battle_code=battle_code.upper())
        except Battle.DoesNotExist:
            return None

    @database_sync_to_async
    def create_submission(self, user, battle_id, code, language):
        battle = Battle.objects.get(id=battle_id)
        submission = Submission.objects.create(
            user=user,
            challenge=battle.challenge,
            code=code,
            language=language
        )
        return submission

    @database_sync_to_async
    def start_battle(self, battle_id):
        battle = Battle.objects.get(id=battle_id)
        battle.status = 'in_progress'
        battle.started_at = timezone.now()
        battle.save()

    @database_sync_to_async
    def get_final_results(self, battle_id):
        battle = Battle.objects.get(id=battle_id)
        submissions = Submission.objects.filter(challenge=battle.challenge, user__in=[battle.player1, battle.player2])
        results = []
        for sub in submissions:
            results.append({
                'user': sub.user.username,
                'status': sub.status,
                'execution_time': sub.execution_time,
                'memory_used': sub.memory_used,
            })
        return results

    @database_sync_to_async
    def get_challenges(self):
        challenges = list(Challenge.objects.all().values(
            'id', 'title', 'description', 'difficulty', 'time_limit'
        ))
        return challenges

    @database_sync_to_async
    def get_challenges_by_level(self, level, num_questions):
        challenges = list(Challenge.objects.filter(difficulty=level).order_by('?')[:num_questions])
        return challenges

    @database_sync_to_async
    def create_battle_with_challenges(self, user, challenges, num_questions, level):
        battle = Battle.objects.create(
            player1=user,
            num_questions=num_questions,
            level=level
        )
        battle.challenges.set(challenges)
        battle.save()
        return battle

    @database_sync_to_async
    def join_or_create_battle(self, user, challenge_id):
        challenge = Challenge.objects.get(id=challenge_id)

        # Try to find an open battle for this challenge (only 2 players max)
        battle = Battle.objects.filter(
            challenge=challenge,
            status='waiting',
            player2__isnull=True
        ).exclude(player1=user).first()

        if battle:
            # Join existing battle as player2
            battle.player2 = user
            battle.save()
        else:
            # Check if user is already in a waiting battle for this challenge
            existing_battle = Battle.objects.filter(
                challenge=challenge,
                status='waiting',
                player1=user
            ).first()

            if existing_battle:
                # User is already waiting in a battle they created
                battle = existing_battle
            else:
                # Create new battle as player1 with a unique battle code
                import random
                import string
                battle_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
                while Battle.objects.filter(battle_code=battle_code).exists():
                    battle_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

                battle = Battle.objects.create(
                    player1=user,
                    challenge=challenge,
                    battle_code=battle_code
                )

        return battle

    @database_sync_to_async
    def join_battle_by_code(self, user, battle_code):
        try:
            battle = Battle.objects.get(battle_code=battle_code.upper())
        except Battle.DoesNotExist:
            return None

        # Check if battle is waiting and has space
        if battle.status != 'waiting' or battle.player2 is not None:
            return None

        # Check if user is not already in this battle
        if battle.player1 == user or battle.player2 == user:
            return battle  # Already in battle

        # Join as player2
        battle.player2 = user
        # Keep status as 'waiting' so players can manually start
        battle.save()
        return battle

    @database_sync_to_async
    def run_code_simulation(self, code, language):
        # Simple simulation - in real implementation, use Judge0
        if language == 'python':
            try:
                # Very basic execution simulation
                if 'print' in code:
                    return {"output": "Hello World", "error": None}
                else:
                    return {"output": "", "error": "No output"}
            except:
                return {"output": "", "error": "Execution error"}
        return {"output": "", "error": "Language not supported"}

    @database_sync_to_async
    def create_submission_with_results(self, user, battle_id, challenge, code, language, status, result):
        submission = Submission.objects.create(
            user=user,
            challenge=challenge,
            code=code,
            language=language,
            status=status,
            test_results=result['details']
        )
        return submission

    @database_sync_to_async
    def update_battle_scores(self, battle_id, user, score):
        battle = Battle.objects.get(id=battle_id)
        if not battle.scores:
            battle.scores = {}
        battle.scores[user.username] = battle.scores.get(user.username, 0) + score
        battle.save()

    @database_sync_to_async
    def get_battle_data_with_scores(self, battle_id):
        battle = Battle.objects.get(id=battle_id)
        challenges = list(battle.challenges.all().values('id', 'title', 'description', 'problem_statement', 'sample_io', 'difficulty', 'time_limit'))
        current_challenge = challenges[battle.current_challenge_index] if challenges and battle.current_challenge_index < len(challenges) else None
        data = {
            'id': battle.id,
            'player1': battle.player1.username,
            'player2': battle.player2.username if battle.player2 else None,
            'challenges': challenges,
            'current_challenge': current_challenge,
            'current_challenge_index': battle.current_challenge_index,
            'status': battle.status,
            'battle_code': battle.battle_code,
            'scores': battle.scores or {}
        }
        return data

    @database_sync_to_async
    def check_user_authorization(self, battle, user):
        return battle.player1 == user or battle.player2 == user

    @database_sync_to_async
    def get_challenge(self, challenge_id):
        try:
            return Challenge.objects.get(id=challenge_id)
        except Challenge.DoesNotExist:
            return None

    @database_sync_to_async
    def get_user(self, user_id):
        return User.objects.get(id=user_id)

    @database_sync_to_async
    def save_user(self, user):
        user.save()

    @database_sync_to_async
    def get_or_create_streak(self, user):
        from gamification.models import Streak
        streak, created = Streak.objects.get_or_create(user=user)
        return streak

    @database_sync_to_async
    def save_streak(self, streak):
        streak.save()

    @database_sync_to_async
    def end_battle(self, battle_id, winner):
        battle = Battle.objects.get(id=battle_id)
        battle.status = 'completed'
        battle.completed_at = timezone.now()
        if winner != 'tie':
            battle.winner = battle.player1 if winner == battle.player1.username else battle.player2
        battle.save()

        # Update user progress and streaks for both players
        if battle.player1:
            score1 = battle.scores.get(battle.player1.username, 0) if battle.scores else 0
            self.update_user_progress(battle.player1.id, score1)
            self.update_streak(battle.player1.id)

        if battle.player2:
            score2 = battle.scores.get(battle.player2.username, 0) if battle.scores else 0
            self.update_user_progress(battle.player2.id, score2)
            self.update_streak(battle.player2.id)

    @database_sync_to_async
    def update_user_progress(self, user_id, score):
        from gamification.models import UserProgress
        progress, created = UserProgress.objects.get_or_create(user_id=user_id)
        progress.quizzes_completed += 1
        progress.total_score += score
        progress.average_score = progress.total_score / progress.quizzes_completed
        progress.xp += score * 10
        progress.level = progress.total_score // 100 + 1
        progress.save()

    @database_sync_to_async
    def update_streak(self, user_id):
        from gamification.models import Streak
        from datetime import date
        streak, created = Streak.objects.get_or_create(user_id=user_id)
        if streak.last_activity != date.today():
            streak.current_streak += 1
            if streak.current_streak > streak.longest_streak:
                streak.longest_streak = streak.current_streak
        streak.save()

    @database_sync_to_async
    def get_current_challenge_and_test_cases(self, battle_id):
        battle = Battle.objects.get(id=battle_id)
        challenges = battle.challenges.all()
        total_challenges = challenges.count()
        
        # Check if current_challenge_index is within valid bounds
        if battle.current_challenge_index >= total_challenges:
            raise ValueError(f"Battle has no more challenges. Current index: {battle.current_challenge_index}, Total: {total_challenges}")
        
        current_challenge = challenges[battle.current_challenge_index]
        test_cases = current_challenge.test_cases
        return current_challenge, test_cases

    def extract_sample_input(self, sample_io):
        # Parse sample_io like "Input: hello world Output: 3" to extract input
        if 'Input:' in sample_io:
            input_part = sample_io.split('Input:')[1].split('Output:')[0].strip()
            return input_part
        return ''

    @database_sync_to_async
    def set_player_ready(self, battle_id, user, ready):
        battle = Battle.objects.get(id=battle_id)
        if battle.player1 == user:
            battle.player1_ready = ready
        elif battle.player2 == user:
            battle.player2_ready = ready
        else:
            raise ValueError("User is not a player in this battle")
        battle.save()

    @database_sync_to_async
    def check_and_set_question_winner(self, battle_id, challenge_index, user):
        """
        Check if this is the first person to solve a question.
        Returns True if this player is the first winner, False otherwise.
        """
        battle = Battle.objects.get(id=battle_id)
        
        # Initialize question_winners if it doesn't exist
        if not battle.question_winners:
            battle.question_winners = {}
        
        # Check if this question already has a winner
        challenge_key = str(challenge_index)
        if challenge_key in battle.question_winners:
            # Question already solved by someone
            return False
        
        # This is the first person to solve it!
        battle.question_winners[challenge_key] = user.username
        battle.save()
        return True

    async def auto_progress_question(self, battle_id, expected_index=None):
        """
        Automatically progress to the next question after a delay.
        Called after a winner is determined for the current question.
        """
        # Wait 5 seconds to allow players to view the winner popup
        await asyncio.sleep(5)
        
        # Advance to next question
        has_more_questions = await self.advance_to_next_question(battle_id, expected_index)
        
        if has_more_questions:
            # Broadcast next challenge event
            battle_data = await self.get_battle_data(battle_id)
            await self.channel_layer.group_send(
                f'battle_{battle_id}',
                {
                    'type': 'next_challenge',
                    'battle': battle_data
                }
            )
        else:
            # All questions completed, end the battle
            battle_data = await self.get_battle_data_with_scores(battle_id)
            scores = battle_data['scores']
            
            # Determine winner
            player1_score = scores.get(battle_data['player1'], 0)
            player2_score = scores.get(battle_data['player2'], 0) if battle_data['player2'] else 0
            
            if player1_score > player2_score:
                winner = battle_data['player1']
            elif player2_score > player1_score:
                winner = battle_data['player2']
            else:
                winner = 'tie'
            
            # Update battle status
            await self.end_battle(battle_id, winner)
            
            # Create leaderboard array sorted by score
            leaderboard = []
            for username, score in scores.items():
                leaderboard.append({
                    'user': username,
                    'score': score
                })
            
            # Sort by score descending
            leaderboard.sort(key=lambda x: x['score'], reverse=True)
            
            # Add rank to each entry
            for i, entry in enumerate(leaderboard):
                entry['rank'] = i + 1
            
            results = {
                'winner': winner,
                'scores': scores,
                'leaderboard': leaderboard
            }
            
            # Broadcast battle ended event
            await self.channel_layer.group_send(
                f'battle_{battle_id}',
                {
                    'type': 'battle_ended',
                    'results': results
                }
            )

    @database_sync_to_async
    def advance_to_next_question(self, battle_id, expected_index=None):
        """
        Increment the current challenge index.
        Returns True if there are more questions, False if all completed.
        If expected_index is provided, only increment if it matches current index (optimistic locking).
        """
        battle = Battle.objects.get(id=battle_id)
        
        # Optimistic locking check
        if expected_index is not None and battle.current_challenge_index != expected_index:
            print(f"Skipping advance: Current index {battle.current_challenge_index} != Expected {expected_index}")
            # verify if we are still within bounds or finished
            total_questions = battle.challenges.count()
            return battle.current_challenge_index < total_questions

        total_questions = battle.challenges.count()
        
        # Increment current challenge index
        battle.current_challenge_index += 1
        battle.save()
        
        # Check if there are more questions
        return battle.current_challenge_index < total_questions

    @database_sync_to_async
    def check_if_all_players_finished(self, battle_id, challenge_index):
        """
        Check if all players in the battle have either solved the question (accepted)
        or timed out (time_limit) for the current challenge.
        """
        battle = Battle.objects.get(id=battle_id)
        challenges = battle.challenges.all()
        if challenge_index >= len(challenges):
            return True # Already done
            
        current_challenge = challenges[challenge_index]
        
        players = [battle.player1]
        if battle.player2:
            players.append(battle.player2)
            
        finished_count = 0
        for player in players:
            # Check if player has a finishing submission for this challenge
            has_finished = Submission.objects.filter(
                user=player, 
                challenge=current_challenge,
                status__in=['accepted', 'time_limit']
            ).exists()
            
            if has_finished:
                finished_count += 1
                
        return finished_count == len(players)
