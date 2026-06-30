# trilium-diary

把当前 Claude Code 会话的对话 JSONL 忠实渲染成 markdown，写入
[Trilium Notes](https://github.com/zadam/trilium) 的日历 / Journal 面板，
标题以 `Recap` 开头。

## 安装

```bash
# 项目级（仅当前项目生效）
git clone https://github.com/<user>/trilium-diary.git .claude/skills/trilium-diary

# 全局（所有项目生效）
git clone https://github.com/<user>/trilium-diary.git ~/.claude/skills/trilium-diary
```

## 配置

```bash
cp etc/config.example.json etc/config.json
```

编辑 `etc/config.json`，填入 Trilium 服务器地址、ETAPI token 和日历根笔记 ID。

## 使用

```bash
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
```

## 功能特性

- **忠实记录**：直接读 session JSONL 渲染成 markdown，含 user/assistant 文本、thinking 折叠、tool 调用与结果
- **幂等覆盖**：同 session 同天的 recap 覆盖已有笔记，不重复创建
- **自动定位**：默认读 `$CLAUDE_CODE_SESSION_ID` 与 `$PWD`，无需手动传 sessionId
- **网络重试**：自动对 502/503/504 错误重试 3 次，指数退避
- **ETAPI 日历端点**：配置 `calendarRootId` 后直接使用 `/calendar/days/{date}` API
- **JSON 输出**：`list --format json` 便于程序化处理

## 依赖

Python 3.12+，通过 [uv](https://docs.astral.sh/uv/) 自动管理依赖（`markdown`、`requests`）。
