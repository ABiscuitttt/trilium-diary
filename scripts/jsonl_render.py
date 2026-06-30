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


def _tool_result_to_text(content) -> str:
    """Normalize tool_result.content to a string.

    Claude API sends either a plain string or a list of typed content
    blocks like [{"type": "text", "text": "..."}, ...].
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
        return "\n\n".join(parts)
    return ""


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
    """Render parsed JSONL records into markdown.

    tool_use blocks are rendered together with their paired tool_result
    (matched on tool_use_id). Orphan tool_results are listed at the end.
    """
    tool_results: dict[str, str] = {}
    for rec in records:
        if rec.get("type") != "user":
            continue
        for block in _content_blocks(rec):
            if block.get("type") == "tool_result":
                tid = block.get("tool_use_id")
                if tid:
                    tool_results[tid] = _tool_result_to_text(block.get("content"))

    matched: set[str] = set()
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
            chunk = _render_assistant(rec, tool_results, matched)
            if chunk:
                parts.append(chunk)

    orphans = [
        (tid, content)
        for tid, content in tool_results.items()
        if tid not in matched
    ]
    if orphans:
        orphan_md = ["## Orphan tool results"]
        for tid, content in orphans:
            orphan_md.append(
                f"### {tid}\n\n"
                "<details><summary>result</summary>\n\n"
                f"{content}\n\n"
                "</details>"
            )
        parts.append("\n\n".join(orphan_md))

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


def _render_assistant(
    rec: dict, tool_results: dict[str, str], matched: set[str]
) -> str:
    rendered: list[str] = []
    for block in _content_blocks(rec):
        btype = block.get("type")
        if btype == "text":
            rendered.append(block.get("text", ""))
        elif btype == "thinking":
            content = block.get("thinking", "")
            rendered.append(
                "<details><summary>thinking</summary>\n\n"
                f"{content}\n\n"
                "</details>"
            )
        elif btype == "tool_use":
            name = block.get("name", "?")
            inp = block.get("input", {})
            inp_json = json.dumps(inp, ensure_ascii=False, indent=2)
            tu_id = block.get("id", "")
            piece = f"### Tool: {name}\n\n" f"```json\n{inp_json}\n```"
            if tu_id in tool_results:
                matched.add(tu_id)
                piece += (
                    "\n\n<details><summary>result</summary>\n\n"
                    f"{tool_results[tu_id]}\n\n"
                    "</details>"
                )
            rendered.append(piece)
    if not rendered:
        return ""
    return "## Assistant\n\n" + "\n\n".join(rendered)
