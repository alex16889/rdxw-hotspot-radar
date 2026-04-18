# Sports Hotspot Dashboard

Rule-based tooling for turning raw sports news items into a ranked hotspot list with:

- normalized metadata
- stable `topic_type` classification
- fine-grained `storyline_tags`
- Chinese `summary_hint` generation
- transparent 0-10 score breakdowns for hotness, topic fit, source strength, keywords, and title quality

The current project state was an empty scaffold. This version makes the folder runnable without external services so the schema and ranking rules can be iterated locally first.

## Project Layout

```text
sports-hotspot-dashboard/
├── docs/
│   └── schema.md
├── output/
│   ├── sample_ranked.json
│   └── sample_ranked.md
├── sources/
│   └── sample_items.json
└── transform/
    └── hotspot_pipeline.py
```

## Input Model

The pipeline accepts either:

- a JSON array of objects
- JSONL with one object per line

Minimum useful fields:

```json
{
  "title": "Warriors eliminate Rockets to clinch West semifinal spot",
  "summary": "Stephen Curry scored 38 and Golden State closed the series 4-2.",
  "source": "ESPN",
  "url": "https://example.com/warriors-rockets",
  "published_at": "2026-04-18T16:30:00+07:00"
}
```

Optional inputs such as `league`, `entities`, or `tags` are preserved and used when ranking.

## Output Model

Each ranked item includes:

- `topic_type`
- `storyline_tags`
- `summary_hint`
- `keyword_hits`
- `league_tags`
- `entity_tags`
- `source_count`
- `latest_published_at`
- `score_breakdown`
- `total_score`
- `why_hot`

See [schema.md](/Users/alexhemsworth/hermes-work/sports-hotspot-dashboard/docs/schema.md) for the full contract.

## Run

Use the bundled sample data:

```bash
python3 /Users/alexhemsworth/hermes-work/sports-hotspot-dashboard/transform/hotspot_pipeline.py \
  --input /Users/alexhemsworth/hermes-work/sports-hotspot-dashboard/sources/sample_items.json \
  --output-json /Users/alexhemsworth/hermes-work/sports-hotspot-dashboard/output/sample_ranked.json \
  --output-markdown /Users/alexhemsworth/hermes-work/sports-hotspot-dashboard/output/sample_ranked.md
```

You can also point `--input` at your own file and optionally override `--reference-time` for reproducible scoring:

```bash
python3 /Users/alexhemsworth/hermes-work/sports-hotspot-dashboard/transform/hotspot_pipeline.py \
  --input /path/to/items.json \
  --reference-time 2026-04-18T18:00:00+07:00
```

## Local Dashboard

生成数据：

```bash
python3 run_daily_hotspots.py --date 20260418
```

打开 Dashboard：

```bash
open dashboard/index.html
```

或者：

```bash
python3 -m http.server 8787
```

浏览器访问：

```text
http://localhost:8787/dashboard/
```

## Ranking Notes

The scoring model is deliberately transparent:

- freshness rewards recent updates
- topic score captures whether the item is a result, preview, star angle, injury, transfer, or controversy
- source weight differentiates aggregators from primary or high-trust reporters
- keyword score rewards playoff, title-race, injury, transfer, scandal, and national-team triggers
- entity score rewards dense items involving major teams, players, or competitions

The scoring now follows a Hermes-aligned weighted model:

- `hotness_score * 0.35`
- `topic_fit_score * 0.25`
- `source_score * 0.20`
- `keyword_score * 0.15`
- `title_quality_score * 0.05`

This keeps the total score on a 0-10 scale and makes it easier to compare items across different ingest sources.

## Google Sheets Daily Sync

The repo now also includes a bound Google Apps Script version at [google_apps_script/hotspot_sheet.gs](/Users/alexhemsworth/hermes-work/sports-hotspot-dashboard/google_apps_script/hotspot_sheet.gs).

That script is intended to live inside a Google Sheet and can:

- fetch multiple Google News RSS sports queries
- filter low-value service-style headlines
- merge duplicate headlines across feed queries
- score and rank hotspot candidates with the same transparent dimensions used locally
- write the final rows into a target worksheet
- install a once-per-day refresh trigger

This gives the project two runtimes:

- local Python for development and file exports
- Google Apps Script for a sheet-native daily refresh workflow
