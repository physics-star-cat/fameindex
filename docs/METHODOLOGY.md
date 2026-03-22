# Fame Index — Scoring Methodology

## What is the Fame Index?

The Fame Index is a weekly ranking of public figures by measurable fame signals.
It does not measure quality, talent, or moral worth — only how much the world is
paying attention to someone right now.

## The Score

Every person gets a single headline number from 0 to 100:

- 90+ : Global phenomenon (household name worldwide)
- 70-89: Major celebrity (widely recognised)
- 50-69: Notable figure (known within their field)
- 30-49: Rising/fading (gaining or losing attention)
- 0-29 : Niche (known only to dedicated followers)

## Five Dimensions

The headline score is built from five measurable dimensions. Each dimension
scores 0-100 independently and is visible on profile pages.

### 1. Search Interest
How often people actively look someone up. When you're curious about a person,
you search for them or visit their Wikipedia page.

**Sources:** Wikipedia pageviews, Google Trends

### 2. News Presence
How much journalists are writing about someone. Measures mainstream media
penetration — are proper news outlets covering this person?

**Sources:** GDELT global news index, Google News

### 3. Social Buzz
How much people are *discussing* someone online. Not follower counts (which
are static) but active conversation volume — are people talking about this
person right now?

**Sources:** Reddit discussion volume, Wikipedia edit activity, YouTube content

### 4. Cultural Output
Are they producing things people consume? An artist releasing music, an actor
in a new film, a writer publishing a book. This dimension only applies to
people with active creative/commercial output.

**Sources:** Spotify artist popularity, TMDB film/TV popularity

### 5. Institutional Recognition
Has the establishment acknowledged them? Awards, nominations, and formal
recognition from industry bodies. This is the slowest-moving dimension —
it represents accumulated credibility rather than current buzz.

**Sources:** Wikidata structured award/nomination data

## How Dimensions Combine

Each dimension score is the average of its normalised source signals. The
five dimension scores are then combined using a weighted formula to produce
the single headline number.

**The weights are not publicly disclosed.** This prevents gaming. If you
knew that news coverage was weighted at exactly X%, you could manufacture
news coverage to boost your score. The opacity is intentional.

What we will say: all five dimensions contribute. No single dimension can
produce a score above ~60 on its own. Genuine fame shows up across multiple
dimensions simultaneously.

## Momentum

The momentum score tracks week-on-week change in the headline number.
A person can have a moderate fame score but extreme momentum (e.g. a
previously unknown person going viral).

Positive momentum = climbing the rankings.
Negative momentum = fading from public attention.

## Normalisation

Raw data from different sources comes in wildly different scales. Wikipedia
pageviews range from 0 to millions. Google Trends is already 0-100. Reddit
scores can be anything.

All signals are normalised to 0-100 using methods appropriate to their
distribution:
- **Log scaling** for power-law data (pageviews, article counts)
- **Passthrough** for pre-normalised data (Google Trends, Spotify)
- **Ratio scaling** for velocity metrics (edit rates, growth ratios)

Historical baselines are used to adapt the scaling — a person's score
reflects their attention relative to the observed range, not an arbitrary
fixed scale.

## Regional Scoring

Fame is not uniform globally. A Bollywood star may score 90 in India but
20 in the UK. Regional views use the same methodology but with
geographically filtered data sources where available.

## What the Index Does NOT Measure

- **Quality or talent** — A terrible person can be extremely famous
- **Net worth** — Wealth and fame are different things
- **Follower counts** — Static numbers don't reflect current attention
- **Moral worth** — The index is descriptive, not prescriptive
