# Tavily Search

Web search via Tavily API (alternative to Brave). Use when the user asks to search the web / look up sources / find links and `web_search` is unavailable or insufficient.

## Requirements

Provide API key via either:

- environment variable: `TAVILY_API_KEY`, or
- `~/.openclaw/.env` line: `TAVILY_API_KEY=...`

## Commands

Run from the OpenClaw workspace:

```bash
# raw JSON (default)
python3 {baseDir}/scripts/tavily_search.py --query "..." --max-results 5

# include short answer (if available)
python3 {baseDir}/scripts/tavily_search.py --query "..." --max-results 5 --include-answer

# stable schema (closer to web_search): {query, results:[{title,url,snippet}], answer?}
python3 {baseDir}/scripts/tavily_search.py --query "..." --max-results 5 --format brave

# human-readable Markdown list
python3 {baseDir}/scripts/tavily_search.py --query "..." --max-results 5 --format md
```

## Output

- **raw** (default): `{query, answer?, results:[{title,url,content}]}`
- **brave**: `{query, answer?, results:[{title,url,snippet}]}`
- **md**: compact Markdown list with title/url/snippet.

## Notes

- Keep `--max-results` small by default (3–5) to reduce token/reading load.
- Prefer returning URLs + snippets; fetch full pages only when needed.
- Tavily provides AI-generated answers and high-quality results; ideal for research.
