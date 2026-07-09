# RDXW Heat Score Spec

RDXW heat score is a site-owned ranking signal for explaining why a topic is worth watching today. It is not search volume, official popularity, traffic, betting, trading, or investment advice.

## Goal

Turn aggregation into original data:

- Show why a topic is hot now, not just that it appears in a feed.
- Separate single-source noise from cross-source signals.
- Provide a stable tool page for SEO/GEO: `/heat-index.html`.
- Feed only 1-2 manually reviewed interpretation candidates per day.

## Formula

`heat_score = base_score * 0.42 + velocity_score * 0.25 + source_diversity_score * 0.20 + freshness_score * 0.13`

All component scores are normalized to `0-100`.

### base_score

Uses the best available internal score:

1. `editorial_value_score`
2. `window_score`
3. `total_score`
4. `score`

Scores from `0-10` are multiplied by 10. Scores already above 10 are capped at 100.

### velocity_score

Uses the trend label, appearance count, and `why_hot` signals:

- `突然升温` starts highest.
- `今日可跟` and `多源交叉` are strong current signals.
- `反复出现` and `一周主线` are useful but less urgent.
- Mentions of `12小时` or `24小时` raise the score.

### source_diversity_score

Uses `source_count` and unique source domains. This favors topics that appear across sources instead of a single scraped headline.

### freshness_score

Uses the latest observed time from `last_seen_at`, `latest_published_at`, or `published_at`. Recent items score higher; missing timestamps get a conservative midpoint.

## Outputs

- `output/heat-index.json`: machine-readable heat index.
- `heat-index.html`: indexable public tool page with Dataset and ItemList schema.
- `output/interpretation_candidates.json`: daily manual interpretation candidates.

## Publishing Boundary

Interpretation candidates are not auto-published as indexable pages. The default policy is:

- `noindex,follow` until manual review.
- Maximum 1-2 deep interpretation pages per day.
- Each published interpretation needs RDXW heat data, timeline, source checks, and creator angles.
- Do not create one thin page per keyword or per scraped headline.

