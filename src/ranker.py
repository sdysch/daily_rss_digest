from __future__ import annotations

import json
import logging

from openai import OpenAI

from src.feed_fetcher import Article

logger = logging.getLogger(__name__)

RANK_SYSTEM_PROMPT = """You are a news curator. Your task is to select the most important and relevant articles from a given list.

Prioritise articles that:
- Cover significant developments in technology, AI/ML, and research
- Have practical relevance or actionable insights
- Represent major news events
- Offer unique technical depth
- Are recent and timely; prefer newer articles when equally important

Avoid:
- Duplicate coverage of the same story (pick the best source)
- Very niche or overly specific content unless it's highly significant
- Low-effort or aggregator content when original sources are available"""


def rank_articles(
    articles: list[Article],
    model: str,
    api_key: str,
    base_url: str | None,
    digest_count: int,
) -> list[Article]:
    if not articles:
        return []

    if not api_key:
        logger.warning('No API key — returning first %d articles as fallback', digest_count)
        return articles[:digest_count]

    user_content = _build_ranking_prompt(articles, digest_count)

    client = OpenAI(api_key=api_key, base_url=base_url)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {'role': 'system', 'content': RANK_SYSTEM_PROMPT},
            {'role': 'user', 'content': user_content},
        ],
        response_format={'type': 'json_object'},
        temperature=0.3,
    )

    raw = resp.choices[0].message.content or '{}'
    return _parse_response(raw, articles)


def _build_ranking_prompt(articles: list[Article], digest_count: int) -> str:
    lines: list[str] = []
    for i, a in enumerate(articles, 1):
        summary = a.summary if a.summary else '(no summary)'
        lines.append(f'{i}. [{a.category}] {a.title}')
        lines.append(f'   Source: {a.source_name}')
        lines.append(f'   Date: {a.published or "unknown"}')
        lines.append(f'   Summary: {summary}')
        lines.append('')

    return f"""Select the top {digest_count} articles from the list below. Return a JSON object with a single key "top" containing an array of article indices (integers, 1-based) ordered by importance. Only include the indices.

Articles:
{chr(10).join(lines)}"""


def _parse_response(raw: str, articles: list[Article]) -> list[Article]:
    try:
        data = json.loads(raw)
        indices = data.get('top', [])
        if not isinstance(indices, list):
            logger.warning('Unexpected response format: %s', raw)
            return articles[:10]
        ranked = []
        for i in indices:
            idx = int(i) - 1
            if 0 <= idx < len(articles):
                ranked.append(articles[idx])
        return ranked
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        logger.warning('Failed to parse LLM response: %s — %s', e, raw)
        return articles[:10]


def summarize_articles(
    articles: list[Article],
    model: str,
    api_key: str,
    base_url: str | None,
) -> list[str]:
    """Generate a short one-line summary for each article using the LLM."""
    if not articles:
        return []

    if not api_key:
        return [a.summary[:120] if a.summary else a.title for a in articles]

    lines = []
    for i, a in enumerate(articles, 1):
        summary = a.summary if a.summary else '(no summary)'
        lines.append(f'{i}. {a.title} — {a.source_name}')
        lines.append(f'   {summary}')
        lines.append('')

    user_content = f"""For each article below, write a single short sentence explaining why it matters. Return a JSON object with a single key "summaries" containing an array of strings, one per article in order.

Articles:
{chr(10).join(lines)}"""

    client = OpenAI(api_key=api_key, base_url=base_url)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {
                'role': 'system',
                'content': 'You write concise, informative one-sentence summaries.',
            },
            {'role': 'user', 'content': user_content},
        ],
        response_format={'type': 'json_object'},
        temperature=0.3,
    )

    raw = resp.choices[0].message.content or '{}'
    try:
        data = json.loads(raw)
        summaries = data.get('summaries', [])
        if isinstance(summaries, list):
            return [str(s) for s in summaries]
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        logger.warning('Failed to parse summary response: %s — %s', e, raw)

    return [a.title for a in articles]
