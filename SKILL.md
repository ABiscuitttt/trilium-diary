---
name: trilium-diary
description: "把开发日记写入 Trilium 日历。Use when: 踩坑解决 / 工作里程碑 / 技术决策 / 学到新东西；用户说'记一下''写到 trilium''写进日记'时直接执行。"
---

# Trilium 工作日记

将 markdown 日记写入 Trilium 内置**日历（Journal）**面板，自动挂到对应日期下。

## 初始化

**每次使用前先检查配置**。执行：

```bash
cd "$(dirname "$SKILL_MD")"

# 检查 config.json 是否存在
if [ ! -f ./etc/config.json ]; then
    echo "⚠️  缺少配置文件，正在从模板创建..."
    cp ./etc/config.example.json ./etc/config.json
    chmod 600 ./etc/config.json
    echo "请编辑 ./etc/config.json 填入你的 Trilium 信息："
    echo "  - server: Trilium 服务地址（如 http://localhost:8080）"
    echo "  - token: ETAPI token（Trilium → Options → ETAPI 生成）"
    echo "  - calendarRootId: 日历根笔记 ID（留空自动探测）"
    exit 1
fi

# 检查连通性
./scripts/trilium.py check
```

- 如果 `check` 失败，引导用户修改 `etc/config.json` 直到通过。
- `config.json` 权限应为 600，**绝不要回显 token 值**。
- 配置通过后继续下面的流程。

## 何时触发

**主动提议**（展示草稿，确认后才写）：
- 🪤 踩坑 — 排查了非平凡的问题（根因不明显、以后可能再踩）
- 📦 里程碑 — 功能落地、模块跑通、联调成功
- 🚦 决策 — 多方案技术选型，值得记下理由与取舍
- 💡 学习 — 搞懂了之前不清楚的机制/工具/API

**直接执行**：用户明确说"记一下""写到 trilium""写进日记"。
**不要记**：琐碎操作（改 typo、跑常规命令）。

## 工作流程

### 写入

1. **起草** markdown，结构建议：
   - 踩坑：现象 → 原因 → 解决
   - 工作：背景 → 做了什么 → 结果
   - 带关键命令、报错、代码片段
2. **展示确认**：草稿 + `类型 + 标题` 给用户看，**确认后才写**
3. **写入**：调 `add` 命令，通过 heredoc stdin 传入内容（无需临时文件）
4. **回报**：贴出标题、日期和打开链接

### 查看

1. 用户想看某条日记详情时，用 `get` 命令
2. 加 `--content` 同时显示正文内容
3. 如果用户不知道 noteId，先用 `list --date` 查找

### 修改

1. 用户说"改一下""更新"时触发
2. 用 `update` 命令，按需传 `--title`、`--type`，内容通过 heredoc stdin 传入
3. 修改类型时自动更新标题前缀 emoji

### 删除

1. 用户说"删掉""不要了"时触发
2. **先展示**即将删除的条目信息（标题、类型、日期），**确认后再删**
3. 调 `delete` 命令

## 命令

```bash
cd "$(dirname "$SKILL_MD")"   # 按实际安装路径调整

# 检查连通性（含日历根标签验证）
./scripts/trilium.py check

# 写入（heredoc stdin，推荐写法，无需临时文件）
./scripts/trilium.py add --type trap --title "ETAPI 401 鉴权" <<'EOF'
## 现象
调用 ETAPI 返回 401...

## 解决
重新生成 token...
EOF

# 写入（简短内容可用 echo + pipe）
echo '## 背景\n...\n## 结果\n...' | \
  ./scripts/trilium.py add --type work --title "联调通过"

# 写入（指定日期）
./scripts/trilium.py add --type work --title "联调通过" \
  --date 2026-05-28 <<'EOF'
## 背景
前后端联调完成

## 结果
所有接口跑通
EOF

# 写入（交互式编辑器，不传内容时自动打开 $EDITOR）
./scripts/trilium.py add --type learn --title "新知识"

# 查看详情
./scripts/trilium.py get <noteId>              # 元数据
./scripts/trilium.py get <noteId> --content    # 含内容

# 修改内容（heredoc stdin）
./scripts/trilium.py update <noteId> <<'EOF'
## 新内容
更新后的 markdown...
EOF

# 修改标题/类型
./scripts/trilium.py update <noteId> --title "新标题"
./scripts/trilium.py update <noteId> --type work

# 删除
./scripts/trilium.py delete <noteId>

# 列出（文本格式）
./scripts/trilium.py list
./scripts/trilium.py list --date 2026-05-29

# 列出（JSON 格式，便于程序化处理）
./scripts/trilium.py list --format json
```

类型映射：`trap`→bx bx-bug-alt `work`→bx bx-package `decision`→bx bx-traffic-cone `learn`→bx bx-bulb
图标通过 `#iconClass` 标签设置（Trilium 原生 Boxicons），可用 `--prefix` 覆盖自定义 Boxicons class。

## 实现细节

日历结构 — 配置了 `calendarRootId` 时使用 ETAPI `/calendar/days/{date}` 端点
（自动创建/查找日 note），否则退回手动幂等查找或创建：
```
Journal (#calendarRoot)
 └─ 2026            #yearNote=2026
     └─ 05 - May    #monthNote=2026-05
         └─ 29 - 周五  #dateNote=2026-05-29  ← 日期笔记
             └─ 标题  #iconClass="bx bx-bug-alt"  ← 条目（带图标）
```

网络请求自动重试 3 次（502/503/504），指数退避间隔 0.5s。

条目不打 `#startDate`（否则被渲染为置顶全天事件），只打 `#diary`、`#diaryType=<type>`、`#diaryDate=YYYY-MM-DD` 用于检索。
图标通过 `#iconClass` 标签设置（Boxicons 图标库），在笔记树和日历视图中渲染。

## 注意事项

- 含反引号/代码块的内容用 heredoc（`<<'EOF'`），无需临时文件，单引号包裹 EOF 防止 shell 转义
- markdown 本地渲染为 HTML（ETAPI 的 render-markdown 接口不认 ETAPI token）
- 图标使用 [Boxicons](https://boxicons.com/)（`bx` 前缀），通过 `#iconClass` 标签应用
- 日历根 id 在 `etc/config.json` 的 `calendarRootId`，留空自动探测 `#calendarRoot`
- 凭证文件 `etc/config.json`（权限 600，已 gitignore，**切勿回显 token**）
- 排错参考 `references/etapi.md`

