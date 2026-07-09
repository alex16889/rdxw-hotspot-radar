# RDXW GEO / AI Search Analysis

Analyzed: 2026-05-29 17:55 MYT  
Site: https://rdxw.cc/  
Skill: `seo-geo`

## GEO Readiness Score: 77/100

RDXW already has a good technical base for AI search: static HTML, `robots.txt`, `llms.txt`, `ai-context.txt`, sitemap index, canonical tags, OG/Twitter metadata, JSON-LD schema, and visible page content without JavaScript execution.

The main gap is not crawlability. The main gap is entity trust and external validation: the brand is still weakly mentioned outside its own site and GitHub, and many content blocks are useful but still read like generated summaries rather than original, quotable data or editorial analysis.

## Score Breakdown

| Category | Score | Notes |
| --- | ---: | --- |
| Citability | 19/25 | Homepage, source page, methodology page, weekly page and details pages have self-contained Chinese answer blocks. Some detail-page copy is still templated and needs more source-attributed facts. |
| Structural readability | 19/20 | Clean static HTML, H1/H2 hierarchy, lists, topic links, breadcrumbs and strong internal linking. |
| Multi-modal content | 10/15 | Homepage/source/weekly/detail pages now have image assets with alt text. Methodology and API pages still have no visual/table asset, and charts are mostly static OG-style summaries. |
| Authority / brand signals | 10/20 | Organization schema and dates exist. Missing strong `sameAs`, author/person/entity profile, Wikipedia/Wikidata/community mentions, and independent third-party discussion. |
| Technical accessibility | 19/20 | AI crawlers are allowed, `llms.txt` and `ai-context.txt` exist, pages are server-rendered/static. RSL licensing is not implemented, which is optional for a traffic-first posture. |

## Platform Breakdown

| Platform | Readiness | Reason |
| --- | ---: | --- |
| Google AI Overviews | 78/100 | Traditional SEO base and indexed pages are improving; citation blocks and schema are usable. Needs stronger original analysis/data to be selected over bigger domains. |
| ChatGPT Search | 72/100 | `llms.txt`, `ai-context.txt`, static HTML and GitHub repo help. Weak external entity mentions and no broad community discussion hold it back. |
| Perplexity | 70/100 | Perplexity tends to reward cited, source-rich, community-validated content. RDXW has source links but little Reddit/YouTube/LinkedIn/Wikipedia-style validation. |
| Bing Copilot | 82/100 | Static pages, IndexNow path, sitemap structure and open crawler access are favorable. |

## AI Crawler Access

Current `robots.txt`:

```txt
User-agent: *
Allow: /

Sitemap: https://rdxw.cc/sitemap.xml
Sitemap: https://rdxw.cc/sitemap-core.xml
Sitemap: https://rdxw.cc/sitemap-topics.xml
Sitemap: https://rdxw.cc/sitemap-daily.xml
Sitemap: https://rdxw.cc/sitemap-hot.xml
Sitemap: https://rdxw.cc/sitemap.txt
```

Crawler status:

| Crawler | Status |
| --- | --- |
| GPTBot | Allowed |
| OAI-SearchBot | Allowed |
| ChatGPT-User | Allowed |
| ClaudeBot | Allowed |
| PerplexityBot | Allowed |
| CCBot | Allowed |
| anthropic-ai | Allowed |
| Bytespider | Allowed |
| cohere-ai | Allowed |

Recommendation: because the project is traffic-first, keep the broad allow rule for now. If content licensing becomes important later, split search crawlers from training crawlers instead of blocking everything.

## llms.txt Status

`https://rdxw.cc/llms.txt` is present and useful. It includes:

- Site positioning.
- Update time.
- Main URLs.
- RSS / JSON / source quality / health endpoints.
- Recommended citation order.
- Content boundary note excluding ads and buttons.

Recommended improvement:

- Add 3-5 stable "Key facts" lines in `llms.txt`, for example update cadence, supported channels, source count, and citation rule.
- Add the GitHub open-source repo link.
- Add a contact/feedback URL for corrections.

## Brand Mention Analysis

Search-visible brand signals found:

- Main site: `https://rdxw.cc/`
- Public GitHub repo: `https://github.com/YOUR_ACCOUNT/rdxw-hotspot-radar`
- Some profile/listing pages mention "RDXW Hotspot Radar", but they are not strong topical citations.

No strong search-visible evidence found for:

- Wikipedia / Wikidata entity.
- Reddit discussion.
- YouTube mentions.
- Hacker News discussion.
- V2EX discussion.
- Product Hunt listing.
- Search-visible LinkedIn post/page.

GEO implication: AI systems often use entity corroboration. RDXW's on-site structure is now ahead of its off-site entity footprint. The next high-leverage work is not more sitemap tuning; it is creating consistent third-party mentions with the same brand name, URL, description and use case.

## Passage-Level Citability

Good existing blocks:

1. Homepage `RDXW 热点雷达是什么?`
   - Around 316 Chinese characters.
   - Self-contained definition of RDXW, update cadence, covered channels, source examples, and creator use case.
   - This is the strongest AI-citable block on the site.

2. Methodology `排序口径 / 收录口径`
   - Around 367 Chinese characters.
   - Explains source quality, windows, keywords, channel weight, repeat appearances, and why only stronger detail pages enter `sitemap-hot.xml`.

3. Source radar page intro
   - Around 349 Chinese characters.
   - Explains source coverage and why the source page exists.

4. Hot detail pages
   - Have good H2 structure: "发生了什么", "为什么值得关注", "多平台讨论焦点", "自媒体 / 创作者选题切口", and "RDXW 核对依据与更新说明".
   - Current weakness: several paragraphs are still generic templates and do not always include enough concrete facts, numbers, or source-attributed details.

Recommended passage format:

```html
<section class="ai-answer-block">
  <h2>RDXW 热点雷达是什么？</h2>
  <p>RDXW 热点雷达是一个中文多来源热点聚合与自媒体选题工具，每 3 小时更新体育、电竞、AI、娱乐、平台热议和 GitHub 项目。它把 24 小时、3 天、7 天窗口分开展示，并把微博、抖音、B站、虎扑、知乎、百度热搜、IT之家、36氪、GitHub、Product Hunt 等来源作为旁路参考。RDXW 的重点不是复制单个平台热搜，而是帮助创作者先看多源交叉、持续发酵、强选题和可核对来源，再决定是否写成短视频、图文、播客或周报。</p>
</section>
```

## Server-Side Rendering Check

Result: pass.

Checked pages:

- `/`
- `/creator-topics.html`
- `/methodology.html`
- `/trend-sources.html`
- `/weekly/index.html`
- `/api.html`
- One sample hotspot detail page.

All checked pages returned static HTML with visible H1 and body text in the response. AI crawlers do not need to execute JavaScript to read the main content.

## Schema Recommendations

Current schema types detected across sampled pages:

- `Organization`
- `WebSite`
- `WebPage`
- `CollectionPage`
- `BreadcrumbList`
- `ItemList`
- `NewsArticle`
- `TechArticle`
- `ImageObject`

High-impact additions:

1. Add `sameAs` to `Organization` after external profiles are published:

```json
"sameAs": [
  "https://github.com/YOUR_ACCOUNT/rdxw-hotspot-radar",
  "https://x.com/...",
  "https://www.linkedin.com/in/...",
  "https://www.producthunt.com/products/..."
]
```

2. Add `Person` or clearer `Organization` author metadata on methodology/detail pages:

```json
"author": {
  "@type": "Organization",
  "name": "RDXW 热点雷达",
  "url": "https://rdxw.cc/about.html"
}
```

3. Consider `Dataset` schema for public JSON outputs:

- `output/latest_hotspots_ranked.json`
- `output/latest_hotspots_windows.json`
- `output/source_quality.json`

4. Keep `FAQPage` only where there is a real FAQ section. Do not add fake FAQ schema just for SEO.

## Top 5 Highest-Impact Changes

1. Build external entity footprint.
   - Publish consistent posts/pages on GitHub README, X, LinkedIn, V2EX, Product Hunt, HN/Show HN, and relevant creator/SEO communities.
   - Use the same brand string: `RDXW 热点雷达 / RDXW Hotspot Radar`.

2. Add `sameAs` after those profiles exist.
   - Do not point to empty placeholders.
   - This helps AI systems resolve RDXW as an entity instead of only a random domain.

3. Add explicit citable answer blocks to stable pages.
   - Homepage, methodology, source radar, API, weekly index, creator topics.
   - Chinese target: 240-360 characters.
   - English target if added: 134-167 words.

4. Add original data tables.
   - Weekly report should expose "source count", "cross-source topics", "single-source topics", "top categories", "update cadence" as tables.
   - AI search prefers original statistics it can quote.

5. Strengthen detail pages with fact density.
   - Put one concise event-summary block near the top.
   - Include source names, time, one key number, why it matters, and creator angle in the same block.
   - Reduce generic sentences such as "适合做复盘和走势判断" unless they are tied to this specific event.

## Content Reformatting Suggestions

Homepage:

- Keep the current `RDXW 热点雷达是什么?` block.
- Add one line with current source count and update cadence in the same section.

Methodology:

- Add a question heading: `RDXW 如何决定哪些热点进入搜索索引？`
- Use a compact table for `可收录 / noindex / JSON only`.

Hot detail pages:

- Add a top section named `一句话结论`.
- Make it specific enough to quote:
  - event;
  - verified source;
  - why it matters;
  - creator angle;
  - last updated time.

Weekly index:

- Add `本周数据摘要` table:
  - total topics;
  - cross-source topics;
  - strong creator candidates;
  - most active source;
  - most active category.

API page:

- Add a `Dataset` style section explaining which JSON endpoint should be cited, embedded, or avoided.

## Limitations

- This scan used live page fetches, search result checks, GitHub public repo metadata, and existing `.seo-cache/technical-indexing-20260529.json`.
- It did not run paid DataForSEO / AI Overview / ChatGPT citation-tracking APIs.
- Search Console screenshots are lagging indicators; the GEO score here is based on current public crawlability and content structure, not delayed GSC counters.
