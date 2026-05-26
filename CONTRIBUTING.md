# Contributing

Thanks for considering a contribution.

## Local Setup

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python3 -m unittest discover -s tests
```

## Before Opening A Pull Request

Run:

```bash
python3 scripts/open_source_audit.py
python3 scripts/build_open_source_release.py --dry-run
python3 -m unittest discover -s tests
```

Do not include generated news outputs, source caches, logs, `.env` files,
tokens, cookies, private deployment files, or production-only configs.

## Source And Content Policy

Keep original-source links visible. Do not add code that republishes full
copyrighted articles. Prefer public RSS, public APIs, or pages whose terms allow
the intended use.

## Pull Request Scope

Small, focused changes are easiest to review:

- ranking or dedupe rule updates
- new source adapters or source config examples
- static output and SEO improvements
- tests for edge cases
- documentation and deployment examples
