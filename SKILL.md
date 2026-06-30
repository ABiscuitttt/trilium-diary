---
name: trilium-diary
description: "把开发对话忠实地写入 Trilium 日历。Use when: 用户说 'recap' / '记一下' / '写到 trilium' / '写进日记' 时直接执行。"
---

# Trilium 工作日记（Recap）

将当前 Claude Code 会话的对话 JSONL 渲染成 markdown，写入 Trilium 内置**日历（Journal）**面板，自动挂到当天日笔记下，标题以 `Recap` 开头。

## 初始化

**每次使用前先检查配置**。执行：

```bash
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
```

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

```bash
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
```

## 实现细节

日历结构 — 配置了 `calendarRootId` 时使用 ETAPI `/calendar/days/{date}` 端点
（自动创建/查找日 note），否则退回手动幂等查找或创建：

```
Journal (#calendarRoot)
 └─ 2026            #yearNote=2026
     └─ 06 - June   #monthNote=2026-06
         └─ 30 - 周二  #dateNote=2026-06-30
             └─ Recap：<suffix>  #iconClass="bx bx-conversation"
                                  #diary #sessionId=<uuid> #diaryDate=2026-06-30
```

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
