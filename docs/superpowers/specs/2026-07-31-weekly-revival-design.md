# Fame Index — weekly revival design

**Date:** 2026-07-31
**Status:** approved

## Problem

The site last updated at **2026-W13** (late March). Today is 2026-W31, so roughly
18 weeks are missing. The existing `scripts/weekly_update.sh` was never run — there
was no cron job and no failure; the cycle simply never happened.

Three things are needed:

1. Backfill W14–W31 so the archive is complete.
2. A week picker so visitors can browse past weeks.
3. A weekly post that says what moved and *why*, in the existing droll register.

Plus an operational requirement: **one Python script the author runs manually each
Friday evening** that updates scores, blog and HTML and pushes it live.

## Key constraint: not all signals are backfillable

The pipeline is architected for historical weeks — every source function takes a
`week` argument. But only some honour it:

| Source | Historical? | Why |
|---|---|---|
| `wikipedia_pageviews` | yes | Wikimedia API serves full daily history |
| `gdelt_count` | yes | queries a real date range against GDELT's archive |
| `google_trends` | yes | `week_to_dates` → historical range |
| `wiki_edit_velocity` | yes | revision history is dated |
| `google_news_count` | partial | treated as unavailable for backfill |
| `reddit_score` | **no** | `fetch_reddit_mentions(time_filter="week")` always means "past week from now" |
| `youtube_score` | **no** | no per-week historical view counts exist |
| `wikidata_recognition` | static | slow-moving; acceptable either way |

Calling `weekly_social_score(name, "2026-W18")` accepts the week and returns **today's**
Reddit data regardless. Backfilling naively would stamp identical Reddit and YouTube
values across all 18 weeks — distorting rankings and leaving a visible flat line in a
site whose entire premise is "this is what fame looked like in week N".

**Decision:** backfill using historical signals only. Reddit and YouTube are omitted
from reconstructed weeks rather than fabricated.

## Design

### 1. Scoring must normalise over available signals

Highest-risk change. The engine currently assumes a fixed signal set. If backfilled
weeks carry six signals instead of eight, they score systematically lower and every
person appears to have crashed in W14 and recovered in W31 — an artefact that would
look like real movement.

Scores are computed over *whichever signals are present*, re-weighted to sum to 1.
Covered by tests, since a mistake here is silently wrong rather than loudly broken.

`scores` gains a `reconstructed` flag (0/1), surfaced as a small teletext footnote on
those week pages so the record stays honest.

### 2. Backfill — `scripts/backfill.py`

Walks W14→W31: pipeline (historical sources only) → score → store, marking each week
reconstructed.

- ~18 weeks × 121 persons × 4 sources ≈ 8,700 API calls
- Rate-limited; Google Trends throttles aggressively
- **Resumable** — skips weeks already scored, so it can be re-run after interruption
- `--from` / `--to` / `--dry-run` flags

### 3. Week picker

Button top-right showing `2026-W31 ▾`, opening a dropdown grouped by year, newest
first, from the existing `get_all_scored_weeks()`. Current week marked; reconstructed
weeks dimmed. Links to existing `/week/{week}` pages — no routing changes.

Built with `<details>`/`<summary>` and CSS so it works without JavaScript, consistent
with the teletext aesthetic.

### 4. Blog "why" — rewrite `server/blog/generator.py`

Current generator picks from `random.choice` template pools. The "why" is stock filler
and repeats — Harry Styles and BLACKPINK both drew *"The streaming numbers don't lie"*
in the same W13 post — and it credits Spotify, which is no longer among the signals.

Replace with signal-derived commentary: for each mover, compare per-signal values
against the previous week, take the largest swing, and name it.

```
Eilish up 5 — Wikipedia traffic tripled.
Lamar down 16 — news mentions halved.
```

Same register, every clause backed by a stored number. Shorter shape: number one,
three climbers, three fallers, new entries. Controversy Corner dropped.

**Backfilled weeks get rankings but no individual posts.** Eighteen structurally
identical posts published simultaneously is the bulk-templated pattern Google is
already declining to index elsewhere in the estate (see `../../../audit_2026-07-31.md`),
and fameindex has a foothold worth protecting — 10 indexed pages, homepage at
position 12.9. Instead: one hand-shaped catch-up post covering March→July, then
genuine weekly posts from W31.

### 5. `scripts/weekly_update.py`

Single Python entrypoint replacing the bash script, which embedded Python in shell
heredocs with `'$WEEK'` string interpolation — fragile and untestable.

Sequence: resolve week → pipeline → score → blog → build → commit → push.

- Deploys by **pushing to `main`**; Vercel auto-deploys. More robust than
  `vercel --prod`, which needs a live CLI token.
- **Atomic**: nothing is committed unless every prior step succeeded.
- Logs to `logs/weekly-YYYY-Www.log`.
- `--week`, `--dry-run`, `--no-push` flags.
- Exits non-zero on failure with a readable summary.

Run manually: `python scripts/weekly_update.py`

## Testing

- Scoring re-weight: unit tests over full and partial signal sets, including that a
  person with identical relative standing scores the same either way.
- Blog generator: given fixture scores/signals, asserts the named signal is the
  largest actual mover.
- Week picker: assert every scored week appears in built HTML.
- Backfill: dry-run over a single week against the live APIs before the full run.

## Out of scope

- Restoring Reddit/YouTube history (not obtainable)
- Adding new signal sources
- Redesigning the ranking algorithm beyond the re-weighting above
- Automated scheduling — the author runs the script manually on Fridays
