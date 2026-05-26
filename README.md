# RDXW 热点雷达

RDXW 热点雷达是一个轻量级的新闻与热点采集、排序和静态站生成工具。

它会从公开热点榜单和新闻信号中采集标题、链接和摘要，做去重、评分和频道归类，然后生成可以直接部署的静态页面、RSS、JSON、sitemap、嵌入组件和每日简报。项目不依赖数据库，适合个人站、热点聚合站、创作者选题雷达、SEO/GEO 实验和内部内容监控。

> English summary: RDXW Hotspot Radar is a lightweight news and trend collection pipeline for publisher-style sites, creator topic discovery, and SEO/GEO experiments.

## 这个项目能做什么

- 采集体育、电竞、AI、娱乐、平台热议、GitHub 等公开热点信号。
- 生成 24 小时、3 天、7 天不同时间窗口的热点列表。
- 对相似话题做去重合并，并保留编辑排序字段。
- 输出静态 HTML、RSS、sitemap、JSON feed 和可嵌入组件。
- 支持用 JSON 配置做人工编辑干预。
- 支持可选的 IndexNow 和百度 URL 主动提交。
- 支持可选的反馈接收服务和 Telegram 每日简报推送。

核心设计目标是：不用数据库、不绑定框架、不依赖后台面板。生成出来的静态文件可以放到 Nginx、Caddy、GitHub Pages、Cloudflare Pages 或普通静态空间上运行。

## 适合哪些场景

- 做一个自己的热点观察站或垂直热点站。
- 给自媒体、视频号、公众号、播客做每日选题雷达。
- 做 SEO / GEO / AI Search 的内容承接实验。
- 把多来源热点整理成 RSS、JSON 或私域简报。
- 给团队内部做轻量级舆情、产品、技术趋势看板。

## 仓库结构

```text
.
├── config/
│   ├── editorial_overrides.json
│   └── source_radar_sources.json
├── dashboard/
│   └── index.html
├── docs/
│   ├── schema.md
│   └── x-promo-copy.md
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

生成页面、缓存、日志和历史输出默认不进入 Git。公开发布边界见 `OPEN_SOURCE_RELEASE.md`。

## 快速开始

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

生成完成后，可以直接打开根目录下的 `index.html`，也可以用任意静态文件服务托管整个目录。

## 常用配置

主要环境变量：

- `HOTSPOT_SITE_URL`：生成链接时使用的公开站点地址。
- `GITHUB_TOKEN`：可选，提高 GitHub Search API 的访问额度。
- `BAIDU_PUSH_TOKEN` 或 `HOTSPOT_BAIDU_PUSH_TOKEN`：可选，百度主动推送 token。
- `TELEGRAM_BOT_TOKEN` 和 `TELEGRAM_HOME_CHANNEL`：可选，Telegram 简报和告警推送。
- `HOTSPOT_DAILY_DIGEST_MIN_HOUR`：每日简报允许发送的最早本地小时。

来源雷达配置在 `config/source_radar_sources.json`。
人工编辑规则配置在 `config/editorial_overrides.json`。

## 常用命令

运行完整生成流程：

```bash
python3 run_daily_hotspots.py --date "$(date +%Y%m%d)" --output-dir output --sources-dir sources
```

导出紧凑的体育上下文文件：

```bash
python3 export_wechat_context.py
```

预览每日简报但不发送：

```bash
python3 scripts/send_hermes_daily_digest.py --dry-run
```

把有变化的 URL 提交到 IndexNow：

```bash
python3 scripts/indexnow_notify.py --site-root . --sitemap sitemap.xml --state logs/indexnow_state.json
```

运行测试：

```bash
python3 -m unittest discover -s tests
```

运行开源发布前检查：

```bash
python3 scripts/open_source_audit.py
python3 scripts/build_open_source_release.py --dry-run
```

## 部署说明

服务器定时任务可以基于 `run_hotspot_cron.example.sh` 修改。把里面的项目路径和环境变量文件换成你自己的即可。

反馈接收服务默认监听本机端口，适合放在反向代理后面：

```bash
python3 scripts/feedback_server.py --host 127.0.0.1 --port 18088 --store /var/lib/hotspot-radar/feedback.jsonl
```

通用 systemd 示例在 `deploy/feedback.service.example`。

## 数据与合规

这个项目会保存和渲染公开标题、URL、摘要片段和派生编辑字段。真正上线前，请检查你启用来源的使用条款，保留原始来源链接，不要整篇转载受版权保护的文章。

公开仓库只应包含代码、示例配置和少量样例数据。不要提交生成缓存、私有日志、API Key、Cookie、生产部署文件或任何真实密钥。

## English Summary

RDXW Hotspot Radar is a lightweight news and trend collection pipeline. It fetches public trend and news sources, ranks and deduplicates topics, generates static dashboards and landing pages, exports JSON/RSS/sitemaps, and can optionally push a private daily digest to Telegram.

The project is designed to run without a database. Static files can be served by Nginx, Caddy, GitHub Pages, Cloudflare Pages, or any ordinary static host.

## License

MIT. See `LICENSE`.
