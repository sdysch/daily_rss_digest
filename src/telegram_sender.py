from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


def send_digest(
    bot_token: str,
    chat_id: str,
    articles: list[tuple[str, str, str]],
    date_str: str,
) -> None:
    if not articles:
        logger.info('No articles to send.')
        return

    lines = [f'<b>📰 Daily Digest — {date_str}</b>\n']
    for i, (title, url, summary) in enumerate(articles, 1):
        lines.append(
            f'{i}. <a href="{url}">{_escape(title)}</a>\n'
            f'   <i>{_escape(summary)}</i>\n'
        )

    text = '\n'.join(lines)

    if len(text) > 4096:
        logger.info('Message too long (%d chars), truncating', len(text))
        text = text[:4090] + '...\n'

    resp = httpx.post(
        f'https://api.telegram.org/bot{bot_token}/sendMessage',
        json={
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'HTML',
            'disable_web_page_preview': True,
        },
        timeout=30,
    )
    resp.raise_for_status()
    logger.info('Digest sent to Telegram (message_id=%s)', resp.json().get('result', {}).get('message_id'))


def _escape(text: str) -> str:
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
