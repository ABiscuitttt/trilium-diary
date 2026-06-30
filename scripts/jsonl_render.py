"""Render a Claude Code session JSONL into readable markdown.

Pure functions only — no IO except `render_jsonl(path)` which reads the file.
"""

from __future__ import annotations

import json
import sys


class EmptyTranscriptError(ValueError):
    """Raised when the JSONL contains no renderable content."""


_IGNORE_TYPES = {
    "system",
    "mode",
    "last-prompt",
    "permission-mode",
    "queue-operation",
    "file-history-snapshot",
    "attachment",
}


def render_jsonl(path: str) -> str:
    """Read a JSONL file and return the rendered markdown."""
    records: list[dict] = []
    skipped = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                skipped += 1
    if skipped:
        print(
            f"warning: skipped {skipped} unparseable line(s) in JSONL",
            file=sys.stderr,
        )
    return render_records(records)


def render_records(records: list[dict]) -> str:
    """Render parsed JSONL records into markdown."""
    parts: list[str] = []
    for rec in records:
        rtype = rec.get("type")
        if rtype in _IGNORE_TYPES:
            continue
        if rtype == "user":
            chunk = _render_user(rec)
            if chunk:
                parts.append(chunk)
        elif rtype == "assistant":
            chunk = _render_assistant(rec)
            if chunk:
                parts.append(chunk)
    if not parts:
        raise EmptyTranscriptError("no renderable content in transcript")
    return "\n\n".join(parts) + "\n"


def _content_blocks(rec: dict) -> list[dict]:
    msg = rec.get("message") or {}
    content = msg.get("content") or []
    return content if isinstance(content, list) else []


def _render_user(rec: dict) -> str:
    texts: list[str] = []
    for block in _content_blocks(rec):
        if block.get("type") == "text":
            texts.append(block.get("text", ""))
    if not texts:
        return ""
    return "## User\n\n" + "\n\n".join(texts)


def _render_assistant(rec: dict) -> str:
    rendered: list[str] = []
    for block in _content_blocks(rec):
        btype = block.get("type")
        if btype == "text":
            rendered.append(block.get("text", ""))
    if not rendered:
        return ""
    return "## Assistant\n\n" + "\n\n".join(rendered)
