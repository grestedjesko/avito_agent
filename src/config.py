import os
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    
    deepseek_api_key: str = Field(default="", env="DEEPSEEK_API_KEY")
    deepseek_base_url: str = Field(
        default="https://api.deepseek.com/v1", 
        env="DEEPSEEK_BASE_URL"
    )
    
    langfuse_public_key: str = Field(default="", env="LANGFUSE_PUBLIC_KEY")
    langfuse_secret_key: str = Field(default="", env="LANGFUSE_SECRET_KEY")
    langfuse_host: str = Field(
        default="http://localhost:3000", 
        env="LANGFUSE_HOST"
    )
    langfuse_enabled: bool = Field(default=True, env="LANGFUSE_ENABLED")
    
    avito_client_id: str = Field(default="", env="AVITO_CLIENT_ID")
    avito_client_secret: str = Field(default="", env="AVITO_CLIENT_SECRET")
    
    google_calendar_credentials_file: str = Field(
        default="credentials.json",
        env="GOOGLE_CALENDAR_CREDENTIALS_FILE"
    )
    google_calendar_id: str = Field(default="primary", env="GOOGLE_CALENDAR_ID")
    google_calendar_refresh_token: str = Field(default="", env="GOOGLE_CALENDAR_REFRESH_TOKEN")
    
    telegram_bot_token: str = Field(default="", env="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field(default="", env="TELEGRAM_CHAT_ID")
    
    environment: str = Field(default="development", env="ENVIRONMENT")
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    max_conversation_history: int = Field(default=10, env="MAX_CONVERSATION_HISTORY")
    
    embedding_model: str = Field(
        default="sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
        env="EMBEDDING_MODEL"
    )
    chroma_persist_directory: str = Field(
        default="./data/chroma_db",
        env="CHROMA_PERSIST_DIRECTORY"
    )
    rag_top_k: int = Field(default=3, env="RAG_TOP_K")
    rag_min_score: float = Field(default=0.5, env="RAG_MIN_SCORE")
    rag_semantic_weight: float = Field(default=0.4, env="RAG_SEMANTIC_WEIGHT")
    rag_keyword_weight: float = Field(default=0.6, env="RAG_KEYWORD_WEIGHT")
    
    llm_temperature: float = Field(default=0.3, env="LLM_TEMPERATURE")
    llm_max_tokens: int = Field(default=1000, env="LLM_MAX_TOKENS")
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()


def get_settings() -> Settings:
    return settings
