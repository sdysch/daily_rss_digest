# RSS Digest

Automated daily RSS digest delivered via Telegram. Fetches feeds from a [newsboat-style urls file](https://raw.githubusercontent.com/sdysch/dotfiles/refs/heads/master/setups/common/.config/newsboat/urls), ranks articles by importance using an LLM, and sends a curated summary to a Telegram chat.

## Usage

```bash
uv run python -m src.main
```

### Dry run (print to stdout)

```bash
uv run python -m src.main --dry-run
```

### Filter by categories

```bash
uv run python -m src.main --categories news,tech,python
```

## Configuration

Set via environment variables (see [`.env.example`](.env.example)):

| Variable | Required | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Yes (unless `--dry-run`) | Telegram bot token |
| `TELEGRAM_CHAT_ID` | Yes (unless `--dry-run`) | Target chat ID |
| `OPENAI_API_KEY` | No* | API key for OpenAI-compatible provider |
| `OPENAI_BASE_URL` | No | Base URL (e.g., `https://api.openai.com/v1`) |
| `LLM_MODEL` | No | Model name (default: `gpt-4o-mini`) |
| `FEEDS_URL` | No | URL to newsboat-style feeds file |
| `DIGEST_CATEGORIES` | No | Comma-separated categories |
| `MAX_ARTICLES_PER_FEED` | No | Max per feed (default: 10) |
| `DIGEST_COUNT` | No | Articles in final digest (default: 10) |

\*Not required if running in GitHub Actions — the built-in `GITHUB_TOKEN` is used with [GitHub Models](https://docs.github.com/en/github-models) (free).

### LLM provider options

- **GitHub Models** (default in CI): no extra keys needed, uses `GITHUB_TOKEN`.
- **OpenAI**: set `OPENAI_API_KEY` and optionally `OPENAI_BASE_URL`.
- **Groq**: set `OPENAI_API_KEY` to a Groq API key and `OPENAI_BASE_URL` to `https://api.groq.com/openai/v1`.

## CI / Automation

A [GitHub Actions workflow](.github/workflows/daily_digest.yml) runs daily at 08:00 UTC. It uses GitHub Models for the LLM at no cost. Set the `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` secrets in your repository.
