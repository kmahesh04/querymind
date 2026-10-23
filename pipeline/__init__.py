"""QueryMind pipeline package. Loads .env once, so GEMINI_API_KEY can live in a file."""
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:  # python-dotenv not installed: rely on real environment variables
    pass
