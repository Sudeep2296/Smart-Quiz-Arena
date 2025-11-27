# Smart Quiz Arena

A Django-based quiz application with multiplayer and code battle features.

## Features

- User authentication and registration
- Quiz creation and management
- Single-player and multiplayer quiz modes
- Code battle functionality with real-time coding challenges
- WebSocket support for real-time interactions
- REST API endpoints
- Gamification elements

## Technologies Used

- Django 5.2.7
- Django Channels for WebSockets
- Django REST Framework
- PostgreSQL (configurable)
- Bootstrap for frontend
- Judge0 API for code execution

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/Sudeep2296/Smart-Quiz-arena.git
   cd smartquizarena
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up environment variables:
   - Copy `.env` and configure your settings
   - Set `GEMINI_API_KEY` for AI-generated questions
   - Configure `JUDGE0_API_KEY` for code execution

4. Run migrations:
   ```bash
   python manage.py migrate
   ```

5. Create a superuser:
   ```bash
   python manage.py createsuperuser
   ```

6. Run the development server:
   ```bash
<<<<<<< HEAD
   python manage.py runserver
=======
   python -m daphne smartquizarena.asgi:application --port 8000 --bind 0.0.0.0
>>>>>>> eb5058b620cc30e81b27f8c2bda4a7890b90ae58
   ```

## Usage

<<<<<<< HEAD
- Access the application at `http://localhost:8000`
=======
- Access the application at `http://http://127.0.0.1:8000`
>>>>>>> eb5058b620cc30e81b27f8c2bda4a7890b90ae58
- Create quizzes and challenges through the admin panel
- Join multiplayer rooms for collaborative quizzes
- Participate in code battles with real-time judging

## Docker Support

The application includes Docker support. Use `docker-compose.yml` to run with Docker.

## Contributing

Contributions are welcome! Please fork the repository and submit pull requests.

<<<<<<< HEAD
## License

This project is licensed under the MIT License.
=======
>>>>>>> eb5058b620cc30e81b27f8c2bda4a7890b90ae58
