from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import Challenge, Battle, Submission
from .serializers import ChallengeSerializer, BattleSerializer, SubmissionSerializer
from .services import Judge0Service
from gamification.services import AchievementService
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import json
from django.core.serializers.json import DjangoJSONEncoder

@login_required
def code_battle_home(request):
    challenges = Challenge.objects.all()
    battles = Battle.objects.all()
    return render(request, 'code_battle.html', {'challenges': challenges, 'battles': battles})

@login_required
def code_editor(request):
    battle_code = request.GET.get('battle_code')
    if not battle_code:
        messages.error(request, 'Battle code required.')
        return redirect('code_battle')

    try:
        battle = Battle.objects.get(battle_code=battle_code.upper())
        # Check if user is in this battle
        if request.user != battle.player1 and request.user != battle.player2:
            messages.error(request, 'You are not part of this battle.')
            return redirect('code_battle')

        # Check if battle is already completed
        if battle.status == 'completed':
            return redirect(f'/codebattle/results/?battle_code={battle_code}')

        # Fetch challenges and current challenge
        challenges = list(battle.challenges.all().values('id', 'title', 'description', 'problem_statement', 'sample_io', 'difficulty', 'time_limit', 'language'))
        current_challenge = challenges[battle.current_challenge_index] if challenges and battle.current_challenge_index < len(challenges) else None

        # Prepare battle data for JavaScript
        battle_data = {
            'id': battle.id,
            'player1': battle.player1.username if battle.player1 else None,
            'player2': battle.player2.username if battle.player2 else None,
            'player1_ready': battle.player1_ready,
            'player2_ready': battle.player2_ready,
            'status': battle.status,
            'battle_code': battle.battle_code,
            'scores': battle.scores or {},
        }

        context = {
            'battle': battle,
            'challenges': challenges,
            'current_challenge': current_challenge,
            'is_host': request.user == battle.player1,
            'battle_code': battle_code,
            'battle_data': battle_data,
        }
        return render(request, 'code_editor_new.html', context)
    except Battle.DoesNotExist:
        messages.error(request, 'Battle not found.')
        return redirect('code_battle')

@login_required
def code_battle_room(request, battle_code):
    try:
        battle = Battle.objects.get(battle_code=battle_code.upper())
        # Check if user is in this battle
        if request.user != battle.player1 and request.user != battle.player2:
            messages.error(request, 'You are not part of this battle.')
            return redirect('code_battle')
        is_host = request.user == battle.player1
        return render(request, 'code_battle_room.html', {'battle': battle, 'is_host': is_host})
    except Battle.DoesNotExist:
        messages.error(request, 'Battle not found.')
        return redirect('code_battle')

@require_POST
@csrf_exempt
def join_by_code(request):
    if not request.user.is_authenticated:
        return JsonResponse({'message': 'Authentication required'}, status=401)

    try:
        data = json.loads(request.body)
        battle_code = data.get('battle_code', '').upper()

        if not battle_code:
            return JsonResponse({'message': 'Battle code required'}, status=400)

        battle = get_object_or_404(Battle, battle_code=battle_code)

        if battle.status != 'waiting':
            return JsonResponse({'message': 'Battle is not available for joining'}, status=400)

        if battle.player2 is not None:
            return JsonResponse({'message': 'Battle is full'}, status=400)

        if battle.player1 == request.user:
            return JsonResponse({'message': 'You are already the host of this battle'}, status=400)

        battle.player2 = request.user
        battle.save()

        # Broadcast to the battle group that a player joined
        channel_layer = get_channel_layer()
        battle_group_name = f'battle_{battle.id}'
        players = []
        if battle.player1:
            players.append({'username': battle.player1.username})
        if battle.player2:
            players.append({'username': battle.player2.username})

        battle_data = {
            'id': battle.id,
            'player1': battle.player1.username,
            'player2': battle.player2.username if battle.player2 else None,
            'player1_ready': battle.player1_ready,
            'player2_ready': battle.player2_ready,
            'status': battle.status,
            'battle_code': battle.battle_code,
        }

        async_to_sync(channel_layer.group_send)(
            battle_group_name,
            {
                'type': 'player_joined',
                'battle': battle_data,
                'player': request.user.username,
                'players': players
            }
        )

        return JsonResponse({'message': 'Joined battle successfully'})

    except json.JSONDecodeError:
        return JsonResponse({'message': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'message': str(e)}, status=500)

class ChallengeListView(generics.ListAPIView):
    queryset = Challenge.objects.all()
    serializer_class = ChallengeSerializer
    permission_classes = [IsAuthenticated]

class ChallengeDetailView(generics.RetrieveAPIView):
    queryset = Challenge.objects.all()
    serializer_class = ChallengeSerializer
    permission_classes = [IsAuthenticated]

class BattleListCreateView(generics.ListCreateAPIView):
    queryset = Battle.objects.all()
    serializer_class = BattleSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(player1=self.request.user)

class JoinBattleView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            battle = Battle.objects.get(pk=pk)
            if battle.player2 is None and battle.player1 != request.user:
                battle.player2 = request.user
                battle.save()
                return Response({'message': 'Joined battle successfully'}, status=status.HTTP_200_OK)
            else:
                return Response({'message': 'Battle is full or you are already in it'}, status=status.HTTP_400_BAD_REQUEST)
        except Battle.DoesNotExist:
            return Response({'message': 'Battle not found'}, status=status.HTTP_404_NOT_FOUND)

class CreateBattleView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        num_questions = request.data.get('num_questions', 5)
        level = request.data.get('level', 'medium')

        if num_questions < 1 or num_questions > 10:
            return Response({'error': 'Number of questions must be between 1 and 10'}, status=status.HTTP_400_BAD_REQUEST)

        battle = Battle.objects.create(
            player1=request.user,
            num_questions=num_questions,
            level=level
        )

        # Select random challenges
        from .models import Challenge
        challenges = Challenge.objects.filter(difficulty=level).order_by('?')[:num_questions]
        battle.challenges.set(challenges)
        battle.save()

        serializer = BattleSerializer(battle)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

class SubmissionCreateView(generics.CreateAPIView):
    serializer_class = SubmissionSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        submission = serializer.save(user=self.request.user)
        # Submit to Judge0 for execution
        judge_service = Judge0Service()
        result = judge_service.submit_code(submission.code, submission.language, submission.challenge.test_cases)
        submission.result = result
        submission.save()

        # Award achievements for code battle completion
        AchievementService.award_achievement_on_codebattle_completion(self.request.user, submission, self.request)

        # Award achievements for code battle completion
        if 'passed' in result.lower():
            AchievementService.award_achievement_on_codebattle_completion(self.request.user, submission)


@login_required
def battle_results(request):
    battle_code = request.GET.get('battle_code')
    if not battle_code:
        messages.error(request, 'Battle code required.')
        return redirect('code_battle')

    try:
        battle = Battle.objects.get(battle_code=battle_code.upper())
        # Check if user is in this battle
        if request.user != battle.player1 and request.user != battle.player2:
            messages.error(request, 'You are not part of this battle.')
            return redirect('code_battle')

        # Get scores
        scores = battle.scores or {}
        player1_score = scores.get(battle.player1.username, 0) if battle.player1 else 0
        player2_score = scores.get(battle.player2.username, 0) if battle.player2 else 0

        # Determine winner based on scores
        if player1_score > player2_score:
            winner_player = battle.player1
        elif player2_score > player1_score:
            winner_player = battle.player2
        else:
            winner_player = None  # Tie

        winner_username = winner_player.username if winner_player else 'Tie'

        context = {
            'battle': battle,
            'player1': battle.player1,
            'player2': battle.player2 if battle.player2 else None,
            'player1_score': player1_score,
            'player2_score': player2_score,
            'winner': winner_username,
            'is_tie': winner_player is None,
            'is_winner': request.user == winner_player if winner_player else False,
        }
        return render(request, 'code_battle_results.html', context)
    except Battle.DoesNotExist:
        messages.error(request, 'Battle not found.')
        return redirect('code_battle')
