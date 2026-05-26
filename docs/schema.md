# Schema

## Ranked Payload

`run_daily_hotspots.py` 会输出：

```json
{
  "date": "20260424",
  "run_date": "2026-04-24",
  "reference_time": "2026-04-24T13:51:14+07:00",
  "items": [],
  "topic_counts": {
    "sports": 15,
    "esports": 16,
    "ai": 20,
    "entertainment": 20,
    "platform": 8,
    "github": 20
  },
  "topic_labels": {
    "sports": "体育热点",
    "platform": "平台热议"
  }
}
```

主要文件：

- `output/latest_hotspots_ranked.json`
- `output/latest_hotspots_windows.json`
- `output/latest_hotspots_manifest.json`
- `output/topics/{window}_{topic}.json`
- `output/source_radar.json`

## Ranked Item

`items[]` 中每条记录的主要字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `title` | string | 对外展示标题。 |
| `summary` | string | 清洗后的纯文本摘要。 |
| `source` | string | 主来源。 |
| `url` | string | 原始链接。 |
| `reference_url` | string | 前端跳转使用的链接。 |
| `topic` | string | `sports` / `esports` / `ai` / `entertainment` / `platform` / `github` |
| `source_topic` | string | 原始来源话题，平台项会保留 `x` 或 `youtube`。 |
| `topic_type` | string | 细分类型，例如 `sports_result`、`youtube_live`。 |
| `topic_label` | string | 中文频道名。 |
| `summary_hint` | string | 一句话摘要钩子。 |
| `editor_note` | string | 面向编辑的简短备注。 |
| `sources` | object[] | 多来源合并后的证据行。 |
| `source_count` | number | 来源数。 |
| `storyline_tags` | string[] | 中文标签，例如 `赛果`、`赛前`、`争议`。 |
| `keyword_hits` | string[] | 命中的关键词标签。 |
| `league_tags` | string[] | 联赛或赛事标签。 |
| `entity_tags` | string[] | 队伍、球员、主体或仓库名。 |
| `score_breakdown` | object | 透明子分数。 |
| `total_score` | number | 最终总分。 |
| `score` | number | 兼容别名。 |
| `why_hot` | string[] | 中文上榜原因。 |
| `editorial_value_score` | number | 规则二段筛选后的选题价值分。 |
| `editorial_value_level` | string | `强选题` / `可跟进` / `观察` / `降噪`。 |
| `editorial_value_reason` | string | 选题价值判断依据。 |
| `publication_briefing` | object | 详情页和推送共用的结构化解读。 |
| `published_at` | string | 发布时间。 |
| `latest_published_at` | string | 多来源合并后的最新时间。 |
| `pin_rank` | number | 手工置顶顺序，仅在命中编辑规则时出现。 |

平台项额外字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `platform_source` | string | `x` 或 `youtube` |
| `platform_label` | string | `X` 或 `YouTube` |

GitHub 项额外字段：

- `repo`
- `stars`
- `forks`
- `language`
- `created_at`
- `recommend_reason`

## Score Breakdown

```json
{
  "hotness_score": 8.9,
  "topic_fit_score": 8.4,
  "source_score": 7.3,
  "keyword_score": 6.8,
  "title_quality_score": 4.1
	}
	```

`publication_briefing` 字段：

| 字段 | 说明 |
| --- | --- |
| `what_happened` | 发生了什么。 |
| `why_it_matters` | 为什么值得看。 |
| `what_to_watch_next` | 后续看什么。 |
| `controversy_point` | 争议点或评论区观察方向。 |

总分计算：

```text
hotness_score * 0.35
+ topic_fit_score * 0.25
+ source_score * 0.20
+ keyword_score * 0.15
+ title_quality_score * 0.05
```

## Window Payload

`latest_hotspots_windows.json` 是兼容保留的轻量窗口摘要文件；公开页不依赖它加载列表，列表数据以 `manifest + topics/{window}_{topic}.json` 为准：

```json
{
  "generated_at": "2026-04-24T13:51:14+07:00",
  "available_windows": [
    {"key": "1d", "label": "24小时", "days": 1},
    {"key": "3d", "label": "3天", "days": 3},
    {"key": "7d", "label": "7天", "days": 7}
  ],
  "windows": {
    "1d": {
      "topic_counts": {},
      "item_count": 0
    }
  }
}
```

窗口项会在 ranked item 基础上增加：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `window_days` | number | 窗口天数。 |
| `appearance_count` | number | 在窗口内出现的次数。 |
| `first_seen_at` | string | 第一次出现时间。 |
| `last_seen_at` | string | 最近一次出现时间。 |
| `history_dates` | string[] | 出现时间简表。 |
| `window_score` | number | 窗口聚合分数。 |

## Manifest Payload

公开页优先读取 `latest_hotspots_manifest.json`：

```json
{
  "generated_at": "2026-04-24T13:51:14+07:00",
  "run_date": "2026-04-24",
  "default_window": "7d",
  "default_topic": "sports",
  "available_windows": [],
  "topics": [
    {"key": "sports", "label": "体育热点"},
    {"key": "platform", "label": "平台热议"}
  ],
  "windows": {
    "7d": {
      "label": "7天",
      "days": 7,
      "topic_counts": {
        "sports": 20,
        "platform": 18
      },
      "files": {
        "sports": "topics/7d_sports.json",
        "platform": "topics/7d_platform.json"
      }
    }
  }
}
```

页面根据这个 manifest 再按需读取对应频道文件，避免首屏直接拉完整窗口大 JSON。

## Source Radar Payload

`output/source_radar.json` 是首页“多源热榜”的旁路来源层，不参与主热点排序。每个来源最多保留 20 条，首页始终展示全部来源；频道分类只作用于下方热点列表。来源清单由 `config/source_radar_sources.json` 控制。

```json
{
  "generated_at": "2026-05-05T16:41:31+07:00",
  "provider": "https://newsnow.busiyi.world",
  "source_count": 13,
  "ok_count": 13,
  "item_count": 255,
  "topic_counts": {
    "sports": 20,
    "esports": 20,
    "platform": 120
  },
  "sources": [
    {
      "id": "hupu",
      "label": "虎扑",
      "title": "主干道热帖",
      "topic": "sports",
	      "group": "体育",
	      "column": "sports",
	      "feed_type": "hottest",
	      "interval": "10m",
	      "quality_tier": "high",
	      "focus_default": true,
	      "updated_at": "2026-05-05T16:40:00+07:00",
      "item_count": 30,
      "items": [
        {
          "rank": 1,
          "title": "示例标题",
          "url": "https://example.com",
          "hot_value": "热度信息"
        }
      ]
    }
  ]
}
```
