"""Tests for the JSONL → markdown renderer."""

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from jsonl_render import EmptyTranscriptError, render_jsonl, render_records


FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _records(*items):
    return list(items)


def _user(text):
    return {
        "type": "user",
        "message": {"role": "user", "content": [{"type": "text", "text": text}]},
    }


def _assistant_text(text):
    return {
        "type": "assistant",
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": text}],
        },
    }


class TestPlainText:
    def test_single_user_text(self):
        md = render_records(_records(_user("你好")))
        assert "## User" in md
        assert "你好" in md

    def test_single_assistant_text(self):
        md = render_records(_records(_assistant_text("回答")))
        assert "## Assistant" in md
        assert "回答" in md

    def test_user_then_assistant_order(self):
        md = render_records(
            _records(_user("问题"), _assistant_text("答复"))
        )
        assert md.index("问题") < md.index("答复")
        assert md.index("## User") < md.index("## Assistant")


class TestFixture:
    def test_render_jsonl_reads_fixture(self):
        path = FIXTURE_DIR / "sample_session.jsonl"
        md = render_jsonl(str(path))
        assert "## User" in md
        assert "## Assistant" in md


class TestEmpty:
    def test_empty_records_raises(self):
        with pytest.raises(EmptyTranscriptError):
            render_records([])
