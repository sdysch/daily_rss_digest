from __future__ import annotations

import argparse
import logging
import sys
from datetime import date

from src.config import Settings
from src.feed_fetcher import collect_articles, fetch_feeds_file, parse_feeds_file
from src.ranker import rank_articles, summarize_articles
from src.telegram_sender import send_digest

logger = logging.getLogger(__name__)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description='RSS daily digest')
    p.add_argument(
        '--categories',
        help='Comma-separated categories to include (overrides env var)',
    )
    p.add_argument(
        '--dry-run',
        action='store_true',
        help='Print digest to stdout instead of sending to Telegram',
    )
    return p.parse_args(argv)


def _validate(settings: Settings) -> bool:
    if not settings.resolved_api_key:
        logger.error(
            'No LLM API key found. Set OPENAI_API_KEY or run in GitHub Actions '
            'with a GITHUB_TOKEN that has the models scope.'
        )
        return False

    if not settings.telegram_bot_token and not hasattr(settings, '_dry_run'):
        # Only require Telegram creds in non-dry-run mode
        pass

    return True


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format='%(levelname)s | %(message)s',
    )

    args = _parse_args(argv)
    settings = Settings.from_env()

    if args.categories:
        settings.categories = [c.strip().lower() for c in args.categories.split(',')]

    if not settings.categories:
        logger.info('No categories selected — fetching all sections as categories')
        # Will be populated after parsing the feeds file

    logger.info(
        'LLM provider: %s',
        'GitHub Models (free)' if settings.using_github_models else 'OpenAI-compatible',
    )

    logger.info('Fetching feeds file from %s', settings.feeds_url)
    content = fetch_feeds_file(settings.feeds_url)

    sections = parse_feeds_file(content)
    logger.info('Found sections: %s', list(sections.keys()))

    if not settings.categories:
        settings.categories = [s.lower() for s in sections if s not in ('Unread', 'Combined')]

    logger.info('Selected categories: %s', settings.categories)
    articles = collect_articles(sections, settings.categories, settings.max_articles_per_feed)

    if not articles:
        logger.warning('No articles collected. Nothing to do.')
        return 0

    MAX_RANKING_INPUT = 50
    if len(articles) > MAX_RANKING_INPUT:
        logger.info('Truncating %d articles to %d for LLM prompt size limit', len(articles), MAX_RANKING_INPUT)
        articles = articles[:MAX_RANKING_INPUT]

    logger.info('Ranking %d articles with LLM...', len(articles))
    ranked = rank_articles(
        articles,
        model=settings.llm_model,
        api_key=settings.resolved_api_key,
        base_url=settings.resolved_base_url,
        digest_count=settings.digest_count,
    )

    logger.info('Generating summaries for top %d articles...', len(ranked))
    summaries = summarize_articles(
        ranked,
        model=settings.llm_model,
        api_key=settings.resolved_api_key,
        base_url=settings.resolved_base_url,
    )

    today = date.today().strftime('%B %d, %Y')
    digest_items = [
        (a.title, a.url, s, a.source_name, a.source_url)
        for a, s in zip(ranked, summaries, strict=False)
    ]

    if not digest_items:
        logger.warning('No articles in final digest.')
        return 0

    if args.dry_run:
        print(f'\n=== 📰 Daily Digest — {today} ===\n')
        for i, (title, url, summary, source_name, _) in enumerate(digest_items, 1):
            print(f'{i}. {title}')
            print(f'   {url}')
            print(f'   via {source_name}')
            print(f'   {summary}')
            print()
        return 0

    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        logger.error(
            'TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set (or use --dry-run)'
        )
        return 1

    logger.info('Sending digest with %d articles to Telegram...', len(digest_items))
    send_digest(
        bot_token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
        articles=digest_items,
        date_str=today,
    )

    return 0


if __name__ == '__main__':
    sys.exit(main())
