from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import feedparser
import httpx

logger = logging.getLogger(__name__)

SECTION_RE = re.compile(r'^---(.+)---$')
FEED_LINE_RE = re.compile(r'^(\S+)\s+(.+)$')
COMMENT_RE = re.compile(r'^\s*(#|$)')


@dataclass
class Article:
    title: str
    url: str
    summary: str
    source_name: str
    source_url: str
    category: str


@dataclass
class ParsedFeed:
    url: str
    name: str
    articles: list[Article]


def parse_feeds_file(content: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current_section = 'uncategorized'

    for line in content.splitlines():
        line_stripped = line.strip()
        if COMMENT_RE.match(line_stripped):
            continue
        m = SECTION_RE.match(line_stripped)
        if m:
            current_section = m.group(1).strip()
            sections.setdefault(current_section, [])
            continue
        m = FEED_LINE_RE.match(line_stripped)
        if m:
            url = m.group(1)
            sections.setdefault(current_section, []).append(url)

    return sections


def fetch_feeds_file(url: str) -> str:
    resp = httpx.get(url, timeout=30)
    resp.raise_for_status()
    return resp.text


def fetch_feed(url: str, max_articles: int) -> ParsedFeed:
    try:
        resp = httpx.get(url, timeout=30)
        resp.raise_for_status()
    except Exception:
        logger.warning('Failed to fetch feed: %s', url)
        return ParsedFeed(url=url, name=url, articles=[])

    parsed = feedparser.parse(resp.text)
    feed_title = parsed.feed.get('title', url)

    articles: list[Article] = []
    for entry in parsed.entries[:max_articles]:
        title = entry.get('title', '')
        link = entry.get('link', '')
        summary = _clean_summary(entry.get('summary', ''))
        articles.append(
            Article(
                title=title,
                url=link,
                summary=summary,
                source_name=feed_title,
                source_url=url,
                category='',
            )
        )

    return ParsedFeed(url=url, name=feed_title, articles=articles)


def _clean_summary(raw: str) -> str:
    clean = re.sub(r'<[^>]+>', '', raw)
    clean = re.sub(r'\s+', ' ', clean).strip()
    if len(clean) > 500:
        clean = clean[:497] + '...'
    return clean


def collect_articles(
    sections: dict[str, list[str]],
    selected_categories: list[str],
    max_per_feed: int,
) -> list[Article]:
    seen_urls: set[str] = set()
    all_articles: list[Article] = []

    section_display = {
        'Individual': 'news',
        'Misc': 'misc',
        'Jobs': 'jobs',
        'python': 'python',
        'Tech': 'tech',
        'ArXiv': 'arxiv',
        'Linux': 'linux',
        'reddit': 'reddit',
    }

    for section, feed_urls in sections.items():
        category = section_display.get(section, section.lower())
        if category not in selected_categories:
            continue

        if section in ('Unread', 'Combined'):
            continue

        logger.info('Fetching %d feeds from category: %s', len(feed_urls), category)
        for url in feed_urls:
            parsed = fetch_feed(url, max_per_feed)
            for article in parsed.articles:
                if article.url in seen_urls:
                    continue
                seen_urls.add(article.url)
                article.category = category
                all_articles.append(article)

    all_articles.sort(key=lambda a: (a.category, a.title))
    logger.info('Total unique articles collected: %d', len(all_articles))
    return all_articles
