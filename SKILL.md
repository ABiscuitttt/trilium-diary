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
