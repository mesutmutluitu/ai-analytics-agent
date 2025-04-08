import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Trino settings
TRINO_HOST = os.getenv("TRINO_HOST", "localhost")
TRINO_PORT = int(os.getenv("TRINO_PORT", "8080"))
TRINO_USER = os.getenv("TRINO_USER", "trino")
TRINO_DEFAULT_CATALOG = os.getenv("TRINO_DEFAULT_CATALOG", "your_catalog")
TRINO_DEFAULT_SCHEMA = os.getenv("TRINO_DEFAULT_SCHEMA", "your_schema")

# Ollama settings
OLLAMA_API_URL = os.getenv("OLLAMA_API_URL", "http://localhost:11434/api")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral")

# Schema cache settings
SCHEMA_CACHE_TTL = int(os.getenv("SCHEMA_CACHE_TTL", "3600"))  # 1 hour

# Application settings
APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "8000"))