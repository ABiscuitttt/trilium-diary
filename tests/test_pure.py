"""Tests for pure functions: render_markdown, parse_date."""

import datetime as _dt
import os

# Import from the script under test.  The script lives in scripts/trilium.py
# so we add that directory to sys.path.
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

# The script calls sys.exit on errors via die(), which we want to catch.
from trilium import (
    MONTH_EN,
    WEEKDAY_ZH,
    build_parser,
    parse_date,
    render_markdown,
)


# ---------------------------------------------------------------------------
# render_markdown
# ---------------------------------------------------------------------------
class TestRenderMarkdown:
    def test_plain_text(self):
        html = render_markdown("hello world")
        assert "<p>hello world</p>" in html

    def test_heading(self):
        html = render_markdown("## Title")
        assert "<h2>" in html

    def test_code_block(self):
        md = "```python\nprint('hi')\n```"
        html = render_markdown(md)
        assert "print" in html

    def test_inline_code(self):
        html = render_markdown("use `foo` bar")
        assert "<code>foo</code>" in html

    def test_table(self):
        md = "| a | b |\n|---|---|\n| 1 | 2 |"
        html = render_markdown(md)
        assert "<table>" in html

    def test_bold_and_italic(self):
        html = render_markdown("**bold** and *italic*")
        assert "<strong>bold</strong>" in html
        assert "<em>italic</em>" in html

    def test_link(self):
        html = render_markdown("[click](https://example.com)")
        assert 'href="https://example.com"' in html

    def test_empty_input(self):
        html = render_markdown("")
        assert html == ""

    def test_fenced_code_with_language(self):
        md = "```js\nconst x = 1;\n```"
        html = render_markdown(md)
        # codehilite wraps tokens in <span>, so check for stripped text
        assert "const" in html
        assert "x" in html
        assert "codehilite" in html

    def test_unordered_list(self):
        html = render_markdown("- a\n- b\n- c")
        assert "<ul>" in html
        assert "<li>" in html

    def test_ordered_list(self):
        html = render_markdown("1. a\n2. b")
        assert "<ol>" in html

    def test_nl2br(self):
        """nl2br extension converts single newlines to <br> inside <p>."""
        html = render_markdown("line1\nline2")
        assert "<br" in html


# ---------------------------------------------------------------------------
# parse_date
# ---------------------------------------------------------------------------
class TestParseDate:
    def test_none_returns_today(self):
        assert parse_date(None) == _dt.date.today()

    def test_valid_date(self):
        assert parse_date("2026-06-01") == _dt.date(2026, 6, 1)

    def test_invalid_format_exits(self):
        with pytest.raises(SystemExit):
            parse_date("01-06-2026")

    def test_gibberish_exits(self):
        with pytest.raises(SystemExit):
            parse_date("not-a-date")

    def test_empty_string_returns_today(self):
        assert parse_date("") == _dt.date.today()

    def test_boundary_year(self):
        assert parse_date("2000-01-01") == _dt.date(2000, 1, 1)
        assert parse_date("2099-12-31") == _dt.date(2099, 12, 31)


# ---------------------------------------------------------------------------
# Constants sanity
# ---------------------------------------------------------------------------
class TestConstants:
    def test_weekday_zh_seven_days(self):
        assert len(WEEKDAY_ZH) == 7

    def test_month_en_twelve(self):
        assert len(MONTH_EN) == 13  # index 0 is empty
        assert MONTH_EN[0] == ""


# ---------------------------------------------------------------------------
# build_parser
# ---------------------------------------------------------------------------
class TestBuildParser:
    def test_check_subcommand(self):
        p = build_parser()
        args = p.parse_args(["check"])
        assert args.cmd == "check"

    def test_note_til(self):
        p = build_parser()
        args = p.parse_args([
            "note", "til",
            "--topic", "Postgres",
            "--title", "TIL: tz",
            "--source-session", "s1",
            "--note-date", "2026-07-03",
        ])
        assert args.cmd == "note"
        assert args.note_cmd == "til"
        assert args.topic == "Postgres"
        assert args.title == "TIL: tz"
        assert args.source_session == "s1"
        assert args.note_date == "2026-07-03"
        assert args.icon is None

    def test_note_til_missing_required(self):
        p = build_parser()
        with pytest.raises(SystemExit):
            p.parse_args(["note", "til", "--topic", "X"])

    def test_note_ref_requires_url(self):
        p = build_parser()
        args = p.parse_args([
            "note", "ref",
            "--topic", "SQLite",
            "--title", "t",
            "--source-session", "s1",
            "--note-date", "2026-07-03",
            "--url", "https://ex.com",
        ])
        assert args.url == "https://ex.com"

    def test_note_ref_missing_url_fails(self):
        p = build_parser()
        with pytest.raises(SystemExit):
            p.parse_args([
                "note", "ref",
                "--topic", "X", "--title", "t",
                "--source-session", "s", "--note-date", "2026-07-03",
            ])

    def test_note_idea(self):
        p = build_parser()
        args = p.parse_args([
            "note", "idea",
            "--topic", "Trilium", "--title", "t",
            "--source-session", "s", "--note-date", "2026-07-03",
            "--icon", "bx bx-brain",
        ])
        assert args.note_cmd == "idea"
        assert args.icon == "bx bx-brain"

    def test_note_topics(self):
        p = build_parser()
        args = p.parse_args(["note", "topics"])
        assert args.note_cmd == "topics"

    def test_note_merge_topic(self):
        p = build_parser()
        args = p.parse_args([
            "note", "merge-topic", "--type", "til", "OldPg", "Postgres",
        ])
        assert args.note_cmd == "merge-topic"
        assert args.type == "til"
        assert args.from_topic == "OldPg"
        assert args.to_topic == "Postgres"

    def test_list_all(self):
        p = build_parser()
        args = p.parse_args([
            "list", "--type", "til", "--topic", "Postgres",
            "--note-date", "2026-07-03", "--source-session", "s1",
            "--limit", "20",
        ])
        assert args.cmd == "list"
        assert args.type == "til"
        assert args.topic == "Postgres"
        assert args.note_date == "2026-07-03"
        assert args.source_session == "s1"
        assert args.limit == 20

    def test_get(self):
        p = build_parser()
        args = p.parse_args(["get", "abc123"])
        assert args.cmd == "get"
        assert args.note_id == "abc123"
        assert args.content is False
        args2 = p.parse_args(["get", "abc123", "--content"])
        assert args2.content is True

    def test_update(self):
        p = build_parser()
        args = p.parse_args([
            "update", "abc", "--title", "new", "--icon", "bx bx-data",
        ])
        assert args.cmd == "update"
        assert args.note_id == "abc"
        assert args.title == "new"
        assert args.icon == "bx bx-data"

    def test_delete(self):
        p = build_parser()
        args = p.parse_args(["delete", "abc"])
        assert args.cmd == "delete"
        assert args.note_id == "abc"

