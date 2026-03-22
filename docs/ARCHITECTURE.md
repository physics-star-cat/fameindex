# Fame Index — Technical Architecture

## System Boundary

The system is split into two strict zones:

### Private (server/)
Contains all intellectual property: scoring algorithms, raw data, database,
and data pipeline code. This code runs at build time only and is never
deployed to any public-facing server.

### Public (site/)
Contains only the static HTML output and assets. No JavaScript exposes
scoring logic. No API endpoints exist. The site is a collection of
pre-rendered HTML documents served from a CDN.

## Build Flow

```
1. Data Pipeline (server/data/)
   - Fetches raw signals from external sources
   - Normalises and stores in database

2. Scoring Engine (server/scoring/)
   - Reads normalised data from database
   - Computes fame scores, momentum, sentiment, controversy
   - Writes scored results back to database

3. Blog Generator (server/blog/)
   - Reads scored data + historical comparisons
   - Produces blog post drafts with commentary

4. Site Generator (site/build/)
   - Reads scored data from database
   - Renders Jinja2 templates to static HTML
   - Embeds structured data (JSON-LD)
   - Outputs to site/output/

5. Deploy (scripts/)
   - Pushes site/output/ to CDN
```

## Database

Development uses SQLite for simplicity. Production uses PostgreSQL.
The application code uses an abstraction layer so the switch is transparent.

Key tables:
- `persons` — canonical list of tracked individuals
- `scores` — weekly fame scores per person
- `signals` — raw signal data per source per person per week
- `blog_posts` — generated blog content

## Weekly Cycle

Every Friday:
1. Pipeline fetches fresh data for the week
2. Scoring engine recalculates all scores
3. Blog generator produces the weekly post
4. Site generator rebuilds all pages
5. Deploy pushes to CDN

The entire process is triggered by `scripts/weekly_update.sh`.
