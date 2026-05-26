# Open Source Release Checklist

Use this checklist before publishing the repository publicly.

## Include

- Core pipeline code: `run_daily_hotspots.py`, `transform/`, `scripts/`, `dashboard/`, `tests/`.
- Public configuration examples: `config/source_radar_sources.json`, `config/editorial_overrides.json`, `.env.example`.
- Minimal sample data: `sources/sample_items.json`.
- Documentation: `README.md`, `docs/schema.md`, `requirements.txt`, `LICENSE`.
- Project hygiene: `CONTRIBUTING.md`, `SECURITY.md`, `.github/workflows/ci.yml`.

## Exclude

- Generated pages and feeds: root `*.html`, `feed.xml`, `sitemap*.xml`, `robots.txt`, `llms.txt`, `ai-context.txt`.
- Generated data: `output/`, `hot/`, `daily/`, `weekly/`, `topics/`, `embed/`.
- Runtime/cache files: `logs/`, `sources/snapshots/`, `sources/source_radar_cache/`, `sources/*_google_news_raw.json`, `sources/llm_editorial_cache.json`, `sources/translation_cache.json`.
- Private operator materials: `AGENTS.md`, `distribution/`, live Nginx configs, live systemd services.
- Secrets: `.env`, API keys, Telegram tokens, Baidu push tokens, cookies, SSH keys.

## Preflight

```bash
python3 scripts/open_source_audit.py
python3 scripts/build_open_source_release.py --dry-run
python3 -m unittest discover -s tests
```

The audit is intentionally conservative. If it reports generated output or
private paths, fix the ignore rules or move the file out of the public branch
before pushing.

To create a local preview tree:

```bash
python3 scripts/build_open_source_release.py --output dist/open-source-preview
```
