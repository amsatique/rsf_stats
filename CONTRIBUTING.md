# Contributing

Thanks for your interest in improving RSF Stats! This is a small hobby project;
contributions are welcome via issues and pull requests.

## Getting started

Requirements: [uv](https://docs.astral.sh/uv/) and Python 3.12+.

```bash
git clone <your-fork-url>
cd rsf_stats
uv sync                 # install runtime + dev dependencies
cp .env.example .env    # add your RallySimFans credentials
uv run rsf-stats        # http://localhost:8000
```

## Development workflow

Before opening a pull request, make sure the checks pass:

```bash
uv run ruff format .    # format
uv run ruff check .     # lint
uv run pytest           # tests
```

- **Format & lint**: [ruff](https://docs.astral.sh/ruff/) (config in `pyproject.toml`).
- **Tests**: [pytest](https://docs.pytest.org/); parsing is covered by offline
  HTML fixtures in `tests/fixtures/` — no network or credentials needed to run them.
- **Types**: add type hints to all function signatures.

## How the code is organized

```
src/rsf_stats/
  config.py     # settings (.env, RSF_ prefix)
  client.py     # httpx login (session, CSRF token)
  scraper.py    # fetch + HTML parsing (catalog, times, leaderboards, career)
  service.py    # orchestration: login -> scraping -> snapshot, ranks (+ 60s cache)
  storage.py    # SQLite: completion history, personal bests, followed drivers
  models.py     # pydantic models + helpers
  app.py        # FastAPI routes
  templating.py # shared Jinja2 instance
  templates/    # HTML views
tests/          # parsing + storage tests + fixtures
```

The site data is scraped from HTML, so the parsers are intentionally defensive.

## Working with the scraper

The site can change its markup at any time. When touching `scraper.py`:

- Prefer anchoring on stable landmarks (table headers, CSS classes like
  `paros`/`paratlan`/`fejlec2`) over brittle absolute positions.
- If you need a new page, capture its HTML and add a **trimmed, anonymized**
  fixture under `tests/fixtures/`, then write a parsing test against it.
- **Never commit real scraped pages or personal data** — dumps are git-ignored
  (`*.dump.html`, `scratch/`). Keep fixtures synthetic.

## Pull requests

- Keep changes focused; one topic per PR.
- Update the `README.md` if you add or change a feature or an endpoint.
- Describe what you changed and how you tested it.
- Use clear commit messages (e.g. `feat: ...`, `fix: ...`, `docs: ...`).

## Guidelines & etiquette

- **Be gentle with the server**: reuse the 60s cache, avoid bulk-scraping all
  stages, and don't add features that hammer rallysimfans.hu.
- **Secrets stay out of git**: credentials live in `.env` (git-ignored). Never
  hardcode or commit them.

## License

By contributing, you agree that your contributions are licensed under the
[Apache License 2.0](LICENSE).
