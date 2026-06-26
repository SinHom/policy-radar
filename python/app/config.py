"""应用配置：pydantic-settings 从环境变量读。"""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# .env 在项目根
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    """所有配置项。"""

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_debug: bool = True

    # DB
    database_url: str = ""

    # LLM
    minimax_api_key: str = ""
    minimax_base_url: str = "https://api.minimaxi.com/v1"
    minimax_model: str = "MiniMax-M3"
    llm_text_max_chars: int = 6000
    llm_summarize_concurrency: int = 2

    # Mock WeChat
    mock_wechat_url: str = "http://localhost:9999"
    mock_wechat_port: int = 9999

    # Admin 鉴权（管理后台登录用）
    admin_user: str = "admin"
    admin_password: str = "policy-radar-2026"  # 改 .env 可自定义
    # 简易 token 存储（重启后失效；生产用 JWT）
    admin_token_secret: str = "change-me-in-production"

    # Crawler
    crawler_request_interval_min: float = 3.0
    crawler_request_interval_max: float = 5.0
    crawler_user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
