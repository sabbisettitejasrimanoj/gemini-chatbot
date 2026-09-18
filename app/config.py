import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def configured_key(name: str) -> str | None:
    value = os.getenv(name)
    return value if value and not value.startswith("your-") else None


@dataclass(frozen=True)
class Settings:
    mongodb_uri: str = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    mongodb_database: str = os.getenv("MONGODB_DATABASE", "lumen_chatbot")
    groq_api_key: str | None = configured_key("GROQ_API_KEY")
    groq_model: str = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")
    admin_key: str | None = os.getenv("ADMIN_KEY")


settings = Settings()
