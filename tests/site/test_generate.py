"""
Tests for the static site generator.

Validates that:
- Generated HTML is valid and complete
- All pages include required meta tags
- Structured data (JSON-LD) is present and valid
- No scoring data leaks into page source
"""

import json
import os
import importlib.util
from unittest.mock import patch, MagicMock

# Import site/build modules by file path to avoid collision with Python's
# built-in 'site' module.
_project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_build_dir = os.path.join(_project_root, "site", "build")

import sys

_gen_spec = importlib.util.spec_from_file_location(
    "site_build_generate", os.path.join(_build_dir, "generate.py"))
generate_mod = importlib.util.module_from_spec(_gen_spec)
sys.modules["site_build_generate"] = generate_mod
_gen_spec.loader.exec_module(generate_mod)

_schema_spec = importlib.util.spec_from_file_location(
    "site_build_schema", os.path.join(_build_dir, "schema.py"))
schema_mod = importlib.util.module_from_spec(_schema_spec)
sys.modules["site_build_schema"] = schema_mod
_schema_spec.loader.exec_module(schema_mod)

build_ranking_page = generate_mod.build_ranking_page
build_person_page = generate_mod.build_person_page
build_week_page = generate_mod.build_week_page
build_blog_page = generate_mod.build_blog_page
person_schema = schema_mod.person_schema
ranking_schema = schema_mod.ranking_schema
blog_post_schema = schema_mod.blog_post_schema


def _mock_score(person_id, name, slug, fame_score, rank, momentum=0.0,
                category="musician", week="2026-W04"):
    """Create a mock Score object."""
    person = MagicMock()
    person.name = name
    person.slug = slug
    person.category = category
    person.id = person_id

    score = MagicMock()
    score.person_id = person_id
    score.person = person
    score.fame_score = fame_score
    score.rank = rank
    score.momentum = momentum
    score.week = week
    score.dim_search = 50.0
    score.dim_news = 40.0
    score.dim_social = 30.0
    score.dim_cultural = 20.0
    score.dim_institutional = 10.0
    return score


class TestBuildRankingPage:
    @patch("site_build_generate.get_scores_for_week")
    def test_html_is_complete(self, mock_scores):
        mock_scores.return_value = [
            _mock_score(1, "Alice", "alice", 85.0, 1),
            _mock_score(2, "Bob", "bob", 72.0, 2),
        ]
        html = build_ranking_page("2026-W04")
        assert "<!DOCTYPE html>" in html
        assert "<html" in html
        assert "</html>" in html
        assert "<head>" in html
        assert "<body" in html

    @patch("site_build_generate.get_scores_for_week")
    def test_meta_tags_present(self, mock_scores):
        mock_scores.return_value = [
            _mock_score(1, "Alice", "alice", 85.0, 1),
        ]
        html = build_ranking_page("2026-W04")
        assert '<meta name="description"' in html
        assert '<link rel="canonical"' in html
        assert "<title>" in html

    @patch("site_build_generate.get_scores_for_week")
    def test_contains_ranking_data(self, mock_scores):
        mock_scores.return_value = [
            _mock_score(1, "Alice", "alice", 85.0, 1),
            _mock_score(2, "Bob", "bob", 72.0, 2),
        ]
        html = build_ranking_page("2026-W04")
        assert "Alice" in html
        assert "Bob" in html
        assert "/person/alice" in html

    @patch("site_build_generate.get_scores_for_week")
    def test_structured_data_valid(self, mock_scores):
        mock_scores.return_value = [
            _mock_score(1, "Alice", "alice", 85.0, 1),
        ]
        html = build_ranking_page("2026-W04")
        assert "application/ld+json" in html
        # Extract JSON-LD
        start = html.index('application/ld+json">') + len('application/ld+json">')
        end = html.index("</script>", start)
        data = json.loads(html[start:end])
        assert data["@type"] == "ItemList"
        assert data["numberOfItems"] == 1

    @patch("site_build_generate.get_scores_for_week")
    def test_no_scoring_leak(self, mock_scores):
        mock_scores.return_value = [
            _mock_score(1, "Alice", "alice", 85.0, 1),
        ]
        html = build_ranking_page("2026-W04")
        # Dimension weights should never appear in output
        assert "0.30" not in html or "dim_search" not in html
        assert "DIMENSION_WEIGHTS" not in html


class TestBuildPersonPage:
    @patch("site_build_generate.get_person_history")
    def test_renders_person_profile(self, mock_history):
        mock_history.return_value = [
            _mock_score(1, "Alice", "alice", 85.0, 1, momentum=3.2, week="2026-W04"),
            _mock_score(1, "Alice", "alice", 81.8, 2, momentum=1.0, week="2026-W03"),
        ]
        html = build_person_page(1)
        assert "Alice" in html
        assert "85.0" in html
        assert "FAME SCORE" in html
        assert "RECENT WEEKS" in html

    @patch("site_build_generate.get_person_history")
    def test_empty_history_returns_empty(self, mock_history):
        mock_history.return_value = []
        html = build_person_page(1)
        assert html == ""

    @patch("site_build_generate.get_person_history")
    def test_has_person_schema(self, mock_history):
        mock_history.return_value = [
            _mock_score(1, "Alice", "alice", 85.0, 1, week="2026-W04"),
        ]
        html = build_person_page(1)
        assert "application/ld+json" in html
        start = html.index('application/ld+json">') + len('application/ld+json">')
        end = html.index("</script>", start)
        data = json.loads(html[start:end])
        assert data["@type"] == "Person"
        assert data["name"] == "Alice"


class TestBuildWeekPage:
    @patch("site_build_generate.get_all_scored_weeks")
    @patch("site_build_generate.biggest_movers")
    @patch("site_build_generate.get_scores_for_week")
    def test_renders_week_snapshot(self, mock_scores, mock_movers, mock_weeks):
        mock_scores.return_value = [
            _mock_score(1, "Alice", "alice", 85.0, 1),
        ]
        mock_movers.return_value = {"climbers": [], "fallers": []}
        mock_weeks.return_value = ["2026-W04", "2026-W03"]

        html = build_week_page("2026-W04")
        assert "WEEK 2026-W04" in html
        assert "NUMBER ONE" in html
        assert "Alice" in html

    @patch("site_build_generate.get_all_scored_weeks")
    @patch("site_build_generate.biggest_movers")
    @patch("site_build_generate.get_scores_for_week")
    def test_has_week_navigation(self, mock_scores, mock_movers, mock_weeks):
        mock_scores.return_value = [
            _mock_score(1, "Alice", "alice", 85.0, 1),
        ]
        mock_movers.return_value = {"climbers": [], "fallers": []}
        mock_weeks.return_value = ["2026-W05", "2026-W04", "2026-W03"]

        html = build_week_page("2026-W04")
        assert "/week/2026-W03" in html  # previous
        assert "/week/2026-W05" in html  # next


class TestBuildBlogPage:
    @patch("site_build_generate.get_all_blog_posts")
    @patch("site_build_generate.get_blog_post")
    def test_renders_blog_post(self, mock_post, mock_all):
        post = MagicMock()
        post.title = "Fame Index — Week 2026-W04: Alice Reigns"
        post.content = "<p>Alice holds the top spot.</p>"
        post.week = "2026-W04"
        mock_post.return_value = post
        mock_all.return_value = [post]

        html = build_blog_page("2026-W04")
        assert "Alice Reigns" in html
        assert "Alice holds the top spot" in html

    @patch("site_build_generate.get_blog_post")
    def test_no_post_returns_empty(self, mock_post):
        mock_post.return_value = None
        html = build_blog_page("2026-W04")
        assert html == ""


class TestSchemaFunctions:
    def test_person_schema_produces_valid_json(self):
        result = person_schema({
            "name": "Alice", "slug": "alice",
            "category": "musician", "score": 85.0,
        })
        assert "application/ld+json" in result
        data = json.loads(result.split(">", 1)[1].rsplit("<", 1)[0])
        assert data["@context"] == "https://schema.org"
        assert data["@type"] == "Person"

    def test_ranking_schema_produces_valid_json(self):
        rankings = [
            {"name": "Alice", "slug": "alice", "rank": 1, "score": 85.0},
            {"name": "Bob", "slug": "bob", "rank": 2, "score": 72.0},
        ]
        result = ranking_schema(rankings, "2026-W04")
        data = json.loads(result.split(">", 1)[1].rsplit("<", 1)[0])
        assert data["@type"] == "ItemList"
        assert len(data["itemListElement"]) == 2

    def test_blog_post_schema_produces_valid_json(self):
        result = blog_post_schema({
            "title": "Test Post", "week": "2026-W04",
            "date": "2026-01-19", "summary": "A test.",
        })
        data = json.loads(result.split(">", 1)[1].rsplit("<", 1)[0])
        assert data["@type"] == "BlogPosting"
        assert data["headline"] == "Test Post"
