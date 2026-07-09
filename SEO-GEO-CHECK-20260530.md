# RDXW SEO + GEO Check

Date: 2026-05-30  
Site: https://rdxw.cc/  
Skills: `seo`, `seo-geo`

## Result

Provisional SEO health: **84/100**  
GEO / AI search readiness: **78/100**

This check used the 2026-05-29 `.seo-cache` files as a baseline, then refreshed live evidence from the public site. The main conclusion has not changed: RDXW is no longer blocked by basic technical SEO. The limiting factors are content depth, entity trust, external mentions, and stronger citable data blocks.

## Live Technical Checks

| Item | Result |
| --- | --- |
| `robots.txt` | 200, allows crawling |
| `llms.txt` | 200, present |
| `ai-context.txt` | 200, present |
| `feed.xml` | 200 |
| `sitemap.xml` | 200 sitemap index |
| child sitemaps | `sitemap-core.xml`, `sitemap-topics.xml`, `sitemap-daily.xml`, `sitemap-hot.xml` all 200 |
| unique sitemap URLs | 133 |
| sitemap URL issues | 0 |
| health endpoint | `ok=true`, `warnings=[]` |
| exposed backup/deploy files | blocked / 404 |

The sitemap URL count increased from the previous 76-URL check to 133 unique URLs, but the larger set still passed status, canonical, and indexability checks.

## AI Crawler Access

All checked AI/search crawlers are allowed by the current broad `User-agent: * Allow: /` rule:

- GPTBot
- OAI-SearchBot
- ChatGPT-User
- ClaudeBot
- PerplexityBot
- CCBot
- anthropic-ai
- Bytespider
- cohere-ai

This is acceptable for a traffic-first site. If licensing becomes a concern later, split search crawlers from model-training crawlers instead of blocking all AI bots.

## Core Page Checks

| Page | Status | Indexing | Schema | Images | Notes |
| --- | ---: | --- | --- | ---: | --- |
| `/` | 200 | index,follow | WebSite, Organization, CollectionPage, ItemList | 1/1 alt | Strongest AI-citable definition block |
| `/creator-topics.html` | 200 | index,follow | CollectionPage, ItemList | 1/1 alt | Good creator landing page |
| `/methodology.html` | 200 | index,follow | WebPage | 0 | Needs table/visual and stronger methodology answer block |
| `/trend-sources.html` | 200 | index,follow | CollectionPage, ItemList | 1/1 alt | Good source navigation page |
| `/weekly/index.html` | 200 | index,follow | CollectionPage, ItemList | 1/1 alt | Good weekly aggregation, should add original stats table |
| `/api.html` | 200 | index,follow | TechArticle | 0 | Needs Dataset-style explanation |
| `/feedback.html` | 200 | noindex,follow | ContactPage | 0 | Correctly noindexed |

## On-Page Findings

- Empty titles: 0
- Empty meta descriptions: 0
- Short meta descriptions under 50 chars: 0
- Duplicate titles: 0
- Duplicate meta description groups: 2
- Thin indexed stable pages under 600 visible characters: 4

Thin stable pages:

- `/about.html`
- `/contact.html`
- `/privacy.html`
- `/terms.html`

These are low-priority because they are support/trust pages, not primary traffic pages. They can still be improved for E-E-A-T.

Duplicate meta descriptions are on generated hotspot detail pages:

- Three GitHub detail pages share a generic automation-project description.
- Two sports preview detail pages share a generic match-preview description.

This is not a critical index blocker, but it confirms that some detail pages still feel templated.

## GEO / AI Search Findings

Strengths:

- Static HTML is visible without JavaScript execution.
- `llms.txt` and `ai-context.txt` are live.
- Homepage has a good self-contained "RDXW 热点雷达是什么?" block.
- Details pages now have useful H2 structure: `发生了什么`, `为什么值得关注`, `多平台讨论焦点`, `自媒体 / 创作者选题切口`.
- AI crawler access is open.

Weaknesses:

- External entity footprint is still weak.
- Organization schema still lacks `sameAs` links.
- No strong public Wikipedia/Wikidata/Reddit/YouTube/LinkedIn/Product Hunt/HN/V2EX signals were found.
- Some generated hotspot pages still use generic description/analysis patterns.
- Methodology and API pages lack tables or visual data assets.

## Priority Actions

### High

1. Build external entity mentions.
   - Publish/submit RDXW consistently on GitHub, X, LinkedIn, V2EX, Product Hunt, HN/Show HN, Reddit or relevant creator/SEO communities.
   - Keep one canonical brand string: `RDXW 热点雷达 / RDXW Hotspot Radar`.

2. Add `Organization.sameAs` only after those profiles are live.
   - Do not add placeholders.
   - Include GitHub immediately if the live schema generator supports it.

3. Improve detail-page uniqueness.
   - Make meta descriptions event-specific.
   - Add one specific number, source name, update time, and creator angle near the top of each detail page.

### Medium

4. Expand About/Contact/Privacy/Terms into trust pages.
   - Add methodology summary, correction channel, data boundary, update cadence, and operator/project background.

5. Add original data tables.
   - Weekly page: total topics, cross-source topics, strong candidates, top sources, top categories.
   - Methodology page: indexable vs noindex vs JSON-only criteria.
   - API page: Dataset-style table for each public JSON/RSS endpoint.

### Low

6. Add visual assets to methodology and API pages.
   - Not urgent, but helpful for image/GEO completeness.

## Notes

- PageSpeed Insights API returned `429 Too Many Requests`, so this check did not include fresh Lighthouse/Core Web Vitals scores.
- `indexnow-key.txt` is public and returned 200. That is expected for IndexNow key verification, not treated as a secret exposure.
- Do not spend more time reworking sitemap unless Search Console exports a specific live URL problem. The live sitemap set is currently clean.

