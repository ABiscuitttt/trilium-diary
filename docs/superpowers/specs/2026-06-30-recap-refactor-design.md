# 2026-06-30 — Recap 重构设计

## Context

当前 `trilium-diary` 项目把 AI 在对话中起草的"压缩摘要"写入 Trilium 日历，
分四类（trap/work/decision/learn）。摘要由 AI 二次加工，存在信息损失，且
四类标签维护成本不必要。

重构目标：把记录方式改成"忠实记录" —— AI 调用脚本时，脚本直接读取当时的
Claude Code session JSONL，渲染成可读 markdown 写入 Trilium。标题统一以
`Recap` 开头，后接 AI 自行总结的简短描述。

完成后：

- AI 触发更轻：无需起草摘要，调用即可
- 记录信息完整：含 user/assistant 文本、思考过程、工具调用与结果
- 同 session 多次 recap 幂等覆盖，不产生重复笔记

## 决策摘要

| 维度 | 决定 |
|---|---|
| JSON 来源 | 脚本读环境变量 `$CLAUDE_CODE_SESSION_ID` 与 `$PWD`，拼出 jsonl 路径 |
| 记录范围 | 整个当前 session |
| 内容形式 | 解析 jsonl → 渲染可读 markdown → 走现有 `render_markdown()` 入库 |
| 标题 | `Recap：<AI 通过 --title-suffix 传入的描述>`；不传则单纯 `Recap` |
| 幂等 key | 当天日笔记下的 `#sessionId=<uuid>`；同 session 同天只 1 条；跨天调同 session 会在新一天另建新条，旧条不动 |
| 旧命令 | 完全替换：删除 `add --type` / trap/work/decision/learn 触发说明 |
| 图标 | 固定 `bx bx-conversation` |
| thinking 渲染 | `<details><summary>thinking</summary>…</details>` 折叠 |
| tool_result 大小 | 全保留，不截断 |
| 表情符号 | 不使用 |

## 命令

```
./scripts/trilium.py recap [--title-suffix "..."] [--session <id>] [--project-dir <path>]
```

- 默认无参：从环境变量解析 sessionId 与项目目录
- `--session`、`--project-dir` 用于覆盖（调试或跨项目场景）
- `--title-suffix` 由 AI 调用时传入简短描述

保留命令：`check`、`list`、`get`、`update`、`delete`（去掉 `--type` / `--prefix`，去掉 `add`）。

## 数据流

```
AI 调用 ./trilium.py recap --title-suffix "重构设计"
  ├─ 读 $CLAUDE_CODE_SESSION_ID 与 $PWD
  ├─ 拼路径 ~/.claude/projects/${PWD//\//-}/${CLAUDE_CODE_SESSION_ID}.jsonl
  ├─ jsonl_render.render_jsonl(path) → markdown
  ├─ 走 render_markdown() → HTML
  ├─ 在 Trilium 当天日笔记下搜 #sessionId=<id>
  │   ├─ 命中 → PUT /notes/{id}/content；标题变了再 PATCH 改标题
  │   └─ 未命中 → POST /create-note + 打标签
  └─ 输出 noteId 与打开链接
```

幂等搜索表达式：`note.parents.noteId="<day-id>" #sessionId="<id>"`

## JSONL 渲染规则

| 来源 | 渲染 |
|---|---|
| `user` 文本（非 tool_result） | `## User\n\n` + 文本 |
| `user` 含 tool_result | 收集为对应 tool_use 的结果块 |
| `assistant` 文本 block | `## Assistant\n\n` + 文本 |
| `assistant` thinking block | `<details><summary>thinking</summary>\n\n` + 内容 + `\n\n</details>` |
| `assistant` tool_use block | `### Tool: <ToolName>\n\n` + ` ```参数 json``` ` |
| `tool_result`（匹配 tool_use_id） | `<details><summary>result</summary>\n\n` + 内容 + `\n\n</details>` |
| `system` / hook / `mode` / `last-prompt` / `permission-mode` / `queue-operation` / `file-history-snapshot` / `attachment`(hook_*) | 忽略 |
| 文本中嵌入的 `<system-reminder>` | 忽略 |

特殊处理：

- 一条 assistant 消息可能含多种 block，按出现顺序拼接
- tool_use / tool_result 通过 `tool_use_id` 配对；孤儿 tool_result 单独列在末尾
- tool_result 不截断；外层 `<details>` 折叠避免视觉爆炸
- 解析坏行跳过，最后汇报跳过条数

## Trilium 标签

| 标签 | 值 | 用途 |
|---|---|---|
| `#diary` | （空） | 总过滤 |
| `#sessionId` | `<uuid>` | 幂等查找 key |
| `#diaryDate` | `YYYY-MM-DD` | 日期过滤 |
| `#iconClass` | `bx bx-conversation` | 树/日历图标 |

不再写 `#diaryType`。

## 错误处理

- 环境变量缺失：明确报错，提示用 `--session` / `--project-dir`
- jsonl 文件不存在：报错并打印路径
- jsonl 解析坏行：跳过，汇报跳过数
- 全空（只剩忽略行）：拒绝写入，避免覆盖已有内容
- Trilium 调用失败：沿用既有 `_req()` 的 die/重试逻辑

## 文件结构

```
scripts/
├── trilium.py            ← 改命令；接入 recap；删 add
└── jsonl_render.py       ← 新；纯函数 render_jsonl(path) -> markdown
tests/
├── test_pure.py
├── test_client.py        ← 删旧 add 用例，加 recap 用例
├── test_jsonl_render.py  ← 新
└── fixtures/
    └── sample_session.jsonl  ← 新；最小可用 session 样例
```

拆 `jsonl_render.py` 的理由：纯函数无 IO，便于 TDD。`trilium.py` 保留
ETAPI 客户端、CLI 入口与网络逻辑；`recap` 命令本身只做"读文件 → 调 render → 调 Trilium"的胶水。

## 测试覆盖

`tests/test_jsonl_render.py`（新）：

- 单一 user 文本
- 单一 assistant 文本
- assistant 含 thinking block → 折叠语法存在
- assistant 含 tool_use + 配对 tool_result
- 孤儿 tool_result（无匹配 tool_use_id）→ 末尾单列
- 忽略行（system / hook / mode 等）
- 多条 block 顺序拼接
- 全空输入 → 抛特定异常或返回空标记

`tests/test_client.py`（改）：

- 删 `cmd_add` 相关 mock 用例
- 加 `cmd_recap` 两条：
  - 当天该 sessionId 不存在 → 创建 + 四个标签
  - 当天该 sessionId 已存在 → PUT 内容、必要时 PATCH 标题，不重复创建

## SKILL.md 改动

- 触发条件简化为"用户说 'recap'/'记一下'/'写到 trilium'/'写进日记' 时调用"
- 删除四类（trap/work/decision/learn）说明
- 命令小节：删 `add --type`，加 `recap [--title-suffix ...]`
- 日历结构图：把"标题"换成"Recap：…"
- 删类型→图标映射表
- 注意事项：补一条"AI 调用 recap 时无需传 sessionId，脚本读环境变量"

## README.md 改动

同步更新命令清单与功能特性段落。

## 兼容/迁移

- 旧的 trap/work/decision/learn 笔记保留不动（历史数据）
- 新版只产 recap 笔记
- 不写迁移脚本

## 版本号

`pyproject.toml` 升至 `2.0.0`（破坏性变更：移除 `add`）。

## 关键文件

- `scripts/trilium.py:340`（`cmd_add` 删除并替换为 `cmd_recap`）
- `scripts/trilium.py:501`（`build_parser` 删 `add` 增 `recap`）
- `scripts/trilium.py:545`（`main` 命令分发表）
- `scripts/jsonl_render.py`（新文件）
- `tests/test_jsonl_render.py`（新文件）
- `tests/test_client.py:全文`（调整 add → recap）
- `SKILL.md`（重写触发条件、命令、注意事项）
- `README.md`（同步）
- `pyproject.toml:3`（版本号）

## 验证

```bash
# 单测
uv run pytest

# 真实链路：当前 session 自身就是测试数据
./scripts/trilium.py recap --title-suffix "测试 recap"

# Trilium 里检查：
# - 今日日笔记下出现 "Recap：测试 recap" 子笔记
# - 笔记图标 bx-conversation
# - 标签含 #diary #sessionId=... #diaryDate=...
# - 内容含 user/assistant 段，thinking 折叠

# 幂等覆盖
./scripts/trilium.py recap --title-suffix "测试 recap v2"
# Trilium 同一条笔记标题变为 "Recap：测试 recap v2"，内容刷新
```
