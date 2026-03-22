# Fame Index — Implementation Plan

## Architecture Overview

**Principle:** Server-side holds all IP (algorithms, raw data, scoring logic). Client-side receives only pre-rendered static HTML. No public API exposes scoring internals.

```
BUILD PROCESS: server scores -> generate HTML -> deploy static pages to CDN

SERVER (PRIVATE)          SITE (PUBLIC)
- Scoring algorithms      - Static HTML
- Database                - CSS/assets
- Data pipelines          - Minimal JS
- Blog generation         - SEO markup
```

Crawlers see full HTML with structured data. Scoring algorithms never leave the server.

## Tech Stack

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Language | Python | Good for data/ML, simple templating |
| Database | SQLite (dev) / PostgreSQL (prod) | Lightweight dev, robust prod |
| Templates | Jinja2 | Clean HTML output, no JS dependency |
| Styling | Plain CSS | Retro aesthetic, fast loading, no framework bloat |
| Hosting | Vercel (fameindex.net) | Fast, free tier, GitHub deploy |
| Data | Wikipedia API, Google Trends, social APIs | Free/cheap, reliable |

## Key Principles

1. **No public API** — scoring logic is build-time only
2. **HTML-first** — every page is a complete document, no JS hydration
3. **Modular scoring** — each signal (search, social, news) is a separate module
4. **Reproducible builds** — same data in = same HTML out
5. **Documentation as code** — methodology page generated from actual algorithm docs
