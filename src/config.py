from __future__ import annotations

from dataclasses import dataclass, field
from os import environ


DEFAULT_FEEDS_URL = 'https://raw.githubusercontent.com/sdysch/dotfiles/refs/heads/master/setups/common/.config/newsboat/urls'
DEFAULT_CATEGORIES = 'news,tech,python,arxiv,linux,misc'
DEFAULT_LLM_MODEL = 'gpt-4o-mini'
GITHUB_MODELS_URL = 'https://models.inference.ai.azure.com'
SUPPORTED_CATEGORIES = ('news', 'tech', 'python', 'arxiv', 'linux', 'misc', 'reddit')


@dataclass
class Settings:
    telegram_bot_token: str = ''
    telegram_chat_id: str = ''
    openai_api_key: str = ''
    openai_base_url: str | None = None
    llm_model: str = DEFAULT_LLM_MODEL
    feeds_url: str = DEFAULT_FEEDS_URL
    categories: list[str] = field(default_factory=lambda: list(SUPPORTED_CATEGORIES))
    max_articles_per_feed: int = 10
    digest_count: int = 10

    @property
    def resolved_api_key(self) -> str:
        if self.openai_api_key:
            return self.openai_api_key
        return environ.get('GITHUB_TOKEN', '')

    @property
    def resolved_base_url(self) -> str | None:
        if self.openai_base_url:
            return self.openai_base_url
        if not self.openai_api_key and environ.get('GITHUB_TOKEN'):
            return GITHUB_MODELS_URL
        return None

    @property
    def using_github_models(self) -> bool:
        return self.resolved_base_url == GITHUB_MODELS_URL

    @classmethod
    def from_env(cls) -> Settings:
        categories_raw = environ.get('DIGEST_CATEGORIES', '')
        return cls(
            telegram_bot_token=environ.get('TELEGRAM_BOT_TOKEN', ''),
            telegram_chat_id=environ.get('TELEGRAM_CHAT_ID', ''),
            openai_api_key=environ.get('OPENAI_API_KEY', ''),
            openai_base_url=environ.get('OPENAI_BASE_URL'),
            llm_model=environ.get('LLM_MODEL', DEFAULT_LLM_MODEL),
            feeds_url=environ.get('FEEDS_URL', DEFAULT_FEEDS_URL),
            categories=[c.strip().lower() for c in categories_raw.split(',') if c.strip()],
            max_articles_per_feed=int(environ.get('MAX_ARTICLES_PER_FEED', '10')),
            digest_count=int(environ.get('DIGEST_COUNT', '10')),
        )
