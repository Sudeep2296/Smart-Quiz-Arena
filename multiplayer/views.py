from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from .models import Room, Player
from .serializers import RoomSerializer, PlayerSerializer

@login_required
def multiplayer_home(request):
    from quizzes.models import Topic
    topics = Topic.objects.all()
    return render(request, 'multiplayer.html', {'topics': topics})

class RoomListCreateView(generics.ListCreateAPIView):
    queryset = Room.objects.all()
    serializer_class = RoomSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        room = serializer.save(host=self.request.user)
        # Add the host as a player in the room
        Player.objects.get_or_create(user=self.request.user, room=room)

class JoinRoomView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            room = Room.objects.get(pk=pk)
            if room.player_set.count() < room.max_players:
                player, created = Player.objects.get_or_create(user=request.user, room=room)
                if created:
                    return Response({'message': 'Joined room successfully'}, status=status.HTTP_200_OK)
                else:
                    return Response({'message': 'Already in room'}, status=status.HTTP_400_BAD_REQUEST)
            else:
                return Response({'message': 'Room is full'}, status=status.HTTP_400_BAD_REQUEST)
        except Room.DoesNotExist:
            return Response({'message': 'Room not found'}, status=status.HTTP_404_NOT_FOUND)


class JoinByCodeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        room_code = request.data.get('room_code')
        if not room_code:
            return Response({'error': 'Room code is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            room = Room.objects.get(room_code=room_code.upper())
            if room.player_set.count() < room.max_players:
                player, created = Player.objects.get_or_create(user=request.user, room=room)
                if created:
                    # Broadcast player joined
                    from channels.layers import get_channel_layer
                    from asgiref.sync import async_to_sync
                    channel_layer = get_channel_layer()
                    async_to_sync(channel_layer.group_send)(
                        f'quiz_room_{room.room_code}',
                        {
                            'type': 'player_joined',
                            'message': f'{request.user.username} joined the room',
                            'room': RoomSerializer(room).data
                        }
                    )
                    # Return room data for frontend to display
                    serializer = RoomSerializer(room)
                    return Response(serializer.data, status=status.HTTP_200_OK)
                else:
                    return Response({'error': 'Already in room'}, status=status.HTTP_400_BAD_REQUEST)
            else:
                return Response({'error': 'Room is full'}, status=status.HTTP_400_BAD_REQUEST)
        except Room.DoesNotExist:
            return Response({'error': 'Room not found'}, status=status.HTTP_404_NOT_FOUND)


class ToggleReadyView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        room_id = request.data.get('room_id')
        user_id = request.data.get('user_id')

        if not room_id or not user_id:
            return Response({'error': 'Room ID and User ID are required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            room = Room.objects.get(pk=room_id)
            player = Player.objects.get(user_id=user_id, room=room)
            player.is_ready = not player.is_ready
            player.save()

            # Broadcast the change via WebSocket
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f'quiz_room_{room.room_code}',
                {
                    'type': 'player_ready',
                    'message': f'{player.user.username} is {"ready" if player.is_ready else "not ready"}',
                    'room': RoomSerializer(room).data
                }
            )

            return Response({'is_ready': player.is_ready}, status=status.HTTP_200_OK)
        except Room.DoesNotExist:
            return Response({'error': 'Room not found'}, status=status.HTTP_404_NOT_FOUND)
        except Player.DoesNotExist:
            return Response({'error': 'Player not found in room'}, status=status.HTTP_404_NOT_FOUND)


class StartGameView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        room_id = request.data.get('room_id')
        user_id = request.data.get('user_id')

        if not room_id or not user_id:
            return Response({'error': 'Room ID and User ID are required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            room = Room.objects.get(pk=room_id)
            player = Player.objects.get(user_id=user_id, room=room)

            # Check if user is host
            if room.host_id != player.user_id:
                return Response({'error': 'Only host can start the game'}, status=status.HTTP_403_FORBIDDEN)

            # Check if all players are ready
            if not all(p.is_ready for p in room.player_set.all()):
                return Response({'error': 'All players must be ready to start'}, status=status.HTTP_400_BAD_REQUEST)

            # Check minimum players
            if room.player_set.count() < 2:
                return Response({'error': 'Need at least 2 players to start'}, status=status.HTTP_400_BAD_REQUEST)

            # Check if topic is selected
            if not room.topic:
                return Response({'error': 'Topic must be selected to start the game'}, status=status.HTTP_400_BAD_REQUEST)

            room.quiz_state = 'active'
            room.save()

            # Generate quiz and broadcast
            try:
                from quizzes.services import QuizGenerationService
                quiz_service = QuizGenerationService()
                quiz = quiz_service.generate_quiz(
                    topic_id=room.topic_id,
                    num_questions=room.num_questions,
                    difficulty=room.level,
                    user=request.user,
                    timeout=120  # Increased timeout to 120 seconds for multiplayer
                )
            except Exception as e:
                return Response({'error': f'Failed to generate quiz: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            # Assign quiz to room
            room.quiz = quiz

            # Set timer duration based on difficulty level
            if room.level == 'easy':
                room.timer_duration = 30  # 30 seconds for easy
            elif room.level == 'medium':
                room.timer_duration = 45  # 45 seconds for medium
            else:  # hard
                room.timer_duration = 60  # 60 seconds for hard

            room.save()

            # Broadcast game started
            from channels.layers import get_channel_layer
            from asgiref.sync import async_to_sync
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f'quiz_room_{room.room_code}',
                {
                    'type': 'game_started',
                    'message': 'Game started!',
                    'quiz_id': quiz.id
                }
            )

            return Response({'message': 'Game started successfully', 'quiz_id': quiz.id}, status=status.HTTP_200_OK)
        except Room.DoesNotExist:
            return Response({'error': 'Room not found'}, status=status.HTTP_404_NOT_FOUND)
        except Player.DoesNotExist:
            return Response({'error': 'Player not found in room'}, status=status.HTTP_404_NOT_FOUND)


class LeaveRoomView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        room_id = request.data.get('room_id')
        user_id = request.data.get('user_id')

        if not room_id or not user_id:
            return Response({'error': 'Room ID and User ID are required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            room = Room.objects.get(pk=room_id)
            player = Player.objects.get(user_id=user_id, room=room)

            # If player is host and there are other players, assign new host
            if player.is_host and room.player_set.count() > 1:
                new_host = room.player_set.exclude(user=player.user).first()
                new_host.is_host = True
                new_host.save()

            player.delete()

            # If room is empty, delete it
            if room.player_set.count() == 0:
                room.delete()
            else:
                # Broadcast player left
                from channels.layers import get_channel_layer
                from asgiref.sync import async_to_sync
                channel_layer = get_channel_layer()
                async_to_sync(channel_layer.group_send)(
                    f'quiz_room_{room.room_code}',
                    {
                        'type': 'player_left',
                        'message': f'{player.user.username} left the room',
                        'room': RoomSerializer(room).data
                    }
                )

            return Response({'message': 'Left room successfully'}, status=status.HTTP_200_OK)
        except Room.DoesNotExist:
            return Response({'error': 'Room not found'}, status=status.HTTP_404_NOT_FOUND)
        except Player.DoesNotExist:
            return Response({'error': 'Player not found in room'}, status=status.HTTP_404_NOT_FOUND)
