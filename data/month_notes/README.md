# Month notes

One JSON file per month (`2026-M10.json`), mapping a person's name to a clause on what happened that month.
The monthly post adds it to their line. Every new entry needs one, and `update.py` logs a warning if it's missing.

- Only state events checked in a named news source, and never guess that an event caused the move.
- Write a clause, with no capital at the start or full stop at the end.
- Keep it neutral: this is a clause in a league table, not commentary.
