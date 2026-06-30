"""Tests for the JSONL → markdown renderer."""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

# Import the module under test after sys.path is set up above.
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


def _assistant_blocks(*blocks):
    return {
        "type": "assistant",
        "message": {"role": "assistant", "content": list(blocks)},
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


class TestThinking:
    def test_thinking_wrapped_in_details(self):
        rec = _assistant_blocks({"type": "thinking", "thinking": "推理过程"})
        md = render_records([rec])
        assert "<details><summary>thinking</summary>" in md
        assert "推理过程" in md
        assert "</details>" in md

    def test_thinking_and_text_in_order(self):
        rec = _assistant_blocks(
            {"type": "thinking", "thinking": "先想"},
            {"type": "text", "text": "再说"},
        )
        md = render_records([rec])
        assert md.index("先想") < md.index("再说")


class TestTool:
    def test_tool_use_renders_name_and_input(self):
        rec = _assistant_blocks(
            {
                "type": "tool_use",
                "id": "t1",
                "name": "Bash",
                "input": {"command": "ls"},
            }
        )
        md = render_records([rec])
        assert "### Tool: Bash" in md
        assert '"command"' in md
        assert "ls" in md

    def test_tool_result_paired_with_tool_use(self):
        records = [
            _assistant_blocks(
                {
                    "type": "tool_use",
                    "id": "t1",
                    "name": "Bash",
                    "input": {"command": "ls"},
                }
            ),
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "t1",
                            "content": "etc\nscripts",
                        }
                    ],
                },
            },
        ]
        md = render_records(records)
        # tool_result must appear after the tool_use it pairs with, not
        # as a stray "## User" section
        assert "## User" not in md or md.count("## User") == 0
        assert "<details><summary>result</summary>" in md
        assert "etc" in md
        assert md.index("### Tool: Bash") < md.index(
            "<details><summary>result</summary>"
        )

    def test_orphan_tool_result_appended_at_end(self):
        records = [
            _user("你好"),
            {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "missing",
                            "content": "orphaned",
                        }
                    ],
                },
            },
        ]
        md = render_records(records)
        assert "orphaned" in md
        assert "## Orphan tool results" in md
        assert md.index("你好") < md.index("orphaned")
