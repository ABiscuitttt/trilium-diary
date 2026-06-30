# Recap Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `trilium-diary` 从「AI 起草压缩摘要」改成「读取当前 Claude Code session JSONL → 渲染成可读 markdown → 写入 Trilium，标题以 `Recap` 开头」。

**Architecture:** 新增纯函数模块 `scripts/jsonl_render.py` 负责把 JSONL 解析渲染成 markdown；`scripts/trilium.py` 新增 `recap` 命令做胶水（解析路径、调 render、写入 Trilium 并做幂等覆盖），同时移除旧 `add`/`--type` 体系。SKILL.md、README.md、tests 同步调整。

**Tech Stack:** Python 3.12+，`requests`，`markdown`（已有），`pytest` + `unittest.mock`。

## Global Constraints

- Python 版本：`>=3.12`（保留 `pyproject.toml` 现值）
- 行长上限：88（ruff `line-length=88`）
- 不引入新运行时依赖
- 不使用表情符号（emoji）在代码、文档、提交信息与渲染输出中
- 渲染输出**不截断** `tool_result`
- 幂等 key：当天日笔记下的 `#sessionId=<uuid>`；同 session 同天只 1 条；跨天另建新条，旧条不动
- 图标固定 `bx bx-conversation`
- thinking block 用 `<details><summary>thinking</summary>\n\n…\n\n</details>` 折叠
- 标题：`Recap：<suffix>`（无 suffix 时为 `Recap`）；连字符为全角冒号 `：`
- 版本号升至 `2.0.0`

## File Structure

新建：

- `scripts/jsonl_render.py` — 纯函数 `render_jsonl(path: str) -> str`，外加内部 helper（block 渲染、行解析）
- `tests/test_jsonl_render.py` — `jsonl_render` 的单元测试
- `tests/fixtures/sample_session.jsonl` — 最小可用 session 样例（覆盖各 block 类型）

改动：

- `scripts/trilium.py` — 删 `cmd_add`、`TYPE_ICON`、`resolve_icon`、`build_parser` 中 add 子命令；新增 `cmd_recap`、`build_parser` 中 recap 子命令；保留 `Trilium` 类、`render_markdown`、`parse_date`、`load_config` 及 check/list/get/update/delete 命令
- `tests/test_pure.py` — 删 `TestResolveIcon`、`TestConstants.test_type_icon_values`、`TestBuildParser` 中 add/update 相关用例；新增 `recap` 解析用例
- `tests/test_client.py` — 删 `cmd_add` 相关；新增 `cmd_recap` 两条（创建 / 幂等覆盖）；调整 `cmd_update` 用例去掉 `--type`/`--prefix`
- `SKILL.md` — 重写触发条件、命令、注意事项、日历结构
- `README.md` — 同步命令清单与功能特性
- `pyproject.toml` — `version = "2.0.0"`

---

### Task 1: 引入 jsonl_render.py 与最小化 fixture（仅 user/assistant 文本）

**Files:**
- Create: `scripts/jsonl_render.py`
- Create: `tests/fixtures/sample_session.jsonl`
- Create: `tests/test_jsonl_render.py`

**Interfaces:**
- Consumes: 无（首个任务）
- Produces:
  - `scripts/jsonl_render.py::render_jsonl(path: str) -> str` — 读取 JSONL 文件，返回渲染后的 markdown 字符串
  - `scripts/jsonl_render.py::EmptyTranscriptError(ValueError)` — 当全部行都被忽略时抛出
  - `scripts/jsonl_render.py::render_records(records: list[dict]) -> str` — 渲染已解析的 record 列表（便于测试不读盘）

- [ ] **Step 1: Write the failing test**

写入 `tests/test_jsonl_render.py`：

```python
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
```

写入 `tests/fixtures/sample_session.jsonl`（每行一个 JSON object）：

```jsonl
{"type":"system","content":"ignored line"}
{"type":"user","message":{"role":"user","content":[{"type":"text","text":"你好"}]}}
{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"回答"}]}}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_jsonl_render.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'jsonl_render'`

- [ ] **Step 3: Create scripts/jsonl_render.py with minimal logic**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_jsonl_render.py -v`

Expected: PASS — 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/jsonl_render.py tests/test_jsonl_render.py tests/fixtures/sample_session.jsonl
git commit -m "feat: introduce jsonl_render with user/assistant text support"
```

---

### Task 2: 处理 thinking block（折叠语法）

**Files:**
- Modify: `scripts/jsonl_render.py` (`_render_assistant`)
- Modify: `tests/test_jsonl_render.py` (add tests)

**Interfaces:**
- Consumes: `render_records` from Task 1
- Produces: 同 Task 1 的 `render_records`，新增对 `thinking` block 的折叠渲染

- [ ] **Step 1: Write the failing test**

在 `tests/test_jsonl_render.py` 中追加：

```python
def _assistant_blocks(*blocks):
    return {
        "type": "assistant",
        "message": {"role": "assistant", "content": list(blocks)},
    }


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_jsonl_render.py::TestThinking -v`

Expected: FAIL — `<details>` not in output.

- [ ] **Step 3: Update _render_assistant in scripts/jsonl_render.py**

替换 `_render_assistant` 函数：

```python
def _render_assistant(rec: dict) -> str:
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
    if not rendered:
        return ""
    return "## Assistant\n\n" + "\n\n".join(rendered)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_jsonl_render.py::TestThinking -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/jsonl_render.py tests/test_jsonl_render.py
git commit -m "feat(jsonl_render): collapse thinking blocks with <details>"
```

---

### Task 3: 处理 tool_use 与配对 tool_result

**Files:**
- Modify: `scripts/jsonl_render.py`
- Modify: `tests/test_jsonl_render.py`

**Interfaces:**
- Consumes: `render_records` from Task 2
- Produces: 同接口，新增对 `tool_use` block 的渲染（`### Tool: <name>` + 参数 codeblock），并把配对的 `tool_result` 内嵌到 tool_use 渲染之后

- [ ] **Step 1: Write the failing test**

追加：

```python
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
        assert md.index("### Tool: Bash") < md.index("<details><summary>result</summary>")

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_jsonl_render.py::TestTool -v`

Expected: FAIL.

- [ ] **Step 3: Rewrite render_records and _render_assistant**

把 `scripts/jsonl_render.py` 中以下三处替换为新版（保留 imports、`EmptyTranscriptError`、`_IGNORE_TYPES`、`render_jsonl`、`_content_blocks`、`_render_user` 不变）：

```python
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
                    tool_results[tid] = block.get("content", "")

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
            piece = (
                f"### Tool: {name}\n\n"
                f"```json\n{inp_json}\n```"
            )
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
```

同时把 `_render_user` 改成只渲染 text，跳过 tool_result（tool_result 已在两遍扫描中由配对逻辑处理）：

```python
def _render_user(rec: dict) -> str:
    texts: list[str] = []
    for block in _content_blocks(rec):
        if block.get("type") == "text":
            texts.append(block.get("text", ""))
    if not texts:
        return ""
    return "## User\n\n" + "\n\n".join(texts)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_jsonl_render.py -v`

Expected: PASS — 全部用例通过（含 Task 1/2 已有用例）。

- [ ] **Step 5: Commit**

```bash
git add scripts/jsonl_render.py tests/test_jsonl_render.py
git commit -m "feat(jsonl_render): pair tool_use with tool_result, collect orphans"
```

---

### Task 4: 扩充 fixture + 剥离 text 内嵌的 `<system-reminder>`

**Files:**
- Modify: `scripts/jsonl_render.py`
- Modify: `tests/fixtures/sample_session.jsonl`
- Modify: `tests/test_jsonl_render.py`

**Interfaces:**
- Consumes: Task 3 的 `render_jsonl`
- Produces: 端到端验证 + 文本清洗（剥离 `<system-reminder>...</system-reminder>` 段）

- [ ] **Step 1: Write the failing test**

在 `tests/test_jsonl_render.py` 的 `TestFixture` 类中追加：

```python
    def test_fixture_contains_all_block_types(self):
        path = FIXTURE_DIR / "sample_session.jsonl"
        md = render_jsonl(str(path))
        assert "## User" in md
        assert "## Assistant" in md
        assert "### Tool: Bash" in md
        assert "<details><summary>thinking</summary>" in md
        assert "<details><summary>result</summary>" in md

    def test_fixture_ignores_system_and_mode_lines(self):
        path = FIXTURE_DIR / "sample_session.jsonl"
        md = render_jsonl(str(path))
        assert "ignored line" not in md
        assert "permission-mode" not in md


class TestStripSystemReminder:
    def test_strips_inline_system_reminder(self):
        rec = _user("你好<system-reminder>\n请记住 X\n</system-reminder>之后")
        md = render_records([rec])
        assert "你好" in md
        assert "之后" in md
        assert "请记住 X" not in md
        assert "system-reminder" not in md

    def test_strips_multiple_reminders(self):
        rec = _user("a<system-reminder>x</system-reminder>b<system-reminder>y</system-reminder>c")
        md = render_records([rec])
        assert "x" not in md
        assert "y" not in md
        assert "a" in md and "b" in md and "c" in md
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_jsonl_render.py -v`

Expected: FAIL — fixture 不全 + system-reminder 没被剥离。

- [ ] **Step 3: Add strip helper and rewrite fixture**

在 `scripts/jsonl_render.py` 顶部 imports 后加：

```python
import re

_SYS_REMINDER_RE = re.compile(
    r"<system-reminder>.*?</system-reminder>", re.DOTALL
)


def _strip_reminders(text: str) -> str:
    return _SYS_REMINDER_RE.sub("", text)
```

在 `_render_user` 与 `_render_assistant` 中处理 `text` block 时调用：

```python
def _render_user(rec: dict) -> str:
    texts: list[str] = []
    for block in _content_blocks(rec):
        if block.get("type") == "text":
            cleaned = _strip_reminders(block.get("text", ""))
            if cleaned.strip():
                texts.append(cleaned)
    if not texts:
        return ""
    return "## User\n\n" + "\n\n".join(texts)
```

`_render_assistant` 的 `text` 分支同样：

```python
        if btype == "text":
            cleaned = _strip_reminders(block.get("text", ""))
            if cleaned.strip():
                rendered.append(cleaned)
```

重写 `tests/fixtures/sample_session.jsonl`：

```jsonl
{"type":"system","content":"ignored line"}
{"type":"mode","mode":"normal"}
{"type":"permission-mode","permissionMode":"default"}
{"type":"user","message":{"role":"user","content":[{"type":"text","text":"列出文件"}]}}
{"type":"assistant","message":{"role":"assistant","content":[{"type":"thinking","thinking":"先看一下结构"},{"type":"tool_use","id":"t1","name":"Bash","input":{"command":"ls"}}]}}
{"type":"user","message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"t1","content":"etc\nscripts","is_error":false}]}}
{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"项目里有 etc 与 scripts。"}]}}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_jsonl_render.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/jsonl_render.py tests/fixtures/sample_session.jsonl tests/test_jsonl_render.py
git commit -m "feat(jsonl_render): strip <system-reminder> blocks; expand fixture"
```

---

### Task 5: 在 trilium.py 中新增 cmd_recap（创建路径）

**Files:**
- Modify: `scripts/trilium.py`
- Modify: `tests/test_client.py`

**Interfaces:**
- Consumes: `jsonl_render.render_jsonl`、现有 `Trilium` 类、`render_markdown`、`load_config`、`parse_date`
- Produces:
  - `scripts/trilium.py::cmd_recap(args)` — 执行 recap 流程
  - `scripts/trilium.py::resolve_jsonl_path(session: str | None, project_dir: str | None) -> str` — 拼接 jsonl 绝对路径，处理环境变量缺失
  - `scripts/trilium.py::RECAP_ICON = "bx bx-conversation"` — 固定图标常量

幂等查找辅助：
- `scripts/trilium.py::Trilium.find_session_note(day_id: str, session_id: str) -> str | None` — 在 day_id 下查找带 `#sessionId=<id>` 的子笔记

- [ ] **Step 1: Write the failing test**

在 `tests/test_client.py` 顶部 imports 处追加 `cmd_recap`、`resolve_jsonl_path`：

```python
from trilium import (
    Trilium,
    cmd_add,
    cmd_check,
    cmd_delete,
    cmd_get,
    cmd_list,
    cmd_recap,
    cmd_update,
    load_config,
    resolve_jsonl_path,
)
```

在文件末尾追加新测试类：

```python
class TestResolveJsonlPath:
    def test_explicit_session_and_project_dir(self, tmp_path):
        proj = tmp_path / "myproj"
        proj.mkdir()
        path = resolve_jsonl_path("abc-123", str(proj))
        slug = str(proj).replace("/", "-")
        assert path.endswith(f"{slug}/abc-123.jsonl")

    def test_falls_back_to_env(self, tmp_path, monkeypatch):
        proj = tmp_path / "p"
        proj.mkdir()
        monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "envsess")
        monkeypatch.chdir(proj)
        path = resolve_jsonl_path(None, None)
        assert path.endswith("envsess.jsonl")

    def test_missing_session_exits(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
        monkeypatch.chdir(tmp_path)
        with pytest.raises(SystemExit):
            resolve_jsonl_path(None, None)


class TestCmdRecapCreate:
    def test_creates_new_note_with_labels(self, tmp_path, monkeypatch, capsys):
        # config
        cfg_path = _make_config(tmp_path)
        monkeypatch.setattr("trilium.CONFIG_PATH", cfg_path)

        # jsonl fixture
        jsonl = tmp_path / "sess.jsonl"
        jsonl.write_text(
            '{"type":"user","message":{"role":"user","content":[{"type":"text","text":"hi"}]}}\n',
            encoding="utf-8",
        )

        args = MagicMock()
        args.title_suffix = "重构设计"
        args.session = "sess"
        args.project_dir = str(tmp_path)
        args.date = None

        # Patch the actual jsonl path resolution to return our fixture
        monkeypatch.setattr(
            "trilium.resolve_jsonl_path",
            lambda s, p: str(jsonl),
        )

        with patch.object(Trilium, "ensure_date_path", return_value="day123"), \
             patch.object(Trilium, "find_session_note", return_value=None), \
             patch.object(
                 Trilium, "create_note",
                 return_value={"note": {"noteId": "newnote"}},
             ) as create, \
             patch.object(Trilium, "add_label") as add_label:
            cmd_recap(args)

        create.assert_called_once()
        # The note title is "Recap：重构设计"
        assert create.call_args.args[1] == "Recap：重构设计"
        # Labels: #diary, #sessionId=sess, #diaryDate=<today>, #iconClass=bx bx-conversation
        names = [c.args[1] for c in add_label.call_args_list]
        assert "diary" in names
        assert "sessionId" in names
        assert "diaryDate" in names
        assert "iconClass" in names
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_client.py::TestResolveJsonlPath tests/test_client.py::TestCmdRecapCreate -v`

Expected: FAIL — `ImportError: cannot import name 'cmd_recap'`

- [ ] **Step 3: Implement in scripts/trilium.py**

在文件顶部 imports 后追加：

```python
RECAP_ICON = "bx bx-conversation"
```

在 `Trilium` 类内（紧跟 `_child_with_label` 之后）追加：

```python
    def find_session_note(self, day_id: str, session_id: str) -> str | None:
        """Find an existing recap note for the given session under day_id."""
        expr = f'note.parents.noteId="{day_id}" #sessionId="{session_id}"'
        for n in self.search(expr, limit="5"):
            attrs = n.get("attributes", []) or []
            if any(
                a["name"] == "sessionId" and a["value"] == session_id
                for a in attrs
            ):
                return n["noteId"]
        return None
```

在文件 imports 区之后（紧邻 `CONFIG_PATH = ...`）追加（注意：这里需要 `import sys`、`os` 已经存在）：

```python
def resolve_jsonl_path(
    session: str | None, project_dir: str | None
) -> str:
    """Compose ~/.claude/projects/<slug>/<session>.jsonl from env or args."""
    sid = session or os.environ.get("CLAUDE_CODE_SESSION_ID")
    if not sid:
        die(
            "缺少 sessionId。请用 --session <id> 显式指定，"
            "或确保在 Claude Code 会话中（$CLAUDE_CODE_SESSION_ID）。"
        )
    pdir = project_dir or os.getcwd()
    pdir_abs = os.path.abspath(pdir)
    slug = pdir_abs.replace("/", "-")
    return os.path.expanduser(f"~/.claude/projects/{slug}/{sid}.jsonl")
```

在 `cmd_update` 后、`build_parser` 前追加 `cmd_recap`：

```python
def cmd_recap(args):
    from jsonl_render import EmptyTranscriptError, render_jsonl

    cfg = load_config()
    t = Trilium(cfg)

    jsonl_path = resolve_jsonl_path(
        getattr(args, "session", None), getattr(args, "project_dir", None)
    )
    if not os.path.exists(jsonl_path):
        die(f"找不到 session JSONL: {jsonl_path}")

    try:
        md = render_jsonl(jsonl_path)
    except EmptyTranscriptError:
        die(f"session JSONL 没有可渲染内容: {jsonl_path}")

    date = parse_date(getattr(args, "date", None))
    day_id = t.ensure_date_path(date)

    suffix = getattr(args, "title_suffix", None)
    title = f"Recap：{suffix}" if suffix else "Recap"

    html = render_markdown(md)
    session_id = (
        getattr(args, "session", None) or os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    )

    existing = t.find_session_note(day_id, session_id)
    if existing:
        t.update_note_content(existing, html)
        cur = t.get_note(existing)
        if cur.get("title") != title:
            t.update_note(existing, title=title)
        nid = existing
        action = "已更新"
    else:
        nid = t.create_note(day_id, title, html, ntype="text")["note"]["noteId"]
        t.add_label(nid, "diary")
        t.add_label(nid, "sessionId", session_id)
        t.add_label(nid, "diaryDate", date.isoformat())
        t.add_label(nid, "iconClass", RECAP_ICON)
        action = "已写入"

    url = "{}/#root/{}".format(cfg["server"], nid)
    print(f"✓ {action}日历: {title}")
    print(f"  日期: {date.isoformat()}（{WEEKDAY_ZH[date.weekday()]}）")
    print(f"  noteId: {nid}")
    print(f"  打开: {url}")
```

最后在 `main()` 的命令分发表里加 `"recap": cmd_recap,`（同时保留其它命令）：

```python
def main():
    args = build_parser().parse_args()
    {
        "check": cmd_check,
        "list": cmd_list,
        "delete": cmd_delete,
        "get": cmd_get,
        "update": cmd_update,
        "recap": cmd_recap,
    }[args.cmd](args)
```

（注意：此 Task 暂不删 `cmd_add`、不动 `build_parser`。Task 6 会替换 parser；当前 main 仍保留旧的 add 入口与新增 recap 共存，便于本任务隔离测试。）

实际上 Task 5 仍保留 `"add": cmd_add` 在分发表内：

```python
def main():
    args = build_parser().parse_args()
    {
        "check": cmd_check,
        "add": cmd_add,
        "list": cmd_list,
        "delete": cmd_delete,
        "get": cmd_get,
        "update": cmd_update,
        "recap": cmd_recap,
    }[args.cmd](args)
```

并在 `build_parser()` 里追加 recap 子命令（其它子命令暂不动）：

```python
    pr = sub.add_parser("recap", help="把当前 session JSONL 渲染并写入日历")
    pr.add_argument("--title-suffix", help="标题后缀（Recap：<suffix>）")
    pr.add_argument("--session", help="覆盖 sessionId，默认读 $CLAUDE_CODE_SESSION_ID")
    pr.add_argument("--project-dir", help="覆盖项目目录，默认 $PWD")
    pr.add_argument("--date", help="覆盖日期 YYYY-MM-DD，默认今天")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_client.py::TestResolveJsonlPath tests/test_client.py::TestCmdRecapCreate -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/trilium.py tests/test_client.py
git commit -m "feat(trilium): add recap command (create path) alongside add"
```

---

### Task 6: cmd_recap 幂等覆盖路径 + 删除旧 add

**Files:**
- Modify: `scripts/trilium.py`
- Modify: `tests/test_client.py`
- Modify: `tests/test_pure.py`

**Interfaces:**
- Consumes: Task 5 的 `cmd_recap`、`Trilium.find_session_note`
- Produces:
  - `scripts/trilium.py` 中移除 `cmd_add`、`TYPE_ICON`、`resolve_icon`、`_read_content`，`build_parser` 移除 `add` 子命令与 `update --type`/`--prefix`
  - `main()` 命令分发表去掉 `add`

- [ ] **Step 1: Write the failing test**

在 `tests/test_client.py` 追加：

```python
class TestCmdRecapUpdate:
    def test_updates_existing_note_when_session_matches(
        self, tmp_path, monkeypatch
    ):
        cfg_path = _make_config(tmp_path)
        monkeypatch.setattr("trilium.CONFIG_PATH", cfg_path)

        jsonl = tmp_path / "sess.jsonl"
        jsonl.write_text(
            '{"type":"user","message":{"role":"user","content":[{"type":"text","text":"hi"}]}}\n',
            encoding="utf-8",
        )

        args = MagicMock()
        args.title_suffix = "v2"
        args.session = "sess"
        args.project_dir = str(tmp_path)
        args.date = None

        monkeypatch.setattr(
            "trilium.resolve_jsonl_path",
            lambda s, p: str(jsonl),
        )

        with patch.object(Trilium, "ensure_date_path", return_value="day"), \
             patch.object(Trilium, "find_session_note", return_value="existing-id"), \
             patch.object(Trilium, "update_note_content") as upd_content, \
             patch.object(
                 Trilium, "get_note",
                 return_value={"title": "Recap：v1"},
             ), \
             patch.object(Trilium, "update_note") as upd_note, \
             patch.object(Trilium, "create_note") as create, \
             patch.object(Trilium, "add_label") as add_label:
            cmd_recap(args)

        upd_content.assert_called_once_with("existing-id", upd_content.call_args.args[1])
        upd_note.assert_called_once_with("existing-id", title="Recap：v2")
        create.assert_not_called()
        add_label.assert_not_called()

    def test_skips_title_patch_when_unchanged(self, tmp_path, monkeypatch):
        cfg_path = _make_config(tmp_path)
        monkeypatch.setattr("trilium.CONFIG_PATH", cfg_path)
        jsonl = tmp_path / "s.jsonl"
        jsonl.write_text(
            '{"type":"user","message":{"role":"user","content":[{"type":"text","text":"hi"}]}}\n',
            encoding="utf-8",
        )
        args = MagicMock()
        args.title_suffix = "same"
        args.session = "s"
        args.project_dir = str(tmp_path)
        args.date = None
        monkeypatch.setattr("trilium.resolve_jsonl_path", lambda a, b: str(jsonl))
        with patch.object(Trilium, "ensure_date_path", return_value="day"), \
             patch.object(Trilium, "find_session_note", return_value="eid"), \
             patch.object(Trilium, "update_note_content"), \
             patch.object(
                 Trilium, "get_note", return_value={"title": "Recap：same"}
             ), \
             patch.object(Trilium, "update_note") as upd_note:
            cmd_recap(args)
        upd_note.assert_not_called()
```

修改 `tests/test_pure.py` —— 删除 `TestResolveIcon` 整个类，把 `TestConstants` 中的 `test_type_icon_values` 删掉，把 `TestBuildParser` 中 add 相关用例移除并改写 update 用例。

最终 `tests/test_pure.py` 中关于 parser 的部分应包含：

```python
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
        assert args.content_file is None

    def test_update_with_content_file(self):
        p = build_parser()
        args = p.parse_args(["update", "n1", "--content-file", "/tmp/n.md"])
        assert args.content_file == "/tmp/n.md"

    def test_update_no_flags_defaults(self):
        p = build_parser()
        args = p.parse_args(["update", "n1"])
        assert args.title is None
        assert args.content_file is None

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
```

`TestConstants` 改为只保留：

```python
class TestConstants:
    def test_weekday_zh_seven_days(self):
        assert len(WEEKDAY_ZH) == 7

    def test_month_en_twelve(self):
        assert len(MONTH_EN) == 13  # index 0 is empty
        assert MONTH_EN[0] == ""
```

`tests/test_pure.py` 顶部 import 改为：

```python
from trilium import (
    MONTH_EN,
    WEEKDAY_ZH,
    build_parser,
    parse_date,
    render_markdown,
)
```

`tests/test_client.py` 顶部 imports 中删除 `cmd_add`，保留：

```python
from trilium import (
    Trilium,
    cmd_check,
    cmd_delete,
    cmd_get,
    cmd_list,
    cmd_recap,
    cmd_update,
    load_config,
    resolve_jsonl_path,
)
```

并删除 `tests/test_client.py` 中所有 `cmd_add` 相关测试类/用例（搜索 `cmd_add` 与 `TestCmdAdd`，全部删除）。

`cmd_update` 测试中所有 `args.type`、`args.prefix` 字段也需删除（保留 title / content_file 用例）。

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest -v`

Expected: FAIL — 旧 add 类型测试找不到 add 子命令；新 recap 更新测试通过；其它通过。

- [ ] **Step 3: Refactor scripts/trilium.py**

删除以下符号：
- `TYPE_ICON`（dict）
- `resolve_icon` 函数
- `_read_content` 函数
- `cmd_add` 函数
- `build_parser` 中 `pa = sub.add_parser("add", ...)` 整段
- `build_parser` 中 `pu.add_argument("--type", ...)`、`pu.add_argument("--prefix", ...)` 两行
- `main()` 分发表中的 `"add": cmd_add,`

修改 `cmd_update`（删除 `--type`/`--prefix` 相关分支）：

```python
def cmd_update(args):
    cfg = load_config()
    t = Trilium(cfg)

    if args.title is not None:
        t.update_note(args.note_id, title=args.title)

    if args.content_file:
        with open(args.content_file, encoding="utf-8") as f:
            md = f.read()
        if not md.strip():
            die("内容为空")
        html = render_markdown(md)
        t.update_note_content(args.note_id, html)
    elif not sys.stdin.isatty():
        md = sys.stdin.read()
        if md.strip():
            html = render_markdown(md)
            t.update_note_content(args.note_id, html)

    updated = t.get_note(args.note_id)
    print(f"✓ 已更新: {updated.get('title', '')}")
    print(f"  noteId: {args.note_id}")
    url = "{}/#root/{}".format(cfg["server"], args.note_id)
    print(f"  打开: {url}")
```

并把 `import subprocess`、`import tempfile` 删掉（不再用 `$EDITOR`）。

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -v`

Expected: PASS — 全部测试通过。

- [ ] **Step 5: Commit**

```bash
git add scripts/trilium.py tests/test_client.py tests/test_pure.py
git commit -m "refactor(trilium): drop add/type system, recap is the only writer"
```

---

### Task 7: 同步 SKILL.md、README.md、pyproject.toml 版本号

**Files:**
- Modify: `SKILL.md`
- Modify: `README.md`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: Task 6 的最终命令集（check/list/get/update/delete/recap）
- Produces: 无运行时接口；文档与版本号

- [ ] **Step 1: Edit SKILL.md**

把 `SKILL.md` 整文件替换为：

```markdown
---
name: trilium-diary
description: "把开发对话忠实地写入 Trilium 日历。Use when: 用户说 'recap' / '记一下' / '写到 trilium' / '写进日记' 时直接执行。"
---

# Trilium 工作日记（Recap）

将当前 Claude Code 会话的对话 JSONL 渲染成 markdown，写入 Trilium 内置**日历（Journal）**面板，自动挂到当天日笔记下，标题以 `Recap` 开头。

## 初始化

**每次使用前先检查配置**。执行：

\`\`\`bash
cd "$(dirname "$SKILL_MD")"

if [ ! -f ./etc/config.json ]; then
    echo "缺少配置文件，正在从模板创建..."
    cp ./etc/config.example.json ./etc/config.json
    chmod 600 ./etc/config.json
    echo "请编辑 ./etc/config.json 填入你的 Trilium 信息："
    echo "  - server: Trilium 服务地址（如 http://localhost:8080）"
    echo "  - token: ETAPI token（Trilium → Options → ETAPI 生成）"
    echo "  - calendarRootId: 日历根笔记 ID（留空自动探测）"
    exit 1
fi

./scripts/trilium.py check
\`\`\`

- 如果 `check` 失败，引导用户修改 `etc/config.json` 直到通过。
- `config.json` 权限应为 600，**绝不要回显 token 值**。

## 何时触发

**用户明确请求时直接执行**：用户说 "recap"、"记一下"、"写到 trilium"、"写进日记"。
**不要主动记录琐碎操作**。

## 工作流程

### 写入（recap）

1. 调 `recap` 命令，传入 `--title-suffix` 简短描述（一句话总结此次会话主题）
2. 脚本读 `$CLAUDE_CODE_SESSION_ID` 与 `$PWD`，找到当前 session JSONL，自动渲染并写入
3. 回报标题、日期和打开链接

同 session 同天再次 `recap` 是幂等的：内容覆盖，标题按新 suffix 更新。

### 查看 / 修改 / 删除

照常使用 `get` / `update` / `delete`（注意 `update` 不再支持 `--type`）。

## 命令

\`\`\`bash
cd "$(dirname "$SKILL_MD")"

./scripts/trilium.py check

# 写入当前 session 的 recap
./scripts/trilium.py recap --title-suffix "联调通过"

# 覆盖 sessionId 或项目目录（调试用）
./scripts/trilium.py recap --session <id> --project-dir /path/to/proj

# 查看
./scripts/trilium.py get <noteId>
./scripts/trilium.py get <noteId> --content

# 修改标题
./scripts/trilium.py update <noteId> --title "新标题"

# 修改内容（heredoc stdin）
./scripts/trilium.py update <noteId> <<'EOF'
新 markdown 内容
EOF

# 删除
./scripts/trilium.py delete <noteId>

# 列出
./scripts/trilium.py list
./scripts/trilium.py list --date 2026-06-30
./scripts/trilium.py list --format json
\`\`\`

## 实现细节

日历结构 — 配置了 `calendarRootId` 时使用 ETAPI `/calendar/days/{date}` 端点
（自动创建/查找日 note），否则退回手动幂等查找或创建：

\`\`\`
Journal (#calendarRoot)
 └─ 2026            #yearNote=2026
     └─ 06 - June   #monthNote=2026-06
         └─ 30 - 周二  #dateNote=2026-06-30
             └─ Recap：<suffix>  #iconClass="bx bx-conversation"
                                  #diary #sessionId=<uuid> #diaryDate=2026-06-30
\`\`\`

网络请求自动重试 3 次（502/503/504），指数退避间隔 0.5s。

JSONL 渲染规则：

- `user` 文本 → `## User`
- `assistant` 文本 → `## Assistant`
- thinking block → `<details><summary>thinking</summary>...</details>` 折叠
- tool_use 与配对的 tool_result → `### Tool: <Name>` + 参数 codeblock + 折叠的 result
- 孤儿 tool_result → 末尾 `## Orphan tool results` 段
- system / hook / mode 等行忽略

## 注意事项

- AI 调用 `recap` 时无需传 sessionId，脚本读 `$CLAUDE_CODE_SESSION_ID` 与 `$PWD`
- markdown 本地渲染为 HTML（ETAPI 的 render-markdown 接口不认 ETAPI token）
- 凭证文件 `etc/config.json`（权限 600，已 gitignore，**切勿回显 token**）
- 排错参考 `references/etapi.md`
```

（注意：示例中的 `\`\`\`` 实际写入时是三个反引号，无需转义；这里反斜杠仅用于在本计划文档里逃逸内嵌 fence。）

- [ ] **Step 2: Edit README.md**

把 `README.md` 整文件替换为：

```markdown
# trilium-diary

把当前 Claude Code 会话的对话 JSONL 忠实渲染成 markdown，写入
[Trilium Notes](https://github.com/zadam/trilium) 的日历 / Journal 面板，
标题以 `Recap` 开头。

## 安装

\`\`\`bash
# 项目级（仅当前项目生效）
git clone https://github.com/<user>/trilium-diary.git .claude/skills/trilium-diary

# 全局（所有项目生效）
git clone https://github.com/<user>/trilium-diary.git ~/.claude/skills/trilium-diary
\`\`\`

## 配置

\`\`\`bash
cp etc/config.example.json etc/config.json
\`\`\`

编辑 `etc/config.json`，填入 Trilium 服务器地址、ETAPI token 和日历根笔记 ID。

## 使用

\`\`\`bash
# 检查连通性（含日历根标签验证）
./scripts/trilium.py check

# 写入当前 session 的 recap
./scripts/trilium.py recap --title-suffix "联调通过"

# 列出日记
./scripts/trilium.py list --date 2026-06-30
./scripts/trilium.py list --format json

# 查看 / 修改 / 删除
./scripts/trilium.py get <noteId> --content
./scripts/trilium.py update <noteId> --title "新标题"
./scripts/trilium.py delete <noteId>
\`\`\`

## 功能特性

- **忠实记录**：直接读 session JSONL 渲染成 markdown，含 user/assistant 文本、thinking 折叠、tool 调用与结果
- **幂等覆盖**：同 session 同天的 recap 覆盖已有笔记，不重复创建
- **自动定位**：默认读 `$CLAUDE_CODE_SESSION_ID` 与 `$PWD`，无需手动传 sessionId
- **网络重试**：自动对 502/503/504 错误重试 3 次，指数退避
- **ETAPI 日历端点**：配置 `calendarRootId` 后直接使用 `/calendar/days/{date}` API
- **JSON 输出**：`list --format json` 便于程序化处理

## 依赖

Python 3.12+，通过 [uv](https://docs.astral.sh/uv/) 自动管理依赖（`markdown`、`requests`）。
```

- [ ] **Step 3: Bump version in pyproject.toml**

```bash
# 修改 pyproject.toml 第 3 行 version = "1.1.0" → version = "2.0.0"
```

具体把 `pyproject.toml` 第 3 行从：

```
version = "1.1.0"
```

改为：

```
version = "2.0.0"
```

- [ ] **Step 4: Run all tests to verify they pass**

Run: `uv run pytest -v && uv run ruff check scripts tests`

Expected: PASS — 全部测试与 lint 通过。

- [ ] **Step 5: Commit**

```bash
git add SKILL.md README.md pyproject.toml
git commit -m "docs: rewrite SKILL.md & README.md for recap; bump to 2.0.0"
```

---

### Task 8: 端到端真实验证

**Files:**
- 无文件修改；纯验证

**Interfaces:**
- Consumes: 全部前序任务
- Produces: 无；产生 Trilium 笔记证明系统工作

- [ ] **Step 1: 跑全套自动化检查**

Run:

```bash
uv run pytest -v
uv run ruff check scripts tests
```

Expected: 全 PASS。

- [ ] **Step 2: 在真实 Trilium 上做创建路径验证**

Run:

```bash
./scripts/trilium.py check
./scripts/trilium.py recap --title-suffix "测试 recap 创建"
```

Expected:
- `check` 输出 `Trilium 可达`、`token 有效`、`日历根 = ...`、`#calendarRoot 标签存在`
- `recap` 输出 `已写入日历: Recap：测试 recap 创建`、当天日期、noteId、打开链接

打开链接，确认 Trilium 中：
- 当天日笔记下出现 `Recap：测试 recap 创建`
- 笔记图标为对话气泡（bx-conversation）
- 标签含 `#diary`、`#sessionId=<id>`、`#diaryDate=YYYY-MM-DD`、`#iconClass=bx bx-conversation`
- 正文含 `## User` / `## Assistant` / 折叠的 `thinking` / `### Tool: ...`

- [ ] **Step 3: 在真实 Trilium 上做幂等覆盖验证**

Run:

```bash
./scripts/trilium.py recap --title-suffix "测试 recap v2"
```

Expected:
- 输出 `已更新日历: Recap：测试 recap v2`，noteId 与上一步**相同**
- Trilium 中**没有**新增笔记，原笔记标题更新为 `Recap：测试 recap v2`，正文也已刷新

- [ ] **Step 4: 验证完成后清理（可选）**

如果想删除测试笔记：

```bash
./scripts/trilium.py delete <noteId>
```

或保留作为日常记录起点。

- [ ] **Step 5: 最终提交（如有遗留小修）**

如果端到端验证中暴露了小问题（如文案错别字），修复后：

```bash
git add -A
git commit -m "fix: 端到端验证发现的小修"
```

否则跳过。
