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
    def test_no_subcommand_exits(self):
        p = build_parser()
        with pytest.raises(SystemExit):
            p.parse_args([])

    def test_list_defaults(self):
        p = build_parser()
        args = p.parse_args(["list"])
        assert args.date is None
        assert args.limit == 50

    def test_list_with_options(self):
        p = build_parser()
        args = p.parse_args(["list", "--date", "2026-06-01", "--limit", "10"])
        assert args.date == "2026-06-01"
        assert args.limit == 10

    def test_delete_parses_note_id(self):
        p = build_parser()
        args = p.parse_args(["delete", "abc123"])
        assert args.cmd == "delete"
        assert args.note_id == "abc123"

    def test_delete_missing_note_id_exits(self):
        p = build_parser()
        with pytest.raises(SystemExit):
            p.parse_args(["delete"])

    def test_get_parses_note_id(self):
        p = build_parser()
        args = p.parse_args(["get", "n1"])
        assert args.cmd == "get"
        assert args.note_id == "n1"
        assert args.content is False

    def test_get_with_content(self):
        p = build_parser()
        args = p.parse_args(["get", "n1", "--content"])
        assert args.content is True

    def test_update_parses_note_id_and_title(self):
        p = build_parser()
        args = p.parse_args(["update", "n1", "--title", "new"])
        assert args.cmd == "update"
        assert args.note_id == "n1"
        assert args.title == "new"
        assert args.icon is None

    def test_update_with_icon(self):
        p = build_parser()
        args = p.parse_args(["update", "n1", "--icon", "bx bx-data"])
        assert args.icon == "bx bx-data"

    def test_update_no_flags_defaults(self):
        p = build_parser()
        args = p.parse_args(["update", "n1"])
        assert args.title is None
        assert args.icon is None

    def test_recap_no_args(self):
        p = build_parser()
        args = p.parse_args(["recap"])
        assert args.cmd == "recap"
        assert args.title_suffix is None
        assert args.session is None
        assert args.project_dir is None
        assert args.date is None

    def test_recap_with_all_args(self):
        p = build_parser()
        args = p.parse_args(
            [
                "recap",
                "--title-suffix",
                "重构",
                "--session",
                "abc",
                "--project-dir",
                "/tmp/p",
                "--date",
                "2026-06-30",
            ]
        )
        assert args.title_suffix == "重构"
        assert args.session == "abc"
        assert args.project_dir == "/tmp/p"
        assert args.date == "2026-06-30"
