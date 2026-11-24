from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_database: str = "finsight_intelligence"
    mysql_user: str = "finsight_user"
    mysql_password: SecretStr = SecretStr("")
    backend_host: str = "127.0.0.1"
    backend_port: int = 8000
    frontend_port: int = 8501
    api_token: SecretStr = SecretStr("")
    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = ""
    gemini_requests_per_minute: int = Field(12, ge=1, le=60000)
    gemini_temperature: float = Field(.2, ge=0, le=2)
    max_gemini_calls: int = Field(20, ge=0, le=100)
    gemini_output_tokens: int = Field(1800, ge=512, le=8192)
    search_provider: Literal["brave", "off"] = "brave"
    brave_search_api_key: SecretStr = SecretStr("")
    brave_web_search_enabled: bool = True
    brave_llm_context_enabled: bool = True
    search_fallback_enabled: bool = False
    brave_country: str = "US"
    brave_search_lang: str = "en"
    brave_results_per_query: int = Field(6, ge=1, le=20)
    brave_llm_context_max_tokens: int = Field(4096, ge=1024, le=32768)
    brave_context_threshold: Literal["strict", "balanced", "lenient", "disabled"] = "balanced"
    max_search_requests_per_run: int = Field(16, ge=0, le=50)
    brave_requests_per_second: float = Field(1, gt=0, le=10)
    search_tier_limits: list[int] = [2, 2, 2, 2, 2, 2]
    sec_user_agent: str = ""
    sec_timeout_seconds: int = Field(15, ge=2, le=60)
    allowed_source_hosts: list[str] = []
    persist_source_hosts: list[str] = []
    market_enabled: bool = True
    persist_market: bool = False
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_enabled: bool = True
    rag_chunk_size: int = Field(1000, ge=350, le=3000)
    rag_chunk_overlap: int = Field(150, ge=0, le=300)
    rag_top_k: int = Field(8, ge=2, le=20)
    max_agent_rounds: int = Field(1, ge=0, le=2)
    max_analysis_seconds: int = Field(300, ge=15, le=1800)
    numeric_relative_tolerance: float = Field(.001, ge=0, le=.02)
    pdf_font_path: str = ""
    brave_web_usd_per_1000: float | None = Field(None, ge=0)
    brave_context_usd_per_1000: float | None = Field(None, ge=0)
    gemini_input_usd_per_million: float | None = Field(None, ge=0)
    gemini_output_usd_per_million: float | None = Field(None, ge=0)

    @model_validator(mode="after")
    def valid_limits(self):
        if len(self.search_tier_limits) != 6 or any(not 0 <= n <= 8 for n in self.search_tier_limits):
            raise ValueError("SEARCH_TIER_LIMITS cần đúng sáu số nguyên từ 0 đến 8")
        if self.backend_host not in ("127.0.0.1", "::1", "localhost") and not self.api_token.get_secret_value():
            raise ValueError("API_TOKEN bắt buộc khi mở backend ngoài loopback")
        return self

    @property
    def db_url(self) -> URL:
        return URL.create("mysql+pymysql", username=self.mysql_user,
                          password=self.mysql_password.get_secret_value(), host=self.mysql_host,
                          port=self.mysql_port, database=self.mysql_database,
                          query={"charset": "utf8mb4"})


@lru_cache
def settings() -> Settings:
    return Settings()
