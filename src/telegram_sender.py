from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


def send_digest(
    bot_token: str,
    chat_id: str,
    articles: list[tuple[str, str, str, str, str]],
    date_str: str,
) -> None:
    if not articles:
        logger.info('No articles to send.')
        return

    header = f'<b>📰 Daily Digest — {date_str}</b>\n'
    body_lines: list[str] = []
    total = len(header)

    for i, (title, url, summary, source_name, source_url) in enumerate(articles, 1):
        article = (
            f'{i}. <a href="{_escape_attr(url)}">{_escape(title)}</a>\n'
            f'   via <a href="{_escape_attr(source_url)}">{_escape(source_name)}</a>\n'
            f'   <i>{_escape(summary)}</i>\n'
        )
        if total + len(article) + 1 > 4096:
            dropped = len(articles) - (i - 1)
            if dropped:
                logger.info('Dropping %d article(s) to fit Telegram 4096-char limit', dropped)
            break
        body_lines.append(article)
        total += len(article) + 1

    text = header + '\n'.join(body_lines)

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


def send_message(bot_token: str, chat_id: str, text: str) -> None:
    resp = httpx.post(
        f'https://api.telegram.org/bot{bot_token}/sendMessage',
        json={'chat_id': chat_id, 'text': text, 'parse_mode': 'HTML'},
        timeout=15,
    )
    logger.debug('sendMessage to %s: %s', chat_id, resp.status_code)


def _escape(text: str) -> str:
    return text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _escape_attr(text: str) -> str:
    return text.replace('&', '&amp;').replace('"', '&quot;').replace('<', '&lt;').replace('>', '&gt;')
