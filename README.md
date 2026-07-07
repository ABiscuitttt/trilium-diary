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

- `记个 TIL，Postgres timestamp 和 timestamptz 的时区语义不同` → subagent 写一条 TIL
- `整理一下这次会话` → subagent 从整段 session 挑候选逐条落盘
- `看看今天记了什么` → 主 Claude 直接调 CLI
- `改标题为 X` / `合并主题 PostgreSQL 到 Postgres` / `删了 abc` → 主 Claude 直接调 CLI

写入笔记的类型、主题、标题、正文、图标由 subagent 自动判定，落到 Trilium 后可用 `update` / `delete` / `note merge-topic` 修正。

写入质量由 `references/note-triage-rules.md` 约束：可搜索标题、首句结论、压缩背景、证据 / 来源、写入前自检；宁可跳过也不写会话摘要。

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
- `references/note-triage-rules.md`：笔记质量规则（类型 / 主题 / 标题 / 正文 / 图标 / 自检）
- `references/etapi.md`：Trilium ETAPI 参考
