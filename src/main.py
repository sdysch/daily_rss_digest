from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import time
from datetime import date

import httpx

from src.config import Settings
from src.feed_fetcher import collect_articles, fetch_feeds_file, parse_feeds_file
from src.ranker import rank_articles, summarize_articles
from src.telegram_sender import send_digest, send_message

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
    p.add_argument(
        '--listen',
        action='store_true',
        help='Poll Telegram for /rerun and /digest commands',
    )
    return p.parse_args(argv)


def _generate_digest(
    settings: Settings,
    categories: list[str] | None = None,
) -> list[tuple[str, str, str, str, str]] | None:
    if categories is not None:
        settings.categories = categories
    elif not settings.categories:
        settings.categories = []

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
        logger.warning('No articles collected.')
        return None

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

    return [
        (a.title, a.url, s, a.source_name, a.source_url)
        for a, s in zip(ranked, summaries, strict=False)
    ]


def _dispatch_workflow(repo: str, token: str) -> bool:
    url = f'https://api.github.com/repos/{repo}/actions/workflows/daily_digest.yml/dispatches'
    resp = httpx.post(
        url,
        headers={
            'Authorization': f'Bearer {token}',
            'Accept': 'application/vnd.github+json',
        },
        json={'ref': 'main'},
        timeout=30,
    )
    return resp.status_code == 204


def _listen_loop(settings: Settings) -> int:
    repo = os.environ.get('GITHUB_REPO', '')
    gh_token = os.environ.get('LISTENER_GITHUB_TOKEN', '')
    bot_token = settings.telegram_bot_token

    if not bot_token:
        logger.error('TELEGRAM_BOT_TOKEN must be set for --listen mode')
        return 1

    logger.info('Starting listener loop ...')
    offset = 0

    while True:
        try:
            resp = httpx.post(
                f'https://api.telegram.org/bot{bot_token}/getUpdates',
                json={
                    'offset': offset,
                    'timeout': 30,
                    'allowed_updates': ['message'],
                },
                timeout=35,
            )
            for update in resp.json().get('result', []):
                update_id = update.get('update_id', 0)
                offset = update_id + 1
                msg = update.get('message', {})
                text = (msg.get('text') or '').strip()
                chat_id = str(msg.get('chat', {}).get('id', ''))

                if not text:
                    continue

                if text == '/rerun':
                    if not repo or not gh_token:
                        send_message(bot_token, chat_id, 'GITHUB_REPO and LISTENER_GITHUB_TOKEN not set')
                        continue
                    ok = _dispatch_workflow(repo, gh_token)
                    reply = (
                        'Digest workflow triggered on main!' if ok
                        else 'Failed to trigger workflow'
                    )
                    send_message(bot_token, chat_id, reply)

                m = re.match(r'^/digest\s*(.*)', text)
                if m:
                    raw = m.group(1).strip()
                    cats = [c.strip().lower() for c in raw.split(',') if c.strip()] if raw else []
                    if cats:
                        unknown = [c for c in cats if c not in ('news', 'tech', 'python', 'arxiv', 'linux', 'misc', 'reddit', 'jobs')]
                        if unknown:
                            send_message(
                                bot_token, chat_id,
                                f'Unknown categories: {", ".join(unknown)}.'
                                f'Valid: news, tech, python, arxiv, linux, misc, reddit, jobs',
                            )
                            continue

                    send_message(bot_token, chat_id, 'Generating digest...')
                    digest = _generate_digest(settings, categories=cats if cats else None)
                    today = date.today().strftime('%B %d, %Y')

                    if not digest:
                        send_message(bot_token, chat_id, 'Nothing to digest!')
                    else:
                        label = f' {"(" + ", ".join(cats) + ")" if cats else ""}'
                        send_digest(
                            bot_token=bot_token,
                            chat_id=chat_id,
                            articles=digest,
                            date_str=f'{today}{label}',
                        )
        except httpx.TimeoutException:
            pass
        except Exception as e:
            logger.warning('Poll error: %s', e, exc_info=True)
            time.sleep(10)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format='%(levelname)s | %(message)s',
    )

    args = _parse_args(argv)
    settings = Settings.from_env()

    if args.listen:
        return _listen_loop(settings)

    if args.categories:
        settings.categories = [c.strip().lower() for c in args.categories.split(',')]

    digest = _generate_digest(settings)
    today = date.today().strftime('%B %d, %Y')

    if not digest:
        logger.warning('Nothing to digest.')
        return 0

    if args.dry_run:
        print(f'\n=== Daily Digest — {today} ===\n')
        for i, (title, url, summary, source_name, _) in enumerate(digest, 1):
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

    logger.info('Sending digest with %d articles to Telegram...', len(digest))
    send_digest(
        bot_token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
        articles=digest,
        date_str=today,
    )

    return 0


if __name__ == '__main__':
    sys.exit(main())
