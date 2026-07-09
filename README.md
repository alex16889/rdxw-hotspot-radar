# RDXW Hotspot Radar

RDXW Hotspot Radar is a lightweight news and trend collection pipeline for
publisher-style sites, creator topic discovery, and SEO/GEO experiments.

It fetches public trend/news sources, ranks and deduplicates topics, generates a
static dashboard and landing pages, exports machine-readable JSON/RSS/sitemaps,
and can optionally push a private daily digest to Telegram.

## What It Does

- Collects sports, esports, AI, entertainment, platform-discussion, and GitHub signals.
- Builds 24-hour, 3-day, and 7-day trend windows.
- Merges duplicate stories and adds editorial ranking fields.
- Generates static HTML, RSS, sitemap files, JSON feeds, and an embeddable widget.
- Supports manual editorial overrides through JSON config.
- Adds optional IndexNow and Baidu URL submission.
- Provides an optional feedback receiver and daily digest sender.

The project is designed to run without a database. Static files can be served by
Nginx, Caddy, GitHub Pages, Cloudflare Pages, or any ordinary static host.

## Repository Layout

```text
.
├── config/
│   ├── editorial_overrides.json
│   └── source_radar_sources.json
├── dashboard/
│   └── index.html
├── docs/
│   └── schema.md
├── scripts/
│   ├── baidu_submit.py
│   ├── feedback_server.py
│   ├── hotspot_health_alert.py
│   ├── indexnow_notify.py
│   ├── open_source_audit.py
│   └── send_hermes_daily_digest.py
├── sources/
│   └── sample_items.json
├── tests/
├── transform/
│   └── hotspot_pipeline.py
├── run_daily_hotspots.py
├── export_wechat_context.py
├── requirements.txt
└── .env.example
```

Generated pages, caches, logs, and historical outputs are intentionally ignored
by Git. See `OPEN_SOURCE_RELEASE.md` for the publish boundary.

## Quick Start

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

python3 run_daily_hotspots.py \
  --date "$(date +%Y%m%d)" \
  --output-dir output \
  --sources-dir sources \
  --top 20 \
  --min-score 5.8
```

Open the generated static site from `index.html` or serve the repository root
with any static file server.

## Configuration

Core environment variables:

- `HOTSPOT_SITE_URL`: public canonical site URL used in generated links.
- `GITHUB_TOKEN`: optional, raises GitHub Search API rate limits.
- `BAIDU_PUSH_TOKEN` or `HOTSPOT_BAIDU_PUSH_TOKEN`: optional Baidu URL push token.
- `TELEGRAM_BOT_TOKEN` and `TELEGRAM_HOME_CHANNEL`: optional private Telegram digest/alerts.
- `HOTSPOT_DAILY_DIGEST_MIN_HOUR`: earliest local hour to send the daily digest.

Source radar entries live in `config/source_radar_sources.json`.
Manual editorial rules live in `config/editorial_overrides.json`.

## Useful Commands

Run the full generator:

```bash
python3 run_daily_hotspots.py --date "$(date +%Y%m%d)" --output-dir output --sources-dir sources
```

Export a compact sports context file:

```bash
python3 export_wechat_context.py
```

Preview the daily digest without sending:

```bash
python3 scripts/send_hermes_daily_digest.py --dry-run
```

Submit changed URLs to IndexNow:

```bash
python3 scripts/indexnow_notify.py --site-root . --sitemap sitemap.xml --state logs/indexnow_state.json
```

Run tests:

```bash
python3 -m unittest discover -s tests
```

Run the open-source preflight:

```bash
python3 scripts/open_source_audit.py
python3 scripts/build_open_source_release.py --dry-run
```

## Deployment Notes

For a server cron job, use `run_hotspot_cron.example.sh` as a starting point.
Point it at your own project directory and environment file.

The feedback receiver listens on localhost and is intended to sit behind a
reverse proxy:

```bash
python3 scripts/feedback_server.py --host 127.0.0.1 --port 18088 --store /var/lib/hotspot-radar/feedback.jsonl
```

A generic systemd example is available at `deploy/feedback.service.example`.

## Data And Legal Notes

This project stores and renders public headlines, URLs, snippets, and derived
editorial metadata. Before publishing a hosted instance, review the terms of the
sources you enable, keep original-source links visible, and avoid republishing
full copyrighted articles.

The repository should contain code, configuration examples, and minimal sample
data only. Do not commit generated news caches, private logs, API keys, cookies,
or production deployment files.

## License

MIT. See `LICENSE`.
