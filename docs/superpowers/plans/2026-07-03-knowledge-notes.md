# Knowledge Notes Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `trilium-diary` 从"忠实记录 recap"重构成通用 Trilium 知识笔记助手：支持 TIL / Idea / Reference 三类知识笔记，主位挂 `Knowledge/<Type>/<Topic>/` 分类树、副入口 clone 到 `Journal/<yyyy>/<MM>/<dd>/` 日历，写入场景派 subagent 从 Claude Code session JSONL 中提炼笔记。

**Architecture:** `scripts/trilium.py` 保持单文件纯落盘器（ETAPI 客户端 + 分类树管理），只输出结构化 JSON 供 AI 消费。`agents/note-taker.md` 与 `references/note-triage-rules.md` 承载 subagent 的写入指令与规则。SKILL.md 定义主 Claude 的触发分派：写入派 subagent、读改删主题查询走 Bash 直调 CLI。

**Tech Stack:** Python 3.12+，`requests`，`markdown`，`pytest` + `unittest.mock`。

## Global Constraints

- Python 版本：`>=3.12`（保留 `pyproject.toml` 现值）
- 行长上限：88（ruff `line-length=88`）
- 不引入新运行时依赖
- 不使用表情符号（emoji）在代码、文档、提交信息与 CLI 输出中
- `note {til,idea,ref}` 落盘时**必须**添加 6 个通用 label（`#knowledge` `#type` `#topic` `#sourceSession` `#noteDate` `#iconClass`），ref 额外必须加 `#url`
- 主位在 `Knowledge/<Type>/<Topic>/`；日历副入口通过 ETAPI branches 二次挂载；clone 失败 warn 不 die
- 结构节点幂等键：`#typeNote=<til|idea|ref>` / `#topicNote=<type>:<Topic>`
- 图标格式必须是 `bx bx-<name>`；类型节点默认图标：TIL=`bx bx-bulb`、Idea=`bx bx-brain`、Reference=`bx bx-book-bookmark`；主题节点统一 `bx bx-folder`
- 除 `check` 外所有命令 stdout 输出 JSON，stderr 输出错误消息，AI 通过 exit code 判成败
- CLI 唯一调用方是 AI；stdin markdown 用 `charset=utf-8` PUT 到 Trilium（沿用 v2.0 做法）
- 版本号升至 `3.0.0`
- 不做迁移命令，历史 `#diary` 数据保留但不再由脚本管理

## File Structure

新建：

- `scripts/trilium.py` 大改（保留 `Trilium` 类骨架、`render_markdown`、`parse_date`、`load_config`、`Retry` 会话；删除 recap 相关，加入 `knowledge_root`、`ensure_type_path`、`ensure_topic_path`、`clone_note`、`merge_topic`、`cmd_note_*`、结构化 JSON stdout）
- `agents/note-taker.md`（新）—— subagent 的完整指令
- `references/note-triage-rules.md`（新）—— 值得记口径 + 类型判定 + 主题命名 + 图标词表
- `tests/test_commands.py`（新）—— cmd_note_* / cmd_list / cmd_get / cmd_update / cmd_delete / cmd_merge_topic 的端到端 mock
- `tests/test_check.py`（新）—— check 命令扩展场景
- `tests/fixtures/note_search_responses.json`（新）—— ETAPI search 响应样例

删除：

- `scripts/jsonl_render.py`
- `tests/test_jsonl_render.py`
- `tests/fixtures/sample_session.jsonl`（如仍存在）

改动：

- `SKILL.md` — 重写触发分派、subagent 调用协议、简报格式
- `README.md` — 重写定位、命令表、使用示例
- `pyproject.toml` — `version = "3.0.0"` + description
- `etc/config.example.json` — 加 `knowledgeRootId` 字段（可选）
- `tests/test_client.py` — 删所有 `TestCmdRecap*`、`TestResolveJsonlPath`；`Trilium` 类测试改为覆盖新方法
- `tests/test_pure.py` — 删 recap 相关；保留 `render_markdown` / `parse_date` / `build_parser`（更新 parser 用例）

---

## 任务顺序总览

1. **T1** 版本号 + config 示例 + 删除 jsonl_render（清空旧战场）
2. **T2** `knowledge_root()` 方法（Trilium 类扩展）
3. **T3** `ensure_type_path()` 方法（含类型默认图标）
4. **T4** `ensure_topic_path()` 方法（含 folder 图标）
5. **T5** `clone_note()` 方法（幂等 branches 挂载）
6. **T6** `cmd_note_til/idea/ref`（写入命令 + JSON stdout）
7. **T7** `cmd_list` 改造（`#knowledge` 检索 + JSON stdout）
8. **T8** `cmd_get` 改造（JSON stdout）
9. **T9** `cmd_update` 改造（去 `--topic` + 加 `--icon` + JSON stdout）
10. **T10** `cmd_delete` 改造（JSON stdout）
11. **T11** `cmd_note_topics`（列所有主题）
12. **T12** `cmd_note_merge_topic`（同类型内归并）
13. **T13** `cmd_check` 扩展（两个 root + 类型节点提示）
14. **T14** `build_parser` 重构（新 subcommand tree）
15. **T15** `references/note-triage-rules.md`
16. **T16** `agents/note-taker.md`
17. **T17** `SKILL.md` 重写
18. **T18** `README.md` 重写
19. **T19** 手动黑盒验证 + 收尾

---

### Task 1: 起分支 + 版本号 + 删旧战场

**Files:**
- Modify: `pyproject.toml`
- Modify: `etc/config.example.json`
- Delete: `scripts/jsonl_render.py`
- Delete: `tests/test_jsonl_render.py`
- Delete: `tests/fixtures/sample_session.jsonl`（若存在）

**Interfaces:**
- Consumes: 无
- Produces: 版本号 3.0.0；config 支持 `knowledgeRootId`；旧 jsonl 渲染器代码彻底移除

- [ ] **Step 1: 起工作分支**

```bash
git checkout -b refactor/knowledge-notes
```

- [ ] **Step 2: 升版本号 + 换 description**

编辑 `pyproject.toml`：

```toml
[project]
name = "trilium-diary"
version = "3.0.0"
description = "通用 Trilium 知识笔记助手：把 Claude Code 会话里的 TIL / 想法 / 参考资料写入分类树 + 日历双入口"
requires-python = ">=3.12"
dependencies = [
    "markdown>=3.5",
    "requests>=2.31",
]
```

其余段落不动。

- [ ] **Step 3: 扩展 config.example.json**

编辑 `etc/config.example.json`（保留 v2.0 三个字段，追加 knowledgeRootId）：

```json
{
  "server": "http://trilium.localhost",
  "token": "<ETAPI token>",
  "calendarRootId": "",
  "knowledgeRootId": ""
}
```

- [ ] **Step 4: 删旧文件**

```bash
git rm scripts/jsonl_render.py
git rm tests/test_jsonl_render.py
rm -f tests/fixtures/sample_session.jsonl
```

- [ ] **Step 5: 提交**

```bash
git add pyproject.toml etc/config.example.json
git commit -m "chore(v3): 起分支、升 3.0.0、加 knowledgeRootId 字段、删除 jsonl_render"
```

---

### Task 2: `Trilium.knowledge_root()` 方法

**Files:**
- Modify: `scripts/trilium.py`（`Trilium` 类内）
- Test: `tests/test_client.py`（TestTriliumClient 内新增）

**Interfaces:**
- Consumes: `self.cfg` 里可选的 `knowledgeRootId`；`self.search()` 已有方法
- Produces: `Trilium.knowledge_root() -> str`（返回知识根 noteId；找不到或多个 → `die`）

- [ ] **Step 1: 写失败测试**

在 `tests/test_client.py` 里，`TestTriliumClient` 类内追加：

```python
def test_knowledge_root_from_config(self):
    t = self._client(
        {"server": "http://x", "token": "t", "calendarRootId": "c",
         "knowledgeRootId": "k1"}
    )
    assert t.knowledge_root() == "k1"

def test_knowledge_root_auto_detect_single(self):
    t = self._client(
        {"server": "http://x", "token": "t", "calendarRootId": "c",
         "knowledgeRootId": ""}
    )
    with patch.object(
        t, "search", return_value=[{"noteId": "kn1", "title": "Knowledge"}]
    ):
        assert t.knowledge_root() == "kn1"

def test_knowledge_root_auto_detect_none_exits(self):
    t = self._client(
        {"server": "http://x", "token": "t", "calendarRootId": "c",
         "knowledgeRootId": ""}
    )
    with patch.object(t, "search", return_value=[]), pytest.raises(SystemExit):
        t.knowledge_root()

def test_knowledge_root_auto_detect_multiple_exits(self):
    t = self._client(
        {"server": "http://x", "token": "t", "calendarRootId": "c",
         "knowledgeRootId": ""}
    )
    with (
        patch.object(
            t,
            "search",
            return_value=[
                {"noteId": "a", "title": "K1"},
                {"noteId": "b", "title": "K2"},
            ],
        ),
        pytest.raises(SystemExit),
    ):
        t.knowledge_root()
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_client.py -k knowledge_root -v
```

Expected: FAIL —— `AttributeError: 'Trilium' object has no attribute 'knowledge_root'`

- [ ] **Step 3: 在 `load_config()` 里增加默认值**

编辑 `scripts/trilium.py` 的 `load_config()`（约 120-131 行），在返回前追加：

```python
    cfg.setdefault("calendarRootId", "")
    cfg.setdefault("knowledgeRootId", "")
    return cfg
```

- [ ] **Step 4: 在 `Trilium` 类里加 `knowledge_root()` 方法**

`calendar_root()` 方法下方添加：

```python
def knowledge_root(self):
    """Resolve the knowledge root note id (config override or #knowledgeRoot)."""
    if self.cfg.get("knowledgeRootId"):
        return self.cfg["knowledgeRootId"]
    hits = self.search("#knowledgeRoot", limit="5")
    if not hits:
        die(
            "找不到知识根（带 #knowledgeRoot 的笔记）。"
            "请在 etc/config.json 设置 knowledgeRootId，"
            "或在 Trilium 里建一条笔记打 #knowledgeRoot 标签。"
        )
    if len(hits) > 1:
        ids = ", ".join("{}({})".format(h["noteId"], h["title"]) for h in hits)
        die(
            f"发现多个 #knowledgeRoot：{ids}\n"
            "请在 etc/config.json 用 knowledgeRootId 指定。"
        )
    return hits[0]["noteId"]
```

- [ ] **Step 5: 运行测试确认通过**

```bash
uv run pytest tests/test_client.py -k knowledge_root -v
```

Expected: PASS 4 条

- [ ] **Step 6: 提交**

```bash
git add scripts/trilium.py tests/test_client.py
git commit -m "feat(trilium): add knowledge_root() with #knowledgeRoot auto-detect"
```

---

### Task 3: `Trilium.ensure_type_path()` 方法

**Files:**
- Modify: `scripts/trilium.py`
- Test: `tests/test_client.py`

**Interfaces:**
- Consumes: `Trilium.knowledge_root()`（T2）、`_child_with_label()`（已有）、`create_note()`（已有）、`add_label()`（已有）
- Produces:
  - `Trilium.ensure_type_path(type_key: str) -> str`：找/建 `Knowledge/<Type>/` 节点；`type_key` 取值 `"til" | "idea" | "ref"`；返回该节点 noteId
  - 模块常量 `TYPE_DISPLAY_NAMES = {"til": "TIL", "idea": "Ideas", "ref": "References"}`
  - 模块常量 `TYPE_DEFAULT_ICONS = {"til": "bx bx-bulb", "idea": "bx bx-brain", "ref": "bx bx-book-bookmark"}`

- [ ] **Step 1: 写失败测试**

`tests/test_client.py` 的 `TestTriliumClient` 类内追加：

```python
def test_ensure_type_path_existing(self):
    t = self._client()
    with (
        patch.object(t, "knowledge_root", return_value="kroot"),
        patch.object(t, "_child_with_label", return_value="tilNode"),
    ):
        assert t.ensure_type_path("til") == "tilNode"

def test_ensure_type_path_creates_with_defaults(self):
    from trilium import TYPE_DEFAULT_ICONS, TYPE_DISPLAY_NAMES

    t = self._client()
    with (
        patch.object(t, "knowledge_root", return_value="kroot"),
        patch.object(t, "_child_with_label", return_value=None),
        patch.object(
            t, "create_note", return_value={"note": {"noteId": "newTil"}}
        ) as create_call,
        patch.object(t, "add_label") as add_call,
    ):
        assert t.ensure_type_path("til") == "newTil"

    create_call.assert_called_once_with("kroot", TYPE_DISPLAY_NAMES["til"], "")
    label_names = [c.args[1] for c in add_call.call_args_list]
    assert "typeNote" in label_names
    assert "iconClass" in label_names
    icon_call = next(c for c in add_call.call_args_list if c.args[1] == "iconClass")
    assert icon_call.args[2] == TYPE_DEFAULT_ICONS["til"]
    type_call = next(c for c in add_call.call_args_list if c.args[1] == "typeNote")
    assert type_call.args[2] == "til"

def test_ensure_type_path_rejects_unknown_type(self):
    t = self._client()
    with pytest.raises(SystemExit):
        t.ensure_type_path("bogus")
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_client.py -k ensure_type_path -v
```

Expected: FAIL —— 常量未定义 / 方法不存在

- [ ] **Step 3: 在 `scripts/trilium.py` 添加常量**

`RECAP_ICON = "bx bx-conversation"` 那行（T14 会删掉，本 task 保留原样以免冲突）之后追加：

```python
TYPE_DISPLAY_NAMES = {"til": "TIL", "idea": "Ideas", "ref": "References"}
TYPE_DEFAULT_ICONS = {
    "til": "bx bx-bulb",
    "idea": "bx bx-brain",
    "ref": "bx bx-book-bookmark",
}
TOPIC_FOLDER_ICON = "bx bx-folder"
```

- [ ] **Step 4: 在 `Trilium` 类里添加 `ensure_type_path()`**

`knowledge_root()` 下方添加：

```python
def ensure_type_path(self, type_key: str) -> str:
    """Find-or-create `Knowledge/<Type>/`; return its noteId."""
    if type_key not in TYPE_DISPLAY_NAMES:
        die(f"未知的知识笔记类型: {type_key!r}（应为 til/idea/ref）")
    root_id = self.knowledge_root()
    found = self._child_with_label(root_id, "typeNote", type_key)
    if found:
        return found
    title = TYPE_DISPLAY_NAMES[type_key]
    nid = self.create_note(root_id, title, "")["note"]["noteId"]
    self.add_label(nid, "typeNote", type_key)
    self.add_label(nid, "iconClass", TYPE_DEFAULT_ICONS[type_key])
    return nid
```

- [ ] **Step 5: 运行测试确认通过**

```bash
uv run pytest tests/test_client.py -k ensure_type_path -v
```

Expected: PASS 3 条

- [ ] **Step 6: 提交**

```bash
git add scripts/trilium.py tests/test_client.py
git commit -m "feat(trilium): add ensure_type_path with type default icons"
```

---

### Task 4: `Trilium.ensure_topic_path()` 方法

**Files:**
- Modify: `scripts/trilium.py`
- Test: `tests/test_client.py`

**Interfaces:**
- Consumes: `ensure_type_path()`（T3）、`_child_with_label()`、`create_note()`、`add_label()`、模块常量 `TOPIC_FOLDER_ICON`
- Produces: `Trilium.ensure_topic_path(type_key: str, topic: str) -> str`：找/建 `Knowledge/<Type>/<Topic>/`；`#topicNote=<type>:<Topic>` 为幂等键；返回主题节点 noteId

- [ ] **Step 1: 写失败测试**

`TestTriliumClient` 内追加：

```python
def test_ensure_topic_path_existing(self):
    t = self._client()
    with (
        patch.object(t, "ensure_type_path", return_value="tilNode"),
        patch.object(t, "_child_with_label", return_value="pgTopic"),
    ):
        assert t.ensure_topic_path("til", "Postgres") == "pgTopic"

def test_ensure_topic_path_creates_with_folder_icon(self):
    from trilium import TOPIC_FOLDER_ICON

    t = self._client()
    with (
        patch.object(t, "ensure_type_path", return_value="tilNode"),
        patch.object(t, "_child_with_label", return_value=None),
        patch.object(
            t, "create_note", return_value={"note": {"noteId": "newTopic"}}
        ) as create_call,
        patch.object(t, "add_label") as add_call,
    ):
        assert t.ensure_topic_path("til", "Postgres") == "newTopic"

    create_call.assert_called_once_with("tilNode", "Postgres", "")
    labels = {c.args[1]: c.args[2] for c in add_call.call_args_list}
    assert labels["topicNote"] == "til:Postgres"
    assert labels["iconClass"] == TOPIC_FOLDER_ICON

def test_ensure_topic_path_rejects_empty_topic(self):
    t = self._client()
    with pytest.raises(SystemExit):
        t.ensure_topic_path("til", "")
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_client.py -k ensure_topic_path -v
```

Expected: FAIL —— `AttributeError`

- [ ] **Step 3: 添加 `ensure_topic_path()` 方法**

`ensure_type_path()` 下方追加：

```python
def ensure_topic_path(self, type_key: str, topic: str) -> str:
    """Find-or-create `Knowledge/<Type>/<Topic>/`; return its noteId."""
    if not topic or not topic.strip():
        die("主题名不能为空")
    topic = topic.strip()
    type_node = self.ensure_type_path(type_key)
    key = f"{type_key}:{topic}"
    found = self._child_with_label(type_node, "topicNote", key)
    if found:
        return found
    nid = self.create_note(type_node, topic, "")["note"]["noteId"]
    self.add_label(nid, "topicNote", key)
    self.add_label(nid, "iconClass", TOPIC_FOLDER_ICON)
    return nid
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/test_client.py -k ensure_topic_path -v
```

Expected: PASS 3 条

- [ ] **Step 5: 提交**

```bash
git add scripts/trilium.py tests/test_client.py
git commit -m "feat(trilium): add ensure_topic_path with topic:<type>:<Topic> key"
```

---

### Task 5: `Trilium.clone_note()` 方法

**Files:**
- Modify: `scripts/trilium.py`
- Test: `tests/test_client.py`

**Interfaces:**
- Consumes: `_req()`（已有）、`get_note()`（已有）
- Produces: `Trilium.clone_note(note_id: str, parent_id: str) -> dict` 返回 `{"cloned": bool, "alreadyPresent": bool, "error": str | None}`；已挂过 `alreadyPresent=True`、`cloned=True`；成功 `cloned=True, alreadyPresent=False`；HTTP 错误 `cloned=False, error=<msg>`；**不 die**

- [ ] **Step 1: 写失败测试**

`TestTriliumClient` 内追加：

```python
def test_clone_note_creates_branch(self):
    t = self._client()
    with (
        patch.object(
            t, "get_note", return_value={"parentNoteIds": ["topicA"]}
        ),
        patch.object(t, "_req") as req_call,
    ):
        req_call.return_value = MagicMock()
        result = t.clone_note("noteX", "dayY")

    assert result == {"cloned": True, "alreadyPresent": False, "error": None}
    req_call.assert_called_once()
    method, path = req_call.call_args.args[0], req_call.call_args.args[1]
    assert method == "POST"
    assert path == "/branches"
    payload = req_call.call_args.kwargs["json"]
    assert payload == {"noteId": "noteX", "parentNoteId": "dayY"}

def test_clone_note_already_present(self):
    t = self._client()
    with (
        patch.object(
            t, "get_note", return_value={"parentNoteIds": ["topicA", "dayY"]}
        ),
        patch.object(t, "_req") as req_call,
    ):
        result = t.clone_note("noteX", "dayY")

    assert result == {"cloned": True, "alreadyPresent": True, "error": None}
    req_call.assert_not_called()

def test_clone_note_http_error_does_not_die(self):
    t = self._client()
    with (
        patch.object(
            t, "get_note", return_value={"parentNoteIds": ["topicA"]}
        ),
        patch.object(t, "_req", side_effect=SystemExit("boom")),
    ):
        # clone_note swallows _req's die/SystemExit into structured error
        result = t.clone_note("noteX", "dayY")

    assert result["cloned"] is False
    assert result["alreadyPresent"] is False
    assert "boom" in result["error"] or result["error"]
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_client.py -k clone_note -v
```

Expected: FAIL —— 方法不存在

- [ ] **Step 3: 添加 `clone_note()` 方法**

`ensure_topic_path()` 下方追加：

```python
def clone_note(self, note_id: str, parent_id: str) -> dict:
    """Attach note_id as an additional child of parent_id (idempotent).

    Uses ETAPI POST /branches. Returns a structured result; never dies.
    """
    try:
        note = self.get_note(note_id)
    except SystemExit as e:
        return {"cloned": False, "alreadyPresent": False, "error": str(e)}
    if parent_id in (note.get("parentNoteIds") or []):
        return {"cloned": True, "alreadyPresent": True, "error": None}
    try:
        self._req(
            "POST",
            "/branches",
            json={"noteId": note_id, "parentNoteId": parent_id},
        )
    except SystemExit as e:
        return {"cloned": False, "alreadyPresent": False, "error": str(e)}
    return {"cloned": True, "alreadyPresent": False, "error": None}
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/test_client.py -k clone_note -v
```

Expected: PASS 3 条

- [ ] **Step 5: 提交**

```bash
git add scripts/trilium.py tests/test_client.py
git commit -m "feat(trilium): add clone_note via /branches (idempotent, non-fatal)"
```

---

### Task 6: `cmd_note_til / idea / ref` 写入命令

**Files:**
- Modify: `scripts/trilium.py`
- Create: `tests/test_commands.py`

**Interfaces:**
- Consumes: `Trilium.ensure_topic_path()`（T4）、`ensure_date_path()`（已有）、`clone_note()`（T5）、`render_markdown()`（已有）、`create_note()`、`add_label()`、`TYPE_DEFAULT_ICONS`
- Produces:
  - 单个共享内部函数 `_cmd_note_write(args, type_key: str) -> None`：读 stdin → 写 note + 6~7 个 label → clone 到日历 → `print(json.dumps({...}))`
  - `cmd_note_til(args)` / `cmd_note_idea(args)` / `cmd_note_ref(args)` 都委托 `_cmd_note_write`（`cmd_note_ref` 额外校验 `args.url` 必填并写入 `#url` label）
  - stdout JSON schema：`{"noteId": str, "url": str, "cloned": bool}`；clone 失败时额外 `"cloneError": str`

**注意：** 本 task 只**新增**函数不改 parser；T14 会把 parser 换到新命令表。此阶段函数通过测试直接调用即可，无需 CLI 可跑。

- [ ] **Step 1: 创建 tests/test_commands.py 骨架 + 写 til 成功用例**

```python
"""Integration tests for cmd_note_* / cmd_list / cmd_get / cmd_update / cmd_delete / cmd_merge_topic."""

import io
import json
import os
import sys
from argparse import Namespace
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from trilium import (
    TYPE_DEFAULT_ICONS,
    cmd_note_idea,
    cmd_note_ref,
    cmd_note_til,
)


def _make_config(tmp_path):
    cfg = {
        "server": "http://localhost:8080",
        "token": "test-token",
        "calendarRootId": "cal",
        "knowledgeRootId": "know",
    }
    p = tmp_path / "etc" / "config.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg), encoding="utf-8")
    return str(p)


class TestNoteTilHappyPath:
    def test_creates_note_labels_and_clone(self, tmp_path, capsys, monkeypatch):
        monkeypatch.setattr("trilium.CONFIG_PATH", _make_config(tmp_path))
        monkeypatch.setattr("sys.stdin", io.StringIO("# body\ncontent"))

        with patch("trilium.Trilium") as TClass:
            t = TClass.return_value
            t.ensure_topic_path.return_value = "topicNoteId"
            t.ensure_date_path.return_value = "dayNoteId"
            t.create_note.return_value = {"note": {"noteId": "abc123"}}
            t.clone_note.return_value = {
                "cloned": True, "alreadyPresent": False, "error": None,
            }

            args = Namespace(
                topic="Postgres",
                title="TIL: timestamps",
                source_session="sess-1",
                note_date="2026-07-03",
                icon=None,
            )
            cmd_note_til(args)

        # 验证结构调用
        t.ensure_topic_path.assert_called_once_with("til", "Postgres")
        # 6 个通用 label
        label_names = {c.args[1] for c in t.add_label.call_args_list}
        assert label_names == {
            "knowledge", "type", "topic", "sourceSession", "noteDate", "iconClass",
        }
        # 默认图标
        icon_val = next(
            c.args[2] for c in t.add_label.call_args_list if c.args[1] == "iconClass"
        )
        assert icon_val == TYPE_DEFAULT_ICONS["til"]
        # clone 到日笔记
        t.clone_note.assert_called_once_with("abc123", "dayNoteId")

        # stdout JSON
        out = json.loads(capsys.readouterr().out)
        assert out == {
            "noteId": "abc123",
            "url": "http://localhost:8080/#root/abc123",
            "cloned": True,
        }

    def test_uses_custom_icon_when_provided(self, tmp_path, capsys, monkeypatch):
        monkeypatch.setattr("trilium.CONFIG_PATH", _make_config(tmp_path))
        monkeypatch.setattr("sys.stdin", io.StringIO("body"))

        with patch("trilium.Trilium") as TClass:
            t = TClass.return_value
            t.ensure_topic_path.return_value = "topic"
            t.ensure_date_path.return_value = "day"
            t.create_note.return_value = {"note": {"noteId": "n1"}}
            t.clone_note.return_value = {
                "cloned": True, "alreadyPresent": False, "error": None,
            }

            args = Namespace(
                topic="Postgres",
                title="t",
                source_session="s",
                note_date="2026-07-03",
                icon="bx bx-data",
            )
            cmd_note_til(args)

        icon_val = next(
            c.args[2] for c in t.add_label.call_args_list if c.args[1] == "iconClass"
        )
        assert icon_val == "bx bx-data"

    def test_empty_stdin_dies(self, tmp_path, monkeypatch):
        monkeypatch.setattr("trilium.CONFIG_PATH", _make_config(tmp_path))
        monkeypatch.setattr("sys.stdin", io.StringIO("   \n\n"))

        args = Namespace(
            topic="X", title="t", source_session="s",
            note_date="2026-07-03", icon=None,
        )
        with pytest.raises(SystemExit):
            cmd_note_til(args)
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_commands.py -v
```

Expected: FAIL —— `ImportError: cannot import name 'cmd_note_til' from 'trilium'`

- [ ] **Step 3: 在 `scripts/trilium.py` 添加内部辅助 + 三个 cmd**

`cmd_recap` 上方（保留 recap 直到 T14）插入：

```python
def _note_url(cfg, note_id: str) -> str:
    return "{}/#root/{}".format(cfg["server"], note_id)


def _read_stdin_markdown() -> str:
    md = sys.stdin.read()
    if not md or not md.strip():
        die("正文为空，请从 stdin 传入 markdown")
    return md


def _cmd_note_write(args, type_key: str) -> None:
    cfg = load_config()
    t = Trilium(cfg)

    md = _read_stdin_markdown()
    html = render_markdown(md)

    topic_id = t.ensure_topic_path(type_key, args.topic)
    nid = t.create_note(topic_id, args.title, html, ntype="text")["note"]["noteId"]

    icon = args.icon if args.icon else TYPE_DEFAULT_ICONS[type_key]
    t.add_label(nid, "knowledge")
    t.add_label(nid, "type", type_key)
    t.add_label(nid, "topic", args.topic)
    t.add_label(nid, "sourceSession", args.source_session)
    t.add_label(nid, "noteDate", args.note_date)
    t.add_label(nid, "iconClass", icon)
    if type_key == "ref":
        t.add_label(nid, "url", args.url)

    date = parse_date(args.note_date)
    day_id = t.ensure_date_path(date)
    clone = t.clone_note(nid, day_id)

    out = {
        "noteId": nid,
        "url": _note_url(cfg, nid),
        "cloned": clone["cloned"],
    }
    if not clone["cloned"] and clone.get("error"):
        out["cloneError"] = clone["error"]
        print(
            f"⚠ clone 到日历失败：{clone['error']}",
            file=sys.stderr,
        )
    print(json.dumps(out, ensure_ascii=False))


def cmd_note_til(args) -> None:
    _cmd_note_write(args, "til")


def cmd_note_idea(args) -> None:
    _cmd_note_write(args, "idea")


def cmd_note_ref(args) -> None:
    if not getattr(args, "url", None):
        die("note ref 必须提供 --url")
    _cmd_note_write(args, "ref")
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/test_commands.py -v
```

Expected: PASS 3 条

- [ ] **Step 5: 追加 idea / ref 覆盖测试**

在 `tests/test_commands.py` 追加：

```python
class TestNoteIdea:
    def test_type_key_is_idea(self, tmp_path, capsys, monkeypatch):
        monkeypatch.setattr("trilium.CONFIG_PATH", _make_config(tmp_path))
        monkeypatch.setattr("sys.stdin", io.StringIO("body"))
        with patch("trilium.Trilium") as TClass:
            t = TClass.return_value
            t.ensure_topic_path.return_value = "topic"
            t.ensure_date_path.return_value = "day"
            t.create_note.return_value = {"note": {"noteId": "i1"}}
            t.clone_note.return_value = {
                "cloned": True, "alreadyPresent": False, "error": None,
            }
            args = Namespace(
                topic="Trilium", title="t", source_session="s",
                note_date="2026-07-03", icon=None,
            )
            cmd_note_idea(args)
        t.ensure_topic_path.assert_called_once_with("idea", "Trilium")
        type_val = next(
            c.args[2] for c in t.add_label.call_args_list if c.args[1] == "type"
        )
        assert type_val == "idea"


class TestNoteRef:
    def test_adds_url_label(self, tmp_path, capsys, monkeypatch):
        monkeypatch.setattr("trilium.CONFIG_PATH", _make_config(tmp_path))
        monkeypatch.setattr("sys.stdin", io.StringIO("body"))
        with patch("trilium.Trilium") as TClass:
            t = TClass.return_value
            t.ensure_topic_path.return_value = "topic"
            t.ensure_date_path.return_value = "day"
            t.create_note.return_value = {"note": {"noteId": "r1"}}
            t.clone_note.return_value = {
                "cloned": True, "alreadyPresent": False, "error": None,
            }
            args = Namespace(
                topic="SQLite", title="t", source_session="s",
                note_date="2026-07-03", icon=None, url="https://example.com/x",
            )
            cmd_note_ref(args)
        labels = {c.args[1]: c.args[2] for c in t.add_label.call_args_list}
        assert labels["url"] == "https://example.com/x"

    def test_missing_url_dies(self, tmp_path, monkeypatch):
        monkeypatch.setattr("trilium.CONFIG_PATH", _make_config(tmp_path))
        monkeypatch.setattr("sys.stdin", io.StringIO("body"))
        args = Namespace(
            topic="X", title="t", source_session="s",
            note_date="2026-07-03", icon=None, url=None,
        )
        with pytest.raises(SystemExit):
            cmd_note_ref(args)


class TestCloneFallback:
    def test_clone_failure_reports_and_continues(
        self, tmp_path, capsys, monkeypatch
    ):
        monkeypatch.setattr("trilium.CONFIG_PATH", _make_config(tmp_path))
        monkeypatch.setattr("sys.stdin", io.StringIO("body"))
        with patch("trilium.Trilium") as TClass:
            t = TClass.return_value
            t.ensure_topic_path.return_value = "topic"
            t.ensure_date_path.return_value = "day"
            t.create_note.return_value = {"note": {"noteId": "n1"}}
            t.clone_note.return_value = {
                "cloned": False, "alreadyPresent": False, "error": "http 500",
            }
            args = Namespace(
                topic="X", title="t", source_session="s",
                note_date="2026-07-03", icon=None,
            )
            cmd_note_til(args)
        cap = capsys.readouterr()
        out = json.loads(cap.out)
        assert out["cloned"] is False
        assert out["cloneError"] == "http 500"
        assert "clone 到日历失败" in cap.err
```

- [ ] **Step 6: 运行测试确认通过**

```bash
uv run pytest tests/test_commands.py -v
```

Expected: PASS 全部（6 条）

- [ ] **Step 7: 提交**

```bash
git add scripts/trilium.py tests/test_commands.py
git commit -m "feat(trilium): add cmd_note_til/idea/ref with JSON stdout"
```

---

### Task 7: `cmd_list` 改造为 `#knowledge` 检索 + JSON

**Files:**
- Modify: `scripts/trilium.py`（改写 `cmd_list`）
- Modify: `tests/test_commands.py`
- Modify: `tests/test_client.py`（删除老 `cmd_list` 相关用例，如有）

**Interfaces:**
- Consumes: `Trilium.search()`（已有）
- Produces: 新的 `cmd_list(args)`；stdout `{"items": [{"noteId", "title", "type", "topic", "noteDate", "sourceSession"}, ...]}`

- [ ] **Step 1: 写失败测试**

`tests/test_commands.py` 追加：

```python
from trilium import cmd_list


class TestList:
    def _make_hits(self):
        return [
            {
                "noteId": "n1",
                "title": "TIL: pg tz",
                "attributes": [
                    {"name": "type", "value": "til"},
                    {"name": "topic", "value": "Postgres"},
                    {"name": "noteDate", "value": "2026-07-03"},
                    {"name": "sourceSession", "value": "sess-1"},
                ],
            },
            {
                "noteId": "n2",
                "title": "Idea: workspaces",
                "attributes": [
                    {"name": "type", "value": "idea"},
                    {"name": "topic", "value": "Trilium"},
                    {"name": "noteDate", "value": "2026-07-03"},
                    {"name": "sourceSession", "value": "sess-1"},
                ],
            },
        ]

    def test_list_default_uses_knowledge_tag(
        self, tmp_path, capsys, monkeypatch
    ):
        monkeypatch.setattr("trilium.CONFIG_PATH", _make_config(tmp_path))
        with patch("trilium.Trilium") as TClass:
            t = TClass.return_value
            t.search.return_value = self._make_hits()
            args = Namespace(
                type=None, topic=None, note_date=None,
                source_session=None, limit=50,
            )
            cmd_list(args)
        expr = t.search.call_args.args[0]
        assert "#knowledge" in expr
        out = json.loads(capsys.readouterr().out)
        assert len(out["items"]) == 2
        first = out["items"][0]
        assert first["noteId"] == "n1"
        assert first["type"] == "til"
        assert first["topic"] == "Postgres"
        assert first["noteDate"] == "2026-07-03"
        assert first["sourceSession"] == "sess-1"

    def test_list_filters_compose(self, tmp_path, capsys, monkeypatch):
        monkeypatch.setattr("trilium.CONFIG_PATH", _make_config(tmp_path))
        with patch("trilium.Trilium") as TClass:
            t = TClass.return_value
            t.search.return_value = []
            args = Namespace(
                type="til", topic="Postgres", note_date="2026-07-03",
                source_session="sess-1", limit=10,
            )
            cmd_list(args)
        expr = t.search.call_args.args[0]
        assert "#knowledge" in expr
        assert '#type="til"' in expr
        assert '#topic="Postgres"' in expr
        assert '#noteDate="2026-07-03"' in expr
        assert '#sourceSession="sess-1"' in expr
        assert t.search.call_args.kwargs["limit"] == "10"

    def test_list_empty_returns_empty_items(
        self, tmp_path, capsys, monkeypatch
    ):
        monkeypatch.setattr("trilium.CONFIG_PATH", _make_config(tmp_path))
        with patch("trilium.Trilium") as TClass:
            t = TClass.return_value
            t.search.return_value = []
            args = Namespace(
                type=None, topic=None, note_date=None,
                source_session=None, limit=50,
            )
            cmd_list(args)
        out = json.loads(capsys.readouterr().out)
        assert out == {"items": []}
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_commands.py::TestList -v
```

Expected: FAIL —— 老 cmd_list 输出文本 or JSON schema 不一致

- [ ] **Step 3: 改写 `cmd_list`**

替换 `scripts/trilium.py` 中的整个 `cmd_list` 函数：

```python
def cmd_list(args):
    cfg = load_config()
    t = Trilium(cfg)

    parts = ["#knowledge"]
    if args.type:
        parts.append(f'#type="{args.type}"')
    if args.topic:
        parts.append(f'#topic="{args.topic}"')
    if args.note_date:
        parts.append(f'#noteDate="{args.note_date}"')
    if args.source_session:
        parts.append(f'#sourceSession="{args.source_session}"')
    expr = " ".join(parts)

    rows = t.search(
        expr,
        orderBy="dateCreated",
        orderDirection="desc",
        limit=str(args.limit),
    )
    items = []
    for n in rows:
        attrs = {a["name"]: a["value"] for a in n.get("attributes", [])}
        items.append({
            "noteId": n.get("noteId"),
            "title": n.get("title"),
            "type": attrs.get("type", ""),
            "topic": attrs.get("topic", ""),
            "noteDate": attrs.get("noteDate", ""),
            "sourceSession": attrs.get("sourceSession", ""),
        })
    print(json.dumps({"items": items}, ensure_ascii=False))
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/test_commands.py::TestList -v
```

Expected: PASS 3 条

- [ ] **Step 5: 提交**

```bash
git add scripts/trilium.py tests/test_commands.py
git commit -m "refactor(trilium): cmd_list uses #knowledge, JSON stdout"
```

---

### Task 8: `cmd_get` 改造为 JSON

**Files:**
- Modify: `scripts/trilium.py`
- Modify: `tests/test_commands.py`

**Interfaces:**
- Consumes: `Trilium.get_note()`、`get_note_content()`（已有）
- Produces: 新 `cmd_get`；stdout `{"noteId", "title", "type", "topic", "noteDate", "sourceSession", "iconClass", "url"}`；带 `--content` 时追加 `"content": <html>`

- [ ] **Step 1: 写失败测试**

`tests/test_commands.py` 追加：

```python
from trilium import cmd_get


class TestGet:
    def _note(self):
        return {
            "noteId": "n1",
            "title": "TIL: tz",
            "attributes": [
                {"name": "type", "value": "til"},
                {"name": "topic", "value": "Postgres"},
                {"name": "noteDate", "value": "2026-07-03"},
                {"name": "sourceSession", "value": "sess-1"},
                {"name": "iconClass", "value": "bx bx-data"},
            ],
        }

    def test_get_returns_metadata_json(
        self, tmp_path, capsys, monkeypatch
    ):
        monkeypatch.setattr("trilium.CONFIG_PATH", _make_config(tmp_path))
        with patch("trilium.Trilium") as TClass:
            t = TClass.return_value
            t.get_note.return_value = self._note()
            args = Namespace(note_id="n1", content=False)
            cmd_get(args)
        out = json.loads(capsys.readouterr().out)
        assert out == {
            "noteId": "n1",
            "title": "TIL: tz",
            "type": "til",
            "topic": "Postgres",
            "noteDate": "2026-07-03",
            "sourceSession": "sess-1",
            "iconClass": "bx bx-data",
            "url": "http://localhost:8080/#root/n1",
        }

    def test_get_with_content_adds_content_field(
        self, tmp_path, capsys, monkeypatch
    ):
        monkeypatch.setattr("trilium.CONFIG_PATH", _make_config(tmp_path))
        with patch("trilium.Trilium") as TClass:
            t = TClass.return_value
            t.get_note.return_value = self._note()
            t.get_note_content.return_value = "<p>body</p>"
            args = Namespace(note_id="n1", content=True)
            cmd_get(args)
        out = json.loads(capsys.readouterr().out)
        assert out["content"] == "<p>body</p>"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_commands.py::TestGet -v
```

Expected: FAIL

- [ ] **Step 3: 改写 `cmd_get`**

替换 `scripts/trilium.py` 中的整个 `cmd_get` 函数：

```python
def cmd_get(args):
    cfg = load_config()
    t = Trilium(cfg)
    note = t.get_note(args.note_id)
    attrs = {a["name"]: a["value"] for a in note.get("attributes", [])}
    out = {
        "noteId": note.get("noteId", args.note_id),
        "title": note.get("title", ""),
        "type": attrs.get("type", ""),
        "topic": attrs.get("topic", ""),
        "noteDate": attrs.get("noteDate", ""),
        "sourceSession": attrs.get("sourceSession", ""),
        "iconClass": attrs.get("iconClass", ""),
        "url": _note_url(cfg, args.note_id),
    }
    if args.content:
        out["content"] = t.get_note_content(args.note_id)
    print(json.dumps(out, ensure_ascii=False))
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/test_commands.py::TestGet -v
```

Expected: PASS 2 条

- [ ] **Step 5: 提交**

```bash
git add scripts/trilium.py tests/test_commands.py
git commit -m "refactor(trilium): cmd_get emits JSON, drops diaryType fallback"
```

---

### Task 9: `cmd_update` 改造（去 `--topic`、加 `--icon`、JSON stdout）

**Files:**
- Modify: `scripts/trilium.py`
- Modify: `tests/test_commands.py`

**Interfaces:**
- Consumes: `Trilium.update_note()`、`update_note_content()`、`get_note()`、`add_label()`、`patch_attribute()`（已有）
- Produces: 新 `cmd_update`；参数 `note_id, title=None, icon=None`（**不接受** `--topic` 也不接受 `--content-file`；正文改动从 stdin 读，可空跳过）；stdout `{"noteId", "ok": true}`

- [ ] **Step 1: 写失败测试**

`tests/test_commands.py` 追加：

```python
from trilium import cmd_update


class TestUpdate:
    def _note_with_icon(self):
        return {
            "noteId": "n1",
            "title": "old title",
            "attributes": [
                {"attributeId": "attrIcon", "name": "iconClass", "value": "bx bx-x"},
            ],
        }

    def _note_without_icon(self):
        return {"noteId": "n1", "title": "old", "attributes": []}

    def test_update_title_only(self, tmp_path, capsys, monkeypatch):
        monkeypatch.setattr("trilium.CONFIG_PATH", _make_config(tmp_path))
        # empty stdin (tty-like): should NOT touch content
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        # Also mark as tty so cmd_update does not attempt to read
        monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
        with patch("trilium.Trilium") as TClass:
            t = TClass.return_value
            t.get_note.return_value = self._note_without_icon()
            args = Namespace(note_id="n1", title="new title", icon=None)
            cmd_update(args)
        t.update_note.assert_called_once_with("n1", title="new title")
        t.update_note_content.assert_not_called()
        out = json.loads(capsys.readouterr().out)
        assert out == {"noteId": "n1", "ok": True}

    def test_update_content_from_stdin(self, tmp_path, capsys, monkeypatch):
        monkeypatch.setattr("trilium.CONFIG_PATH", _make_config(tmp_path))
        fake = io.StringIO("## new body")
        fake.isatty = lambda: False
        monkeypatch.setattr("sys.stdin", fake)
        with patch("trilium.Trilium") as TClass:
            t = TClass.return_value
            t.get_note.return_value = self._note_without_icon()
            args = Namespace(note_id="n1", title=None, icon=None)
            cmd_update(args)
        t.update_note_content.assert_called_once()
        html_arg = t.update_note_content.call_args.args[1]
        assert "<h2>new body" in html_arg

    def test_update_icon_patches_existing_attr(
        self, tmp_path, capsys, monkeypatch
    ):
        monkeypatch.setattr("trilium.CONFIG_PATH", _make_config(tmp_path))
        fake = io.StringIO("")
        fake.isatty = lambda: True
        monkeypatch.setattr("sys.stdin", fake)
        with patch("trilium.Trilium") as TClass:
            t = TClass.return_value
            t.get_note.return_value = self._note_with_icon()
            args = Namespace(note_id="n1", title=None, icon="bx bx-data")
            cmd_update(args)
        t.patch_attribute.assert_called_once_with("attrIcon", value="bx bx-data")
        t.add_label.assert_not_called()

    def test_update_icon_adds_label_when_missing(
        self, tmp_path, capsys, monkeypatch
    ):
        monkeypatch.setattr("trilium.CONFIG_PATH", _make_config(tmp_path))
        fake = io.StringIO("")
        fake.isatty = lambda: True
        monkeypatch.setattr("sys.stdin", fake)
        with patch("trilium.Trilium") as TClass:
            t = TClass.return_value
            t.get_note.return_value = self._note_without_icon()
            args = Namespace(note_id="n1", title=None, icon="bx bx-cog")
            cmd_update(args)
        t.add_label.assert_called_once_with("n1", "iconClass", "bx bx-cog")
        t.patch_attribute.assert_not_called()
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_commands.py::TestUpdate -v
```

Expected: FAIL —— 参数名不一致 / stdout 格式不同

- [ ] **Step 3: 改写 `cmd_update`**

替换 `scripts/trilium.py` 中的整个 `cmd_update` 函数：

```python
def cmd_update(args):
    cfg = load_config()
    t = Trilium(cfg)

    if args.title is not None:
        t.update_note(args.note_id, title=args.title)

    if not sys.stdin.isatty():
        md = sys.stdin.read()
        if md.strip():
            html = render_markdown(md)
            t.update_note_content(args.note_id, html)

    if args.icon is not None:
        note = t.get_note(args.note_id)
        existing = next(
            (a for a in note.get("attributes", []) if a["name"] == "iconClass"),
            None,
        )
        if existing:
            t.patch_attribute(existing["attributeId"], value=args.icon)
        else:
            t.add_label(args.note_id, "iconClass", args.icon)

    print(json.dumps(
        {"noteId": args.note_id, "ok": True}, ensure_ascii=False
    ))
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/test_commands.py::TestUpdate -v
```

Expected: PASS 4 条

- [ ] **Step 5: 提交**

```bash
git add scripts/trilium.py tests/test_commands.py
git commit -m "refactor(trilium): cmd_update drops --topic/--content-file, adds --icon patch"
```

---

### Task 10: `cmd_delete` 改造为 JSON

**Files:**
- Modify: `scripts/trilium.py`
- Modify: `tests/test_commands.py`

**Interfaces:**
- Consumes: `Trilium.delete_note()`（已有）
- Produces: 新 `cmd_delete`；stdout `{"noteId", "ok": true}`

- [ ] **Step 1: 写失败测试**

`tests/test_commands.py` 追加：

```python
from trilium import cmd_delete


class TestDelete:
    def test_delete_emits_json(self, tmp_path, capsys, monkeypatch):
        monkeypatch.setattr("trilium.CONFIG_PATH", _make_config(tmp_path))
        with patch("trilium.Trilium") as TClass:
            t = TClass.return_value
            args = Namespace(note_id="n1")
            cmd_delete(args)
        t.delete_note.assert_called_once_with("n1")
        out = json.loads(capsys.readouterr().out)
        assert out == {"noteId": "n1", "ok": True}
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_commands.py::TestDelete -v
```

Expected: FAIL

- [ ] **Step 3: 改写 `cmd_delete`**

替换整个函数：

```python
def cmd_delete(args):
    cfg = load_config()
    t = Trilium(cfg)
    t.delete_note(args.note_id)
    print(json.dumps({"noteId": args.note_id, "ok": True}, ensure_ascii=False))
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/test_commands.py::TestDelete -v
```

Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add scripts/trilium.py tests/test_commands.py
git commit -m "refactor(trilium): cmd_delete emits JSON, no preview"
```

---

### Task 11: `cmd_note_topics` 列所有主题

**Files:**
- Modify: `scripts/trilium.py`
- Modify: `tests/test_commands.py`

**Interfaces:**
- Consumes: `Trilium.search()`
- Produces: 新 `cmd_note_topics(args)`；stdout `{"topics": [{"type", "topic", "noteId", "count"}, ...]}`；`count` 是该主题下**知识笔记**数（不是主题子笔记数）

- [ ] **Step 1: 写失败测试**

`tests/test_commands.py` 追加：

```python
from trilium import cmd_note_topics


class TestNoteTopics:
    def _topic_notes(self):
        # 主题节点自身
        return [
            {
                "noteId": "topicPg",
                "title": "Postgres",
                "attributes": [
                    {"name": "topicNote", "value": "til:Postgres"},
                ],
            },
            {
                "noteId": "topicRust",
                "title": "Rust",
                "attributes": [
                    {"name": "topicNote", "value": "idea:Rust"},
                ],
            },
        ]

    def test_topics_lists_and_counts(self, tmp_path, capsys, monkeypatch):
        monkeypatch.setattr("trilium.CONFIG_PATH", _make_config(tmp_path))

        def _search(expr, **_):
            if "#topicNote" in expr:
                return self._topic_notes()
            # count queries: match by #knowledge #type=X #topic=Y
            if 'topic="Postgres"' in expr:
                return [{"noteId": "n1"}, {"noteId": "n2"}]
            if 'topic="Rust"' in expr:
                return [{"noteId": "n3"}]
            return []

        with patch("trilium.Trilium") as TClass:
            t = TClass.return_value
            t.search.side_effect = _search
            args = Namespace()
            cmd_note_topics(args)

        out = json.loads(capsys.readouterr().out)
        topics = sorted(out["topics"], key=lambda x: x["topic"])
        assert topics == [
            {"type": "til", "topic": "Postgres", "noteId": "topicPg", "count": 2},
            {"type": "idea", "topic": "Rust", "noteId": "topicRust", "count": 1},
        ]
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_commands.py::TestNoteTopics -v
```

Expected: FAIL

- [ ] **Step 3: 添加 `cmd_note_topics`**

在 `cmd_note_ref` 下方追加：

```python
def cmd_note_topics(args):
    cfg = load_config()
    t = Trilium(cfg)
    hits = t.search("#topicNote", limit="1000")
    topics = []
    for n in hits:
        key = next(
            (a["value"] for a in n.get("attributes", []) if a["name"] == "topicNote"),
            "",
        )
        if ":" not in key:
            continue
        type_key, topic = key.split(":", 1)
        cnt_hits = t.search(
            f'#knowledge #type="{type_key}" #topic="{topic}"',
            limit="1000",
        )
        topics.append({
            "type": type_key,
            "topic": topic,
            "noteId": n.get("noteId"),
            "count": len(cnt_hits),
        })
    print(json.dumps({"topics": topics}, ensure_ascii=False))
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/test_commands.py::TestNoteTopics -v
```

Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add scripts/trilium.py tests/test_commands.py
git commit -m "feat(trilium): add cmd_note_topics listing #topicNote with counts"
```

---

### Task 12: `cmd_note_merge_topic` 同类型内归并

**Files:**
- Modify: `scripts/trilium.py`
- Modify: `tests/test_commands.py`

**Interfaces:**
- Consumes: `Trilium.search()`、`ensure_topic_path()`（T4）、`patch_attribute()`、`_req()`（用于 branches）、`delete_note()`（已有）
- Produces: 新 `cmd_note_merge_topic(args)`；args: `type: str, from_topic: str, to_topic: str`；行为：
  1. 找 `from_topic` 下所有笔记（用 `#knowledge #type=<T> #topic=<from>` 搜）
  2. 逐条：修改其 `#topic` label 值为 `to_topic`；把主位从 fromTopic 节点移到 toTopic 节点（改 branch parent）
  3. 若 fromTopic 主题节点 clone 后无子笔记则删除
  4. stdout `{"moved": <n>, "fromNoteId": <id>, "toNoteId": <id>, "fromEmpty": <bool>}`

**注意：** 移动主位需要更新 branch。搜索 fromTopic 节点自身 + toTopic 节点自身用 `#topicNote=<type>:<name>`；找移动目标 branch 需要 `note.get("parentBranchIds")`。为简化，本 task **改用 delete+recreate 分支**：找出该 note 挂在 fromTopic 的 branchId，`DELETE /branches/<id>`；再 `POST /branches` 挂到 toTopic。

需要额外方法 `Trilium.list_branches_of(note_id) -> list[dict]`（返回 `[{"branchId", "parentNoteId"}, ...]`）——从 `get_note()` 返回中提取 `parentBranchIds` 拿 branchId 再 `GET /branches/{id}` 查 parent。因为 ETAPI 无"按 noteId+parentNoteId 查 branch"端点，简化做法：`get_note` 返回中 `parentBranchIds` 与 `parentNoteIds` 顺序对应（Trilium 实现），可直接配对。若不确定，**先加一个 `find_branch()` 方法**再用。

- [ ] **Step 1: 加辅助方法 `find_branch()` + 测试**

在 `Trilium` 类 `clone_note()` 下方追加：

```python
def find_branch(self, note_id: str, parent_id: str) -> str | None:
    """Return the branchId connecting note_id to parent_id, or None."""
    note = self.get_note(note_id)
    branch_ids = note.get("parentBranchIds") or []
    parent_ids = note.get("parentNoteIds") or []
    for bid, pid in zip(branch_ids, parent_ids):
        if pid == parent_id:
            return bid
    return None
```

`tests/test_client.py` 追加：

```python
def test_find_branch_matches_parent(self):
    t = self._client()
    note = {
        "parentBranchIds": ["b1", "b2"],
        "parentNoteIds": ["pA", "pB"],
    }
    with patch.object(t, "get_note", return_value=note):
        assert t.find_branch("n", "pB") == "b2"
        assert t.find_branch("n", "pZ") is None
```

运行：

```bash
uv run pytest tests/test_client.py -k find_branch -v
```

Expected: PASS

- [ ] **Step 2: 写 merge_topic 测试**

`tests/test_commands.py` 追加：

```python
from trilium import cmd_note_merge_topic


class TestMergeTopic:
    def test_merge_moves_notes_and_removes_empty_source(
        self, tmp_path, capsys, monkeypatch
    ):
        monkeypatch.setattr("trilium.CONFIG_PATH", _make_config(tmp_path))

        # notes carrying #topic="OldPg" under type=til
        source_notes = [
            {
                "noteId": "n1",
                "attributes": [
                    {"attributeId": "at1", "name": "topic", "value": "OldPg"},
                ],
            },
            {
                "noteId": "n2",
                "attributes": [
                    {"attributeId": "at2", "name": "topic", "value": "OldPg"},
                ],
            },
        ]
        # source topic node itself
        source_topic_hits = [
            {
                "noteId": "topicOld",
                "attributes": [{"name": "topicNote", "value": "til:OldPg"}],
            }
        ]

        def _search(expr, **_):
            if "#knowledge" in expr and 'topic="OldPg"' in expr:
                return source_notes
            if '#topicNote="til:OldPg"' in expr:
                return source_topic_hits
            return []

        with patch("trilium.Trilium") as TClass:
            t = TClass.return_value
            t.search.side_effect = _search
            t.ensure_topic_path.return_value = "topicNew"
            t.find_branch.side_effect = ["b1", "b2"]

            args = Namespace(
                type="til", from_topic="OldPg", to_topic="Postgres"
            )
            cmd_note_merge_topic(args)

        # relabel each note's #topic
        patch_calls = t.patch_attribute.call_args_list
        assert ("at1",) in [c.args for c in patch_calls] or any(
            c.args[0] == "at1" for c in patch_calls
        )
        assert any(c.args[0] == "at2" for c in patch_calls)
        # ensure new topic path prepared
        t.ensure_topic_path.assert_called_once_with("til", "Postgres")
        # branch delete + recreate
        # For each note: delete old branch then POST new branch
        assert t.delete_branch.call_count == 2
        assert t.create_branch.call_count == 2
        # remove empty source topic node
        t.delete_note.assert_called_once_with("topicOld")

        out = json.loads(capsys.readouterr().out)
        assert out == {
            "moved": 2,
            "fromNoteId": "topicOld",
            "toNoteId": "topicNew",
            "fromEmpty": True,
        }
```

- [ ] **Step 3: 添加两个 `Trilium` 辅助方法 + `cmd_note_merge_topic`**

在 `Trilium` 类内 `find_branch()` 下方追加：

```python
def delete_branch(self, branch_id: str):
    return self._req("DELETE", f"/branches/{branch_id}")

def create_branch(self, note_id: str, parent_id: str):
    return self._req(
        "POST",
        "/branches",
        json={"noteId": note_id, "parentNoteId": parent_id},
    ).json()
```

在 `cmd_note_topics` 下方追加：

```python
def cmd_note_merge_topic(args):
    cfg = load_config()
    t = Trilium(cfg)

    if args.type not in TYPE_DISPLAY_NAMES:
        die(f"未知的知识笔记类型: {args.type!r}")
    if args.from_topic == args.to_topic:
        die("源主题与目标主题相同")

    src_notes = t.search(
        f'#knowledge #type="{args.type}" #topic="{args.from_topic}"',
        limit="1000",
    )
    src_topic_hits = t.search(
        f'#topicNote="{args.type}:{args.from_topic}"',
        limit="5",
    )
    src_topic_id = src_topic_hits[0]["noteId"] if src_topic_hits else None

    dst_topic_id = t.ensure_topic_path(args.type, args.to_topic)

    moved = 0
    for n in src_notes:
        # relabel #topic
        topic_attr = next(
            (a for a in n.get("attributes", []) if a["name"] == "topic"),
            None,
        )
        if topic_attr:
            t.patch_attribute(topic_attr["attributeId"], value=args.to_topic)
        # move main branch: delete from src topic, create under dst topic
        if src_topic_id:
            bid = t.find_branch(n["noteId"], src_topic_id)
            if bid:
                t.delete_branch(bid)
        t.create_branch(n["noteId"], dst_topic_id)
        moved += 1

    from_empty = False
    if src_topic_id:
        remaining = t.search(
            f'#knowledge #type="{args.type}" #topic="{args.from_topic}"',
            limit="1",
        )
        if not remaining:
            t.delete_note(src_topic_id)
            from_empty = True

    print(json.dumps({
        "moved": moved,
        "fromNoteId": src_topic_id or "",
        "toNoteId": dst_topic_id,
        "fromEmpty": from_empty,
    }, ensure_ascii=False))
```

**测试适配**：上面测试假设第二次 search 用于验证 `remaining` 为空。修一下测试的 `_search`：

```python
        empty_after_move = {"called": False}
        def _search(expr, **_):
            if "#knowledge" in expr and 'topic="OldPg"' in expr:
                if empty_after_move["called"]:
                    return []
                empty_after_move["called"] = True
                return source_notes
            if '#topicNote="til:OldPg"' in expr:
                return source_topic_hits
            return []
```

（在 Step 2 编写时就用这个版本，如果 Step 2 已经用了简版，回到该测试改成上面这版。）

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/test_commands.py::TestMergeTopic tests/test_client.py -k find_branch -v
```

Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add scripts/trilium.py tests/test_commands.py tests/test_client.py
git commit -m "feat(trilium): add cmd_note_merge_topic (same-type topic merge)"
```

---

### Task 13: `cmd_check` 扩展

**Files:**
- Modify: `scripts/trilium.py`
- Create: `tests/test_check.py`

**Interfaces:**
- Consumes: `Trilium.app_info()`、`calendar_root()`、`knowledge_root()`、`get_note()`、`search()`
- Produces: 改写 `cmd_check`。输出：（这是唯一的人类可读命令）

```
✓ Trilium 可达: <server> (v<ver>)
✓ token 有效
✓ 日历根 = <id>（#calendarRoot 标签存在）
✓ 知识根 = <id>（#knowledgeRoot 标签存在）
i TIL 类型节点：<存在 / 首次写入时自动建>
i Ideas 类型节点：<...>
i References 类型节点：<...>
```

- [ ] **Step 1: 写测试**

创建 `tests/test_check.py`：

```python
"""Tests for cmd_check (v3)."""

import json
import os
import sys
from argparse import Namespace
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from trilium import cmd_check


def _make_config(tmp_path):
    cfg = {
        "server": "http://localhost:8080",
        "token": "t",
        "calendarRootId": "cal",
        "knowledgeRootId": "know",
    }
    p = tmp_path / "etc" / "config.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg), encoding="utf-8")
    return str(p)


class TestCheck:
    def test_check_all_good_reports_both_roots_and_types(
        self, tmp_path, capsys, monkeypatch
    ):
        monkeypatch.setattr("trilium.CONFIG_PATH", _make_config(tmp_path))
        with patch("trilium.Trilium") as TClass:
            t = TClass.return_value
            t.app_info.return_value = {"appVersion": "0.99.0"}
            t.calendar_root.return_value = "cal"
            t.knowledge_root.return_value = "know"

            def _get(nid):
                if nid == "cal":
                    return {"attributes": [{"name": "calendarRoot"}]}
                if nid == "know":
                    return {"attributes": [{"name": "knowledgeRoot"}]}
                return {"attributes": []}

            t.get_note.side_effect = _get
            # type node search results: TIL exists, Ideas missing, Reference exists
            def _search(expr, **_):
                if 'typeNote="til"' in expr:
                    return [{"noteId": "tilN"}]
                if 'typeNote="idea"' in expr:
                    return []
                if 'typeNote="ref"' in expr:
                    return [{"noteId": "refN"}]
                return []
            t.search.side_effect = _search

            cmd_check(Namespace())

        out = capsys.readouterr().out
        assert "Trilium 可达: http://localhost:8080 (v0.99.0)" in out
        assert "token 有效" in out
        assert "日历根 = cal" in out
        assert "#calendarRoot 标签存在" in out
        assert "知识根 = know" in out
        assert "#knowledgeRoot 标签存在" in out
        assert "TIL 类型节点" in out and "存在" in out.split("TIL")[1].splitlines()[0]
        assert "Ideas 类型节点" in out
        assert "首次写入时自动建" in out
        assert "References 类型节点" in out
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_check.py -v
```

Expected: FAIL —— 当前 `cmd_check` 只报日历根

- [ ] **Step 3: 改写 `cmd_check`**

替换整个 `cmd_check` 函数：

```python
def cmd_check(args):
    cfg = load_config()
    t = Trilium(cfg)
    info = t.app_info()
    print("✓ Trilium 可达: {} (v{})".format(cfg["server"], info.get("appVersion")))
    print("✓ token 有效")

    cal = t.calendar_root()
    cal_note = t.get_note(cal)
    cal_ok = any(a["name"] == "calendarRoot" for a in cal_note.get("attributes", []))
    tag = "#calendarRoot 标签存在" if cal_ok else "⚠ 缺少 #calendarRoot 标签"
    print(f"✓ 日历根 = {cal}（{tag}）")

    know = t.knowledge_root()
    know_note = t.get_note(know)
    know_ok = any(a["name"] == "knowledgeRoot" for a in know_note.get("attributes", []))
    tag = "#knowledgeRoot 标签存在" if know_ok else "⚠ 缺少 #knowledgeRoot 标签"
    print(f"✓ 知识根 = {know}（{tag}）")

    for type_key in ("til", "idea", "ref"):
        hits = t.search(f'#typeNote="{type_key}"', limit="5")
        display = TYPE_DISPLAY_NAMES[type_key]
        status = "存在" if hits else "首次写入时自动建"
        print(f"i {display} 类型节点：{status}")
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/test_check.py -v
```

Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add scripts/trilium.py tests/test_check.py
git commit -m "refactor(trilium): cmd_check reports knowledgeRoot + type nodes"
```

---

### Task 14: `build_parser` 重构（新命令表 + 删 recap/list-old/etc）

**Files:**
- Modify: `scripts/trilium.py`
- Modify: `tests/test_pure.py`（parser 部分）
- Modify: `tests/test_client.py`（删 `RECAP_ICON` 相关、`resolve_jsonl_path`、`TestCmdRecap*`、老 list/get/update/delete 用例）

**Interfaces:**
- Consumes: 所有 `cmd_*` 函数
- Produces: `argparse.ArgumentParser` 覆盖新命令表（`check`, `note {til,idea,ref,topics,merge-topic}`, `list`, `get`, `update`, `delete`）

- [ ] **Step 1: 删除旧代码块**

删除 `scripts/trilium.py` 里：
- 常量 `RECAP_ICON`
- 函数 `resolve_jsonl_path`
- 函数 `cmd_recap`
- `main()` 里的 `"recap": cmd_recap` 键
- `build_parser` 全部内容（下一步整体重写）

同时删除 `tests/test_client.py` 里：
- `from trilium import ... RECAP_ICON, cmd_recap, resolve_jsonl_path, ...` 语句
- `class TestCmdRecap*`（所有以 `TestCmdRecap` 开头的类）
- `class TestResolveJsonlPath`（如存在）

删除 `tests/test_pure.py` 里：
- `class TestBuildParser`（要重写，见 Step 3）

删除 `SKILL.md` 顶部导入 recap 逻辑的段落——**这一步不动 SKILL.md，T17 会重写**。

**先仅删代码块**，跑一次测试确认没引用漂移：

```bash
uv run pytest tests/ -x --ignore=tests/test_check.py --ignore=tests/test_commands.py 2>&1 | head -50
```

（预期：test_client.py 会失败，因为老用例引用了刚删的类。按需注释/删除失败用例。）

- [ ] **Step 2: 写 parser 目标测试**

`tests/test_pure.py` 追加（放到文件末尾）：

```python
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
```

- [ ] **Step 3: 运行 parser 测试确认失败**

```bash
uv run pytest tests/test_pure.py -k TestBuildParser -v
```

Expected: FAIL

- [ ] **Step 4: 重写 `build_parser` + `main` 分派**

替换 `scripts/trilium.py` 里 `build_parser()` 和 `main()`：

```python
def _add_note_write_args(p, *, needs_url=False):
    p.add_argument("--topic", required=True)
    p.add_argument("--title", required=True)
    p.add_argument("--source-session", dest="source_session", required=True)
    p.add_argument("--note-date", dest="note_date", required=True)
    p.add_argument("--icon", default=None)
    if needs_url:
        p.add_argument("--url", required=True)


def build_parser():
    p = argparse.ArgumentParser(
        prog="trilium.py", description="通用 Trilium 知识笔记 CLI"
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {_get_version()}")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("check", help="检查服务器、token、两个 root、类型节点")

    # note 命名空间
    p_note = sub.add_parser("note", help="知识笔记写入 / 主题治理")
    note_sub = p_note.add_subparsers(dest="note_cmd", required=True)

    p_til = note_sub.add_parser("til", help="写一条 TIL")
    _add_note_write_args(p_til)
    p_idea = note_sub.add_parser("idea", help="写一条想法")
    _add_note_write_args(p_idea)
    p_ref = note_sub.add_parser("ref", help="写一条参考资料")
    _add_note_write_args(p_ref, needs_url=True)

    note_sub.add_parser("topics", help="列所有主题")

    p_merge = note_sub.add_parser("merge-topic", help="同类型内归并主题")
    p_merge.add_argument("--type", required=True, choices=["til", "idea", "ref"])
    p_merge.add_argument("from_topic")
    p_merge.add_argument("to_topic")

    # 顶层通用 CRUD
    p_list = sub.add_parser("list", help="列出知识笔记")
    p_list.add_argument("--type", choices=["til", "idea", "ref"])
    p_list.add_argument("--topic")
    p_list.add_argument("--note-date", dest="note_date")
    p_list.add_argument("--source-session", dest="source_session")
    p_list.add_argument("--limit", type=int, default=50)

    p_get = sub.add_parser("get", help="查看一条笔记")
    p_get.add_argument("note_id")
    p_get.add_argument("--content", action="store_true")

    p_upd = sub.add_parser("update", help="修改标题/图标/正文")
    p_upd.add_argument("note_id")
    p_upd.add_argument("--title", default=None)
    p_upd.add_argument("--icon", default=None)

    p_del = sub.add_parser("delete", help="删除一条笔记")
    p_del.add_argument("note_id")

    return p


def main():
    args = build_parser().parse_args()
    if args.cmd == "note":
        {
            "til": cmd_note_til,
            "idea": cmd_note_idea,
            "ref": cmd_note_ref,
            "topics": cmd_note_topics,
            "merge-topic": cmd_note_merge_topic,
        }[args.note_cmd](args)
        return
    {
        "check": cmd_check,
        "list": cmd_list,
        "get": cmd_get,
        "update": cmd_update,
        "delete": cmd_delete,
    }[args.cmd](args)
```

- [ ] **Step 5: 运行全部测试**

```bash
uv run pytest tests/ -v
```

Expected: 全部 PASS。如果 `test_client.py` 还有引用 `RECAP_ICON` / `cmd_recap` / `resolve_jsonl_path` 的 import 或用例，删除它们；如果 `TestBuildParser` 的老用例中 `test_recap` 之类还在，也删除。

- [ ] **Step 6: 跑 ruff**

```bash
uv run ruff check scripts/ tests/
```

有报错就修（多为未用 import）。

- [ ] **Step 7: 提交**

```bash
git add scripts/trilium.py tests/
git commit -m "refactor(trilium): rewrite build_parser for note namespace; drop recap"
```

---

### Task 15: `references/note-triage-rules.md`

**Files:**
- Create: `references/note-triage-rules.md`

**Interfaces:**
- Consumes: 无（纯文档）
- Produces: subagent 启动时读取的规则文件

- [ ] **Step 1: 写入完整规则文件**

创建 `references/note-triage-rules.md`：

````markdown
# 知识笔记规则（subagent 消费）

**你是 note-taker subagent。**这份文件规定"什么值得记"、"怎么分类"、"怎么起名"、"怎么选图标"。严格遵守。

## 一、类型判定

只能是三种之一：

| type | 定义 | 例子 |
|---|---|---|
| **til** | 从 debug / 读文档 / 读源码得到的**结论性知识点**：一句话就能说清"X 的真相是 Y" | "Postgres `timestamp` 和 `timestamptz` 存储上是同一种 UTC 值，只有解释方式不同" |
| **idea** | 想做/想研究/想改的**方向**，不是已完成的知识 | "trilium-diary 应该支持 workspace 概念" |
| **ref** | 外部**已发表的资料**：blog / paper / issue / doc / video，必须带 URL | "SQLite WAL mode 的这篇 blog：https://..." |

**边界**：
- 用户 hint 明确带类型词（"TIL"/"想法"/"参考"）时直接用；歧义时按上表判定。
- 一段 debug 结论 + 附上 SO 链接：主体是 til（结论 primary），附上链接作为正文的引用即可，不额外拆一条 ref。
- 命令片段（"这句 `git rebase --onto` 好用"）算 til。

## 二、值得记的口径（中等）

批量整理（mode=batch）时，从 session JSONL 挑候选。**收录条件**（满足任一即可）：

1. **明显值得记的**：debug 得出的非平凡结论、读文档发现的反直觉行为
2. **卡了很久突破的**：session 中多个来回验证、试错的最终解
3. **重复来回验证的结论**：AI 和用户反复确认过的观点
4. **值得未来查的命令片段**：一句可复制的 shell / SQL / 代码片段

**排除**：
- 项目内部结构描述（写代码就能看到）
- 一次性的调试输出
- 用户在思考中的猜测（还没验证）
- 与主题无关的闲聊

**去重**：同 session 内同主题、同结论的候选只留一条，其它进 `skipped`。

## 三、主题（topic）命名

- **PascalCase**：`Postgres`、`TriliumDiary`、`RustAsync`
- **原生大小写**：`SQLite` 不是 `Sqlite`；`iOS` 不是 `Ios`
- **避免复数/缩写变体**：用 `Postgres` 不用 `PostgreSQL` 或 `PG`；用 `Docker` 不用 `Containers`
- **调用 CLI 前**：先 `./scripts/trilium.py note topics` 拿现有主题清单；若目标概念已有主题就用现有名（避免 `Postgres`/`PostgreSQL` 分裂）
- **主题应有"聚合价值"**：一个笔记不足以支持一个主题也可以先建；避免类似"未分类"的兜底

## 四、标题（title）

- 格式：`<Type>: <一句话>`（英文冒号 + 空格）
- 例：`TIL: Postgres timestamp vs timestamptz 存储行为一致`
- 例：`Idea: trilium-diary 支持多 workspace`
- 例：`Ref: SQLite WAL mode 深度解析`
- 中文英文混排允许；不要以方括号 / 特殊符号开头
- 一行；≤60 中文字符 / ≤120 半角字符

## 五、正文（body markdown）

- 顶部一行"结论"作为首句
- 之后按需分节：**背景 / 复现 / 结论 / 参考**
- **代码块**用 fenced code + 语言标签
- **命令片段**加语言标签 `bash`
- 引用来源（对 ref）：正文首行 `> 来源: <url>`
- 保持简短：TIL 30-150 字为宜；idea 一句话即可；ref 附上摘要 + 关键引用

## 六、图标（iconClass）选择

从下表选一个覆盖类型默认：

| 主题域 | 图标 | 场景 |
|---|---|---|
| 数据库 / SQL | `bx bx-data` | Postgres、MySQL、SQLite |
| 网络 / API | `bx bx-cloud` | HTTP、DNS、CDN |
| 命令行 / 脚本 | `bx bx-terminal` | 一句可复制的 shell / 命令片段 |
| Bug / 坑 | `bx bx-bug` | debug 结论、workaround |
| 性能 | `bx bx-tachometer` | 性能优化、benchmark |
| 安全 | `bx bx-shield` | 权限、注入、认证 |
| 代码 | `bx bx-code-alt` | 语言/框架细节 |
| 文档 / paper | `bx bx-book-open` | 长文摘要 |
| 视频 / 演讲 | `bx bx-play-circle` | 会议演讲、教程视频 |
| Git / VCS | `bx bx-git-branch` | Git 技巧、分支策略 |
| 工具 / 配置 | `bx bx-cog` | 编辑器/IDE/工具配置 |

**规则**：
- 判定核心主题域 → 用对应图标
- 匹配多个 → 用最具体的（Bug 优先于 代码；DB 优先于 代码）
- 都不匹配 → 不传 `--icon`，让 CLI 用类型默认
- **只能用上表里的值**；扩展词表要先改本文件

## 七、CLI 调用模板

**单条 til**：

```bash
cat <<'MD' | ./scripts/trilium.py note til \
    --topic "<Topic>" \
    --title "<title>" \
    --source-session "<sessionId>" \
    --note-date "<YYYY-MM-DD>" \
    --icon "<bx bx-xxx>"
<正文 markdown>
MD
```

**单条 idea / ref**：命令换 `idea` / `ref`；ref 额外加 `--url "<url>"`。

**读现有主题**（每次批量或不确定命名时都跑）：

```bash
./scripts/trilium.py note topics
```

## 八、失败处理

- 每条独立调 CLI，失败继续下一条
- CLI 非零退出 → 保留 stderr 内容，加入 `failed[]`
- 跳过（去重、口径不够）→ 加入 `skipped[]`，写清理由

## 九、返回格式

严格 JSON：

```json
{
  "notes": [
    {
      "type": "til | idea | ref",
      "title": "...",
      "topic": "...",
      "why": "一句话说明为什么值得记",
      "noteId": "...",
      "url": "http://.../#root/..."
    }
  ],
  "skipped": [
    { "reason": "...", "hint": "..." }
  ],
  "failed": [
    { "attemptedTitle": "...", "error": "..." }
  ],
  "note": "可选：整体说明"
}
```
````

- [ ] **Step 2: 提交**

```bash
git add references/note-triage-rules.md
git commit -m "docs(rules): add note-triage-rules for subagent"
```

---

### Task 16: `agents/note-taker.md`

**Files:**
- Create: `agents/note-taker.md`

**Interfaces:**
- Consumes: `references/note-triage-rules.md`（T15）
- Produces: subagent 完整指令；由主 Claude 通过 Agent 工具启动 subagent 时**内嵌**这份内容

- [ ] **Step 1: 建目录 + 写入**

```bash
mkdir -p agents
```

创建 `agents/note-taker.md`：

````markdown
# note-taker subagent

**角色**：你是 trilium-diary 的记笔记 subagent。主 Claude 遇到用户"记一下 / 整理一下"类触发词后，把上下文打包成 `<input>` 传给你；你从 Claude Code session JSONL 中提炼知识笔记，逐条调 CLI 落盘，最后返回结构化 JSON。

**你的输入**（`<input>` XML）：

```
<sessionId>{{$CLAUDE_CODE_SESSION_ID}}</sessionId>
<projectDir>{{$PWD}}</projectDir>
<mode>single | batch</mode>
<hint>{{用户原话，如"记个 TIL，Postgres timestamp..."}}</hint>
<noteDate>{{YYYY-MM-DD，可选，缺省用今天}}</noteDate>
```

## 执行步骤

1. **读规则文件**：`Read references/note-triage-rules.md`（对应规则内容会同时嵌在你的 prompt 里；如已内嵌可跳过 Read）。
2. **确定 noteDate**：`<noteDate>` 非空则用它；否则用今天（当前 shell 日期 `date +%Y-%m-%d`）。
3. **读 session JSONL**：路径 `~/.claude/projects/<slug>/<sessionId>.jsonl`，`<slug>` 是把 `<projectDir>` 中所有 `/` 换成 `-`（如 `/home/foo/proj` → `-home-foo-proj`）。
   - **mode=single**：读文件尾部 ~50 条消息（`tail -n 200` 后取尾部）——`<hint>` 指向的话题应该在最近上下文里
   - **mode=batch**：读完整文件
4. **调用 `./scripts/trilium.py note topics`** 拿现有主题清单，用于主题命名一致性检查。
5. **判定并生成笔记**：
   - **single**：以 `<hint>` 为主，从上下文补细节，产出**恰好 1 条**
   - **batch**：按规则 § 二"值得记的口径（中等）"筛候选；每个候选独立生成
6. **每条笔记**：
   - 判 `type`（规则 § 一）
   - 定 `topic`（规则 § 三；优先复用现有主题）
   - 写 `title`（规则 § 四）
   - 写 `body`（规则 § 五）
   - 选 `icon`（规则 § 六）
   - 组装 `why`：一句话说明为什么值得记（≤30 字）
7. **逐条调 CLI**（规则 § 七的模板）；解析 stdout JSON 拿 `noteId` 和 `url`。CLI 非零退出 → 记入 `failed`，继续下一条。
8. **返回**：严格按规则 § 九的 JSON schema。

## 注意事项

- **不要**直接调 ETAPI；只通过 CLI。
- **不要**在正文里包含 tool_use 参数、超长 log。
- **不要**改动 CLI 之外的文件。
- Subagent 完成后，主 Claude 会把你返回的 JSON 转成简报显示。**你的最终输出必须是可 JSON.parse 的字符串**，不要额外解释。
- 如果 `<hint>` 完全无法在上下文里定位相关内容，返回 `{"notes": [], "note": "根据 hint 未能在 session 上下文里定位相关内容"}` 而非硬编。
````

- [ ] **Step 2: 提交**

```bash
git add agents/note-taker.md
git commit -m "docs(agents): add note-taker subagent instructions"
```

---

### Task 17: 重写 `SKILL.md`

**Files:**
- Modify: `SKILL.md`

**Interfaces:**
- Consumes: `agents/note-taker.md`（T16）、`references/note-triage-rules.md`（T15）、CLI 命令表（T14）
- Produces: 完整重写的 SKILL.md，作为主 Claude 的入口指令

- [ ] **Step 1: 覆盖写入**

替换整份 `SKILL.md`：

````markdown
---
name: trilium-diary
description: "把开发日记写入 Trilium 日历。Use when: 踩坑解决 / 工作里程碑 / 技术决策 / 学到新东西；用户说'记一下''写到 trilium''写进日记'时直接执行。"
---

# Trilium 知识笔记助手

把 Claude Code 会话里的 **TIL / 想法 / 参考资料**写入 Trilium：分类树主位 + 日历副入口。

写入路径由 subagent 执行（不污染主对话上下文）；读改删主题查询由主 Claude 直接调 CLI。

## 初始化

**每次使用前先检查配置**。执行：

```bash
cd "$(dirname "$SKILL_MD")"

if [ ! -f ./etc/config.json ]; then
    echo "缺少配置文件，正在从模板创建..."
    cp ./etc/config.example.json ./etc/config.json
    chmod 600 ./etc/config.json
    echo "请编辑 ./etc/config.json 填入 Trilium 信息："
    echo "  - server: Trilium 服务地址（如 http://localhost:8080）"
    echo "  - token: ETAPI token（Trilium → Options → ETAPI 生成）"
    echo "  - calendarRootId: 日历根 noteId（留空自动探测 #calendarRoot）"
    echo "  - knowledgeRootId: 知识树根 noteId（留空自动探测 #knowledgeRoot）"
    exit 1
fi

./scripts/trilium.py check
```

`check` 失败要引导用户修 `etc/config.json` 直到通过。config 权限须 600，**绝不要回显 token**。

**Trilium 侧准备**：知识树根需要是一条 `book` 或 `text` 笔记，带 `#knowledgeRoot` 标签（跟 `#calendarRoot` 对称）。如果 Trilium 里还没建，引导用户建一条名为 `Knowledge` 的顶层笔记并打上标签。

## 触发场景分派

| 用户说 | 你要做的 |
|---|---|
| `记一下` / `记个 TIL` / `记个想法` / `记个参考` | **派 subagent（single）** |
| `整理一下` / `批量记这次会话` | **派 subagent（batch）** |
| `看看记了什么` / `列一下今天 / 关于 X 的` | 直接跑 `./scripts/trilium.py list` |
| `打开 abc` / `显示 abc` | `./scripts/trilium.py get abc [--content]` |
| `改标题为 X` / `改图标为 Y` / `改内容` | `./scripts/trilium.py update <id> [--title X] [--icon Y]`；改正文从 stdin 传 |
| `删了 abc` | `./scripts/trilium.py delete abc` |
| `合并主题 X 和 Y` | `./scripts/trilium.py note merge-topic --type <T> X Y` |
| `都有哪些主题` | `./scripts/trilium.py note topics` |

**架构约束**：写入场景必须派 subagent（写入需要读 JSONL + 大量 AI 判断，会污染主对话）；其他 CRUD 主 Claude 直调即可。

## 写入路径：派 subagent

用 Agent 工具（`subagent_type: general-purpose`），prompt 结构：

```xml
<input>
  <sessionId>{{$CLAUDE_CODE_SESSION_ID}}</sessionId>
  <projectDir>{{$PWD}}</projectDir>
  <mode>single | batch</mode>
  <hint>{{用户原话}}</hint>
  <noteDate>{{YYYY-MM-DD，可选}}</noteDate>
</input>

<instructions>
{{内嵌 agents/note-taker.md 全文}}
</instructions>

<rules>
{{内嵌 references/note-triage-rules.md 全文}}
</rules>
```

Subagent 会返回 JSON，格式见 `references/note-triage-rules.md` § 九。

## 简报格式

Subagent 返回后展示：

```
✓ 已记 N 条 · 跳过 M 条 · 失败 K 条

· TIL · <topic> · <title>
  why: <一句话>
  → <url>

· Idea · <topic> · <title>
  why: <一句话>
  → <url>

（如有失败）
✗ <attemptedTitle>
  <error>
```

- N=0 单条：`⚠ 没记到内容：<note 字段>`
- N=0 批量：`i 本次会话未发现符合中等口径的候选`
- 失败列表为空则整段省略

## 读/改/删/查询：主 Claude 直调 CLI

所有命令 stdout 是 JSON（除 `check`）；解析后转述给用户，不要原样输出 JSON。

**示例**：用户说"列一下今天关于 Postgres 的"：

```bash
./scripts/trilium.py list --topic Postgres --note-date "$(date +%Y-%m-%d)"
```

拿到 `{"items": [...]}` 后，对每条转成 `<type> · <topic> · <title> → <url>` 展示。

## 命令表速查

```
check                                        # 服务器 + token + 两个 root + 类型节点
note til   --topic T --title t --source-session s --note-date d [--icon i] < body.md
note idea  --topic T --title t --source-session s --note-date d [--icon i] < body.md
note ref   --topic T --title t --source-session s --note-date d [--icon i] --url u < body.md
note topics
note merge-topic --type T from-topic to-topic
list       [--type T] [--topic X] [--note-date d] [--source-session s] [--limit N]
get        <id> [--content]
update     <id> [--title t] [--icon i]       # 从 stdin 读新正文（可选）
delete     <id>
```

**注意**：`update` 不支持 `--topic`；改主题请 `delete + 重记` 或 `note merge-topic`。

## 排错

- **check 报 `#knowledgeRoot` 找不到**：引导用户在 Trilium 建一条根笔记打 `#knowledgeRoot` 标签，或在 `etc/config.json` 设 `knowledgeRootId`。
- **subagent 返回 `failed`**：报给用户看错误消息；由用户决定是否重试。
- **clone 到日历失败**：主位已建，副入口缺失；不阻塞。用户可以事后手动在 Trilium 里 clone。
- **图标不显示**：iconClass 值可能拼错；用 `update <id> --icon "bx bx-xxx"` 修正（`references/note-triage-rules.md` § 六 有词表）。
- 详细 ETAPI 参考：`references/etapi.md`。
````

- [ ] **Step 2: 提交**

```bash
git add SKILL.md
git commit -m "docs(skill): rewrite for v3 knowledge notes (subagent write + direct CRUD)"
```

---

### Task 18: 重写 `README.md`

**Files:**
- Modify: `README.md`

**Interfaces:**
- Produces: 面向 GitHub 访问者的 README

- [ ] **Step 1: 覆盖写入**

替换 `README.md`：

````markdown
# trilium-diary

Claude Code skill：把开发会话里的 **TIL / 想法 / 参考资料**写入
[Trilium Notes](https://github.com/zadam/trilium)。

- **分类树主位**：`Knowledge/<Type>/<Topic>/` 三层结构
- **日历副入口**：clone 到 `Journal/<yyyy>/<MM>/<dd>/`，两个入口指向同一份内容
- **AI 全自动**：subagent 从 session 上下文提炼类型、主题、标题、正文和图标
- **单条 / 批量**：`记一下` 单条；`整理一下这次会话` 批量筛候选

## 安装

```bash
# 项目级
git clone https://github.com/<user>/trilium-diary.git .claude/skills/trilium-diary

# 全局
git clone https://github.com/<user>/trilium-diary.git ~/.claude/skills/trilium-diary
```

## 配置

```bash
cp etc/config.example.json etc/config.json
chmod 600 etc/config.json
```

编辑 `etc/config.json`：

```json
{
  "server": "http://localhost:8080",
  "token": "<ETAPI token>",
  "calendarRootId": "",
  "knowledgeRootId": ""
}
```

- `token`：Trilium → Options → ETAPI → Create new ETAPI token
- `calendarRootId` / `knowledgeRootId`：留空则脚本按 `#calendarRoot` / `#knowledgeRoot` 标签自动探测；探测到多个会报错要求显式指定

**Trilium 侧**：确保有一条笔记打 `#knowledgeRoot`（跟 `#calendarRoot` 对称）。建议在 root 下建一条名为 `Knowledge` 的 `book` 笔记。

## 使用（在 Claude Code 里）

- `记个 TIL，Postgres timestamp 和 timestamptz 存储上一样` → subagent 写一条 TIL
- `整理一下这次会话` → subagent 从整段 session 挑候选逐条落盘
- `看看今天记了什么` → 主 Claude 直接调 CLI
- `改标题为 X` / `合并主题 PostgreSQL 到 Postgres` / `删了 abc` → 主 Claude 直接调 CLI

写入笔记的类型、主题、标题、正文、图标由 subagent 自动判定，落到 Trilium 后可用 `update` / `delete` / `note merge-topic` 修正。

## 命令

```bash
./scripts/trilium.py check

# 写入（一般由 subagent 调用）
./scripts/trilium.py note til   --topic Postgres --title "..." --source-session <sid> --note-date 2026-07-03 < body.md
./scripts/trilium.py note idea  --topic Trilium  --title "..." --source-session <sid> --note-date 2026-07-03 < body.md
./scripts/trilium.py note ref   --topic SQLite   --title "..." --source-session <sid> --note-date 2026-07-03 --url https://... < body.md

# 治理
./scripts/trilium.py note topics
./scripts/trilium.py note merge-topic --type til PostgreSQL Postgres

# 查询 / 修改
./scripts/trilium.py list --type til --topic Postgres
./scripts/trilium.py get <noteId> --content
./scripts/trilium.py update <noteId> --title "新标题" --icon "bx bx-data"
./scripts/trilium.py delete <noteId>
```

所有命令（除 `check`）输出 JSON。

## 依赖

Python 3.12+，通过 [uv](https://docs.astral.sh/uv/) 自动管理（`markdown`、`requests`）。

## 相关文档

- `SKILL.md`：Claude Code 触发协议
- `agents/note-taker.md`：subagent 指令
- `references/note-triage-rules.md`：类型 / 主题 / 标题 / 图标规则
- `references/etapi.md`：Trilium ETAPI 参考
````

- [ ] **Step 2: 提交**

```bash
git add README.md
git commit -m "docs(readme): rewrite for v3 knowledge notes"
```

---

### Task 19: 手动黑盒验证 + 收尾

**Files:**
- 无代码改动；仅验证

**Interfaces:**
- 无

**目的**：真实 Trilium 环境跑一遍，确认 subagent + CLI + Trilium 联动正确；把结果贴回 spec 附录。

- [ ] **Step 1: 全量单元测试 + ruff**

```bash
uv run pytest tests/ -v
uv run ruff check scripts/ tests/
```

Expected: 全 PASS，ruff 无 error。

- [ ] **Step 2: `check` 冒烟**

```bash
./scripts/trilium.py check
```

Expected: 5 行 ✓ + 3 行 i；如果 `#knowledgeRoot` 找不到，先在 Trilium 建一条 `Knowledge` 笔记打 `#knowledgeRoot` 标签，再跑一次。

- [ ] **Step 3: 手动 til 冒烟**

```bash
echo "Postgres timestamp 和 timestamptz 存储上都是 UTC，只是解释方式不同。" | \
  ./scripts/trilium.py note til \
    --topic Postgres --title "TIL: timestamp vs timestamptz" \
    --source-session smoke-1 --note-date "$(date +%Y-%m-%d)" \
    --icon "bx bx-data"
```

Expected: stdout 一行 `{"noteId": "...", "url": "...", "cloned": true}`；在 Trilium 里能看到笔记同时挂在 `Knowledge/TIL/Postgres/` 和当天日笔记下。

- [ ] **Step 4: 手动 idea / ref 冒烟**

```bash
echo "把 trilium-diary 扩展成支持 workspace" | \
  ./scripts/trilium.py note idea \
    --topic TriliumDiary --title "Idea: 支持 workspace" \
    --source-session smoke-1 --note-date "$(date +%Y-%m-%d)"

echo "SQLite WAL 模式详解" | \
  ./scripts/trilium.py note ref \
    --topic SQLite --title "Ref: WAL 模式" \
    --url "https://www.sqlite.org/wal.html" \
    --source-session smoke-1 --note-date "$(date +%Y-%m-%d)"
```

Expected: 两条各自 JSON；Trilium 里 idea/ref 类型节点自动建好；三个笔记都出现在同一天的日历下。

- [ ] **Step 5: `list` / `get` / `note topics` 冒烟**

```bash
./scripts/trilium.py list --note-date "$(date +%Y-%m-%d)"
./scripts/trilium.py get <上面某 noteId>
./scripts/trilium.py note topics
```

Expected: JSON 输出正确。

- [ ] **Step 6: `update` / `merge-topic` 冒烟**

```bash
# 用一个已存在的 til noteId
./scripts/trilium.py update <id> --title "TIL: PG timestamp（改）" --icon "bx bx-bug"
./scripts/trilium.py note merge-topic --type til Postgres PostgresTest
./scripts/trilium.py note merge-topic --type til PostgresTest Postgres
```

Expected: 两次 merge 都 `moved` > 0；第二次把主题再合回来，验证方向可逆。

- [ ] **Step 7: `delete` 清理**

```bash
./scripts/trilium.py delete <每个 smoke-1 的 noteId>
```

- [ ] **Step 8: subagent 端到端（真实 Claude Code 会话内）**

在真实 Claude Code session 里，让主 Claude 触发：

1. 单条 til：说"记个 TIL，Postgres timestamp 和 timestamptz 一样"
2. 单条 idea：说"记个想法，trilium-diary 支持 workspace"
3. 单条 ref：说"记个参考，SQLite WAL 这篇 blog https://www.sqlite.org/wal.html"
4. 批量：一段 debug 后说"整理一下这次会话"

每次记录 subagent 返回的简报（type / topic / title / why / url），贴到
`docs/superpowers/specs/2026-07-03-knowledge-notes-design.md` 末尾的
"手动黑盒测试" 附录（若无则新建 `## 附录：v3.0 手动黑盒验证结果` 段）。

- [ ] **Step 9: 收尾提交 + 合并**

```bash
git add docs/superpowers/specs/
git commit -m "docs(spec): v3 blackbox verification results"
```

推分支 + 开 PR（等用户确认）：

```bash
git push -u origin refactor/knowledge-notes
```

**不要**自动 merge。用户复核后再合并。

---

## Self-Review 结果

**Spec 覆盖**：

| Spec 章节 | 对应 task |
|---|---|
| §1 背景 | 无（仅动机） |
| §2 触发 | T17 SKILL.md |
| §3 架构 | T6~T14 CLI；T15~T17 subagent 侧 |
| §4 数据模型（两棵根树、标签约定、clone） | T2~T6 |
| §5 组件与文件布局 | 全 task |
| §6 命令表 | T6~T14 |
| §7 数据流（单条 / 批量 / CLI 内部） | T6/T14/T16/T17 |
| §8 图标策略 | T3 类型默认 / T15 词表 / T9 update patch |
| §9 错误处理 | T5 clone 非致命 / T6 empty stdin die / T13 check |
| §10 测试策略 | T2~T14 每 task 带测试 / T19 黑盒 |
| §11 迁移 | T1 删除 jsonl_render；无 migrate 命令（YAGNI） |
| §12 分支与提交 | T1 起分支 / 每 task commit |
| §13 决策记录 | 隐式贯穿；无独立 task |
| §14~§18 附录 | T15/T16/T17 承载 |

**类型一致性**：
- `type_key` 三处（`ensure_type_path` / `ensure_topic_path` / `_cmd_note_write`）都用同一集合 `{"til","idea","ref"}`。
- `add_label(noteId, "type", type_key)` 与 search 表达式 `#type="til"` 一致（小写）。
- CLI 参数 `--source-session` / `--note-date` 全 plan 一致。

**关键留意点**：
- `_cmd_note_write` 依赖 `TYPE_DEFAULT_ICONS`，该常量在 T3 引入；T6 才用，顺序正确。
- `find_branch` 在 T12 引入，`clone_note` 已在 T5 独立可用（不依赖 find_branch）。
- `TestBuildParser` 老用例会在 T14 一次性替换，避免中间 task 因 parser 报错。
- ruff 校验放在 T14 收官，因为前面 task 有渐进式函数残留（`RECAP_ICON` 等）。

---

**Plan 完成**。总计 19 个 task；每个 task 都以「独立 commit + 测试通过」为完成标志。







