# trilium-diary

把开发过程中的关键节点（踩坑、工作里程碑、技术决策、学习笔记）以 markdown 形式记入
[Trilium Notes](https://github.com/zadam/trilium) 的日历 / Journal 面板。

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

编辑 `etc/config.json`，填入你的 Trilium 服务器地址、ETAPI token 和日历根笔记 ID。

## 使用

```bash
# 检查连通性（含日历根标签验证）
./scripts/trilium.py check

# 写入一条日记（heredoc stdin，推荐）
./scripts/trilium.py add --type work --title "联调通过" <<'EOF'
## 背景
前后端联调完成

## 结果
所有接口跑通
EOF

# 写入一条日记（简短内容可用 echo + pipe）
echo '## 背景\n...\n## 结果\n...' | \
  ./scripts/trilium.py add --type work --title "联调通过"

# 写入一条日记（交互式编辑器）
./scripts/trilium.py add --type learn --title "学会了 retry 机制"

# 列出日记（文本格式）
./scripts/trilium.py list --date 2026-05-29

# 列出日记（JSON 格式）
./scripts/trilium.py list --format json

# 修改内容（heredoc stdin）
./scripts/trilium.py update <noteId> <<'EOF'
## 新内容
更新后的 markdown...
EOF
```

`--type` 选项：`trap`（踩坑）、`work`（工作）、`decision`（决策）、`learn`（学习）。

## 功能特性

- **网络重试**：自动对 502/503/504 错误重试 3 次，指数退避
- **ETAPI 日历端点**：配置 `calendarRootId` 后直接使用 `/calendar/days/{date}` API
- **交互式编辑**：`add` 不传内容时自动打开 `$EDITOR`
- **JSON 输出**：`list --format json` 便于程序化处理
- **增强校验**：`check` 验证日历根笔记的 `#calendarRoot` 标签

## 依赖

Python 3.12+，通过 [uv](https://docs.astral.sh/uv/) 自动管理依赖（`markdown`、`requests`）。
