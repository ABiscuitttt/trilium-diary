---
name: trilium-diary
description: "把开发日记写入 Trilium 日历。Use when: 踩坑解决 / 工作里程碑 / 技术决策 / 学到新东西；用户说'记一下''写到 trilium''写进日记'时直接执行。"
---

# Trilium 工作日记

将 markdown 日记写入 Trilium 内置**日历（Journal）**面板，自动挂到对应日期下。

## 初始化

**每次使用前先检查配置**。执行：

```bash
SKILL_DIR=~/.claude/skills/trilium-diary

# 检查 config.json 是否存在
if [ ! -f "$SKILL_DIR/etc/config.json" ]; then
    echo "⚠️  缺少配置文件，正在从模板创建..."
    cp "$SKILL_DIR/etc/config.example.json" "$SKILL_DIR/etc/config.json"
    chmod 600 "$SKILL_DIR/etc/config.json"
    echo "请编辑 $SKILL_DIR/etc/config.json 填入你的 Trilium 信息："
    echo "  - server: Trilium 服务地址（如 http://localhost:8080）"
    echo "  - token: ETAPI token（Trilium → Options → ETAPI 生成）"
    echo "  - calendarRootId: 日历根笔记 ID（留空自动探测）"
    exit 1
fi

# 检查连通性
"$SKILL_DIR/scripts/trilium.py" check
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

1. **起草** markdown，结构建议：
   - 踩坑：现象 → 原因 → 解决
   - 工作：背景 → 做了什么 → 结果
   - 带关键命令、报错、代码片段
2. **展示确认**：草稿 + `类型 + 标题` 给用户看，**确认后才写**
3. **写入**：调 `add` 命令，含代码块用 `--content-file`
4. **回报**：贴出标题、日期和打开链接

## 命令

```bash
SKILL_DIR=~/.claude/skills/trilium-diary   # 按实际安装路径调整

# 检查连通性
"$SKILL_DIR/scripts/trilium.py" check

# 写入（stdin）
echo '## 现象\n...\n## 解决\n...' | \
  "$SKILL_DIR/scripts/trilium.py" add --type trap --title "ETAPI 401 鉴权"

# 写入（文件，含代码块时推荐）
"$SKILL_DIR/scripts/trilium.py" add --type work --title "联调通过" \
  --date 2026-05-28 --content-file /tmp/note.md

# 列出
"$SKILL_DIR/scripts/trilium.py" list
"$SKILL_DIR/scripts/trilium.py" list --date 2026-05-29
```

类型映射：`trap`→🪤 `work`→📦 `decision`→🚦 `learn`→💡
其他值无前缀，可用 `--prefix` 覆盖（勿用方括号开头）。

## 实现细节

日历结构 — 幂等查找或创建，复用 Trilium 已有节点：
```
Journal (#calendarRoot)
 └─ 2026            #yearNote=2026
     └─ 05 - May    #monthNote=2026-05
         └─ 29 - 周五  #dateNote=2026-05-29  ← 日期笔记
             └─ 🪤 · 标题                    ← 条目（日期笔记的子笔记）
```

条目不打 `#startDate`（否则被渲染为置顶全天事件），只打 `#diary`、`#diaryType=<type>`、`#diaryDate=YYYY-MM-DD` 用于检索。
**前缀用 emoji 非方括号**：ICU 排序中 `[` `【` 排在数字前会导致条目浮到日期标题上方。

## 注意事项

- 含反引号/代码块的内容用 `--content-file`，避免 shell 转义
- markdown 本地渲染为 HTML（ETAPI 的 render-markdown 接口不认 ETAPI token）
- 日历根 id 在 `etc/config.json` 的 `calendarRootId`，留空自动探测 `#calendarRoot`
- 凭证文件 `etc/config.json`（权限 600，已 gitignore，**切勿回显 token**）
- 排错参考 `references/etapi.md`

