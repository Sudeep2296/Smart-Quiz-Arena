import google.generativeai as genai
from django.conf import settings
import os
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smartquizarena.settings')
django.setup()

# Configure Gemini
genai.configure(api_key=settings.GEMINI_API_KEY)

print("Listing all available Gemini models...\n")

try:
    models = genai.list_models()
    
    print("All models:")
    print("-" * 80)
    for model in models:
        print(f"Name: {model.name}")
        if hasattr(model, 'supported_generation_methods'):
            print(f"  Supported methods: {model.supported_generation_methods}")
        if hasattr(model, 'display_name'):
            print(f"  Display name: {model.display_name}")
        print()
    
    print("\nModels that support generateContent:")
    print("-" * 80)
    for model in models:
        if hasattr(model, 'supported_generation_methods') and 'generateContent' in model.supported_generation_methods:
            print(f"✓ {model.name}")
            if hasattr(model, 'display_name'):
                print(f"  ({model.display_name})")
                
except Exception as e:
    print(f"Error listing models: {e}")
    import traceback
    traceback.print_exc()
