"""
store_scores must replace a period's scores, not append to them.

It previously only ever appended, so rescoring a period doubled its rows and
every person appeared twice in the rankings. That would have fired on every
re-run of the update script and on any backfill retry — and it did, silently,
until a top-10 listing printed each name twice.
"""

from server.db import init_db, get_session
from server.db.models import Score
from server.db.queries import store_scores


def _rows(period):
    with get_session() as s:
        return s.query(Score).filter(Score.week == period).count()


def _score(pid, period, val):
    return {"person_id": pid, "week": period, "fame_score": val, "rank": pid}


class TestStoreScoresIsIdempotent:
    def test_rescoring_a_period_replaces_rather_than_appends(self):
        init_db()
        period = "1999-Q1"  # sentinel period, never real data
        try:
            store_scores([_score(1, period, 10.0), _score(2, period, 20.0)])
            assert _rows(period) == 2
            # Re-run the same period, as the update script would
            store_scores([_score(1, period, 11.0), _score(2, period, 21.0)])
            assert _rows(period) == 2, "rescoring duplicated rows"
            with get_session() as s:
                vals = sorted(r.fame_score for r in
                              s.query(Score).filter(Score.week == period).all())
            assert vals == [11.0, 21.0], "kept stale values instead of replacing"
        finally:
            with get_session() as s:
                s.query(Score).filter(Score.week == period).delete(
                    synchronize_session=False)
                s.commit()

    def test_empty_batch_leaves_existing_scores_alone(self):
        init_db()
        period = "1999-Q2"
        try:
            store_scores([_score(1, period, 5.0)])
            store_scores([])  # must not wipe anything
            assert _rows(period) == 1
        finally:
            with get_session() as s:
                s.query(Score).filter(Score.week == period).delete(
                    synchronize_session=False)
                s.commit()
