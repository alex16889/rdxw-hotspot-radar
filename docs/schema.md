# Schema

## Raw Input

Each raw item is a single object.

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `title` | string | yes | Primary headline. |
| `summary` | string | no | Short body or dek. |
| `source` | string | no | Publisher or reporter name. |
| `url` | string | no | Reference URL. |
| `published_at` | string | no | ISO-8601 timestamp. |
| `league` | string or array | no | Optional league hints. |
| `entities` | array | no | Optional player, club, or competition names. |
| `tags` | array | no | Extra source-side hints. |

## Enriched Output

The pipeline emits a sorted array of enriched hotspot objects.

| Field | Type | Notes |
| --- | --- | --- |
| `item_id` | string | Stable slug derived from the title. |
| `title` | string | Original title. |
| `summary` | string | Original summary. |
| `source` | string | Original source name. |
| `source_count` | number | Number of distinct sources attached to the item. |
| `reference_url` | string or null | Normalized URL field. |
| `published_at` | string or null | Original timestamp. |
| `latest_published_at` | string or null | Latest known timestamp across all merged sources. |
| `topic_type` | string | One of `sports_result`, `sports_preview`, `sports_star`, `sports_business`, `sports_low_value`. |
| `storyline_tags` | array | Secondary story angles such as `transfer`, `injury`, `controversy`, `lineup`, `result`, `business`, `star`. |
| `summary_hint` | string | Chinese one-line hook suitable for downstream copy generation. |
| `keyword_hits` | array | Matched keywords contributing to the score. |
| `league_tags` | array | Detected league or competition tags. |
| `entity_tags` | array | Player, club, or country entities found in the text. |
| `score_breakdown` | object | Transparent sub-scores. |
| `total_score` | number | Sum of all score components. |
| `why_hot` | array | Human-readable reasons for ranking. |
| `raw` | object | Original input object for debugging and traceability. |

## Score Breakdown

```json
{
  "hotness_score": 8.6,
  "topic_fit_score": 9.2,
  "source_score": 6.0,
  "keyword_score": 6.4,
  "title_quality_score": 9.0
}
```

## Example Output

```json
{
  "item_id": "warriors-eliminate-rockets-to-clinch-west-semifinal-spot",
  "title": "Warriors eliminate Rockets to clinch West semifinal spot",
  "summary": "Stephen Curry scored 38 and Golden State closed the series 4-2.",
  "source": "ESPN",
  "source_count": 1,
  "reference_url": "https://example.com/warriors-rockets",
  "published_at": "2026-04-18T16:30:00+07:00",
  "latest_published_at": "2026-04-18T16:30:00+07:00",
  "topic_type": "sports_result",
  "storyline_tags": ["result", "star"],
  "summary_hint": "Warriors赛果已定，适合强调关键节点和后续走势影响。",
  "keyword_hits": ["eliminate", "clinch", "semifinal"],
  "league_tags": ["nba"],
  "entity_tags": ["warriors", "rockets", "stephen curry"],
  "score_breakdown": {
    "hotness_score": 8.58,
    "topic_fit_score": 9.8,
    "source_score": 5.9,
    "keyword_score": 6.62,
    "title_quality_score": 9.5
  },
  "total_score": 8.1,
  "why_hot": [
    "recent update within 2h",
    "result-driven storyline",
    "high-interest keywords: eliminate, clinch, semifinal",
    "major entities: warriors, rockets, stephen curry",
    "story signals: result, star",
    "trusted source: ESPN"
  ]
}
```

## Intended Next Step

The schema is designed so a future ingest layer can stay simple:

1. scrape or import raw items
2. normalize into the raw input contract
3. run the local enrichment pipeline
4. feed the ranked output into a dashboard, export, or LLM summarizer

## Current Design Choice

`topic_type` stays stable and coarse so downstream ranking and UI buckets do not churn. More specific angles are pushed into `storyline_tags`.
