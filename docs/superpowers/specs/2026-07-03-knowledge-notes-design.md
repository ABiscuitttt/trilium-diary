# trilium-diary v3.0 · 通用 Trilium 知识笔记助手设计

**日期**：2026-07-03
**版本目标**：3.0.0（断代式重构，撤 recap）
**分支建议**：`refactor/knowledge-notes`

---

## 1. 背景与动机

当前 trilium-diary v2.0 是一个高度聚焦的 skill：把 Claude Code 会话的 JSONL 忠实渲染成 markdown，写入 Trilium 日历面板作为 `Recap: xxx` 笔记。定位是"过程流水账"，AI 是格式化器不是编辑者。

v3.0 转向定位：**通用 Trilium 知识笔记助手**。用户在 Claude Code 会话里，用一句话触发，由 AI 从当前上下文提炼出**未来还能被自己捞出来用**的知识型笔记，落到 Trilium 的分类树 + 日历双入口。

**首批支持类型**：
- **TIL**（Today I Learned）：debug、读源码、读文档得到的知识点
- **Idea**（想法）：项目想法、待研究话题、灵感
- **Reference**（参考资料）：链接 + 摘要，"这篇 blog / paper / issue 讲了 X"

recap 撤销。历史 recap 笔记（Trilium 里已有的 `#diary` 数据）保留但脚本不再管理。

## 2. 用户场景与触发

**触发方式**：只在 Claude Code 会话里由用户自然语言触发。

**触发场景分派**：

| 用户说 | 调用方式 | 输入类型 |
|---|---|---|
| `记一下` / `记个 TIL` / `记个想法` / `记个参考` | **subagent（single）** | 会话上下文 |
| `整理一下` / `批量记这次会话` | **subagent（batch）** | 会话上下文 |
| `看看记了什么` / `列一下今天 / 关于 X 的` | 主 Claude 直调 `list` | 已知参数 |
| `打开 / 显示 abc 那条` | 主 Claude 直调 `get [--content]` | 已知 noteId |
| `改标题为 X` / `改图标为 Y` / `改内容` | 主 Claude 直调 `update` | 已知 noteId |
| `删了 abc` | 主 Claude 直调 `delete` | 已知 noteId |
| `合并主题 X 和 Y` | 主 Claude 直调 `note merge-topic` | 已知主题名 |
| `都有哪些主题` | 主 Claude 直调 `note topics` | 无 |

**不做主动建议**——AI 不主动问"要不要记"，只在用户显式触发时动手。

**AI 全自动**：写入场景下 subagent 判类型、拟标题、选主题、写正文，直接落盘。用户想改后用 `update` / `delete`。

**架构硬约束**：**从会话上下文生成笔记**必须派 subagent 执行——这是唯一需要读 JSONL 并做大量判断的场景，会污染主对话 context。其它 CRUD 是已知参数的单点调用，主 Claude 直接调 CLI 即可（用 Bash 工具）。

## 3. 整体架构

**写入路径**（需读 JSONL、涉大量判断）：

```
┌─────────────────────────────────────────────────────────────┐
│  Claude Code 主对话                                          │
│  · 匹配写入触发词（记一下 / 整理一下）                          │
│  · 打包入参 → Agent 工具（general-purpose）                    │
│  · 展示 subagent 返回的简报                                    │
└─────────────────────────────────────────────────────────────┘
                     ↓ Agent 工具
┌─────────────────────────────────────────────────────────────┐
│  Subagent（独立 context）                                     │
│  · 读 agents/note-taker.md + references/note-triage-rules.md │
│  · 读 ~/.claude/projects/<slug>/<sid>.jsonl                   │
│  · 判类型 / 拟标题 / 选主题 / 写正文 / 选图标                    │
│  · 逐条调 CLI 落盘                                            │
│  · 收集 noteId + url，return 结构化简报                        │
└─────────────────────────────────────────────────────────────┘
                     ↓ 命令行 + stdin markdown
┌─────────────────────────────────────────────────────────────┐
│  scripts/trilium.py（纯落盘器）                                │
│  · 找/建 Knowledge/<Type>/<Topic>/ 分类树                       │
│  · 创建笔记 + 标签                                             │
│  · Clone 到 Journal/<yyyy>/<MM>/<dd>/                          │
│  · 输出结构化 JSON                                             │
└─────────────────────────────────────────────────────────────┘
                     ↓ ETAPI
                   Trilium
```

**读/改/删/查询路径**（已知参数、单点调用）：

```
Claude Code 主对话 → Bash 工具 → scripts/trilium.py {list|get|update|delete|note topics|note merge-topic} → ETAPI → Trilium
```

**三层职责严格分离**：
- **主对话**：解析用户意图，写入场景派 subagent，其它场景直调 CLI 并把 JSON 结果转述给用户。
- **Subagent**：只在写入场景启用，读 JSONL 做 AI 判断，调 CLI 落盘。
- **CLI**：纯 Trilium 客户端 + 分类树管理，不做 AI 判断，不读 JSONL，输出机器可解析的 JSON。

## 4. Trilium 数据模型

### 4.1 两棵根树

```
<root>
├─ Journal (#calendarRoot)              ← 保留
│   └─ 2026/07/03 - 周五/
│       └─ [clone] TIL: Postgres time zones     ← 日历副入口（clone）
│
└─ Knowledge (#knowledgeRoot)           ← 新增
    ├─ TIL/                             #typeNote=til  #iconClass="bx bx-bulb"
    │   └─ Postgres/                    #topicNote="til:Postgres"  #iconClass="bx bx-folder"
    │       └─ TIL: Postgres time zones (主位)
    │           #knowledge #type=til #topic=Postgres
    │           #sourceSession=<sid> #noteDate=2026-07-03
    │           #iconClass="bx bx-data"
    ├─ Ideas/                           #typeNote=idea  #iconClass="bx bx-brain"
    │   └─ <Topic>/                     #topicNote="idea:<Topic>"
    │       └─ Idea: ... (主位)
    │           #knowledge #type=idea #topic=... #sourceSession=... #noteDate=...
    │           #iconClass=<按主题域选>
    └─ References/                      #typeNote=ref  #iconClass="bx bx-book-bookmark"
        └─ <Topic>/                     #topicNote="ref:<Topic>"
            └─ Ref: ... (主位)
                #knowledge #type=ref #topic=... #url=... #sourceSession=... #noteDate=...
                #iconClass=<按主题域选>

（注：Journal 实际结构是 `Journal/<yyyy>/<MM - Month>/<dd - 周X>/`，
上图简写为 `2026/07/03 - 周五/`；沿用 v2.0 的日历路径逻辑。）
```

### 4.2 标签约定

**根节点**：
- `#calendarRoot` — 日历根（Trilium 内置约定）
- `#knowledgeRoot` — 知识树根（本项目新增约定）

**结构节点**：
- `#typeNote=til|idea|ref` — 类型节点幂等键
- `#topicNote="<type>:<Topic>"` — 主题子笔记幂等键；`<type>` 前缀让不同类型下的同名主题不冲突（`til:Postgres` 与 `ref:Postgres` 是两个节点）

**笔记本身**：
- `#knowledge` — 所有知识笔记通用标签（用于 `list` 检索）
- `#type=til|idea|ref` — 类型
- `#topic=<Topic>` — 主题
- `#sourceSession=<sessionId>` — 单向指回源 session（能反查这条笔记是哪次会话产生的）
- `#noteDate=<YYYY-MM-DD>` — AI 认定的笔记归属日期（由 CLI `--note-date` 参数指定，subagent 默认传今天）；跟 Trilium 内建的 `dateCreated` 不同，后者是物理创建时间戳
- `#iconClass=<bx ...>` — 图标（详见第 8 段）
- `#url=<url>` — 仅 reference 类型必带

### 4.3 双重挂载（clone）

主位在 `Knowledge/<Type>/<Topic>/`。同时通过 ETAPI 的 `branches` 接口把同一 noteId 挂第二个父到 `Journal/<yyyy>/<MM>/<dd>/`——同一份内容，两个入口。

**所有三种类型**（TIL、Idea、Reference）都 clone 到日历。

## 5. 组件与文件布局

```
trilium-diary/
├─ SKILL.md                          ← 重写：init 检查、触发词、subagent 调用协议、简报格式
├─ README.md                         ← 重写：定位换成"通用知识笔记"
├─ pyproject.toml                    ← version 3.0.0，description 换掉
│
├─ scripts/
│   ├─ trilium.py                    ← 精简改写：纯落盘器
│   └─ jsonl_render.py               ← 删除
│
├─ agents/
│   └─ note-taker.md                 ← 新增：subagent 完整 system prompt
│
├─ references/
│   ├─ etapi.md                      ← 保留
│   ├─ etapi.openapi.json            ← 保留
│   └─ note-triage-rules.md          ← 新增：值得记口径 + 类型判定 + 命名规范 + 图标词表
│
├─ etc/
│   ├─ config.example.json           ← 加 knowledgeRootId 字段（可选）
│   ├─ config.json                   ← 用户本地（gitignored）
│   └─ .gitignore
│
└─ tests/
    ├─ test_client.py                ← 大改：围绕 note 生态重写
    ├─ test_pure.py                  ← 大改：删 recap 纯函数、加新纯函数
    ├─ test_commands.py              ← 新增：cmd 端到端 mock
    ├─ test_check.py                 ← 新增：check 扩展场景
    └─ fixtures/                     ← 精简，删 JSONL fixtures
```

**删除清单**：`scripts/jsonl_render.py`、`tests/test_jsonl_render.py`、`test_client.py` 中所有 `TestCmdRecap*` 类。

## 6. 命令表

```
check                                            # 输出人可读文本，供首次初始化
                                                 # 主 Claude 展示给用户

note til     --topic <T> --title <t>             # 从 stdin 读 markdown 正文
             --source-session <sid>
             --note-date YYYY-MM-DD
             [--icon "bx bx-xxx"]                # 可选，缺省用 TYPE_DEFAULT_ICONS[type]

note idea    （参数同 til）
note ref     --url <url>                         # ref 额外必带 --url
             （其它参数同 til）

note topics                                      # 列所有 #topicNote
note merge-topic --type <til|idea|ref> <fromTopic> <toTopic>
                                                 # 同类型内归并同义主题

list         [--type til|idea|ref]
             [--topic <T>] [--note-date YYYY-MM-DD]
             [--source-session <sid>] [--limit N]

get          <noteId> [--content]

update       <noteId> [--title <t>] [--icon "bx bx-xxx"]
                                                 # 从 stdin 读新 markdown 正文（可选）
                                                 # 不支持 --topic（改主题请 delete + 重记，或 merge-topic）

delete       <noteId>
```

**说明**：
- `note` 是命名空间，写入 + 主题治理命令在其下。
- `list/get/update/delete` 顶层，统一按 `#knowledge` 标签检索。
- **批量 triage 不作 CLI 子命令**——subagent 判断完仍逐条调 `note til/idea/ref` 落盘。
- 所有 `note {til,idea,ref}` 写入命令从 **stdin** 读 markdown 正文；stdout 输出结构化 JSON（AI 消费）。
- **`update` 不支持 `--topic`**：改主题涉及主位移动到新主题子笔记，语义复杂。想改就 `delete` + 重记；批量改用 `note merge-topic`。
- **`--source-session` 必填**：subagent 一定能拿到 sessionId；强制传能保证所有笔记都有反查入口。
- 除 `check` 外所有命令 stdout 输出 JSON，stderr 输出错误消息，AI 通过 exit code 判成败。

## 7. 数据流

### 7.1 单条显式记录

```
用户 "记个 TIL, Postgres timestamp 和 timestamptz 存储上其实一样"
   ↓
主 Claude Code
   · 匹配触发词 → mode="single"
   · Agent 工具调 subagent，传 { sessionId, projectDir, mode, hint, date? }
   ↓
Subagent
   1. Read agents/note-taker.md + references/note-triage-rules.md
   2. Read ~/.claude/projects/<slug>/<sid>.jsonl 尾部 ~50 条消息定位话题
   3. 判定：type=til / topic=Postgres / title / body / icon="bx bx-data"
   4. cat <<'EOF' | ./scripts/trilium.py note til \
          --topic Postgres --title "..." --icon "bx bx-data" \
          --source-session <sid> --date 2026-07-03
      <正文 markdown>
      EOF
   5. 解析 stdout JSON 拿 noteId + url
   6. Return { notes: [{ type, title, topic, why, noteId, url }] }
   ↓
主 Claude Code
   打印简报（type · title · topic · why · url）
```

### 7.2 批量整理

```
用户 "整理一下这次会话"
   ↓
Subagent（mode="batch"）
   1. Read 完整 JSONL
   2. 按"中等口径"筛候选：
        · 明显值得记的
        · 卡了很久突破的
        · 重复来回验证的结论
        · 值得未来查的命令片段
   3. 每个候选独立判 type/topic/title/body/icon
   4. 逐条调 CLI（失败继续，收集 failed[]）
   5. Return { notes: [...], skipped: [...], failed: [...] }
```

### 7.3 CLI 单次落盘

```
接收: --topic <T> --title <t> [--icon <i>] [--source-session <s>] [--date <d>]
      + stdin markdown
   ↓
1. load_config → server / token / 两个 root
2. Trilium.knowledge_root()                 # config 或 #knowledgeRoot 搜索
3. Trilium.ensure_type_path("til")          # 找/建 Knowledge/TIL/
4. Trilium.ensure_topic_path("til", "Postgres")  # 找/建 Knowledge/TIL/Postgres/
5. render_markdown(stdin) → HTML
6. create_note(parent=<topicNoteId>, title, html, type="text")
7. add_label(noteId, "knowledge")
   add_label(noteId, "type", "til")
   add_label(noteId, "topic", "Postgres")
   add_label(noteId, "sourceSession", <sid>)
   add_label(noteId, "noteDate", <YYYY-MM-DD>)
   add_label(noteId, "iconClass", <icon or TYPE_DEFAULT_ICONS["til"]>)
   # ref 类型额外 add_label(noteId, "url", <url>)
8. Trilium.ensure_date_path(<date>)         # 日笔记 id
9. Trilium.clone_note(noteId, dayNoteId)    # 挂第二个父
   （已挂过则跳过；失败则 stderr warn，stdout 输出 cloned=false）
10. print JSON to stdout
```

**幂等性**：
- 结构节点（type/topic/date）都是找-或-建，重复调安全。
- Clone 前查父节点集合，已挂过跳过。
- **笔记本身不做幂等**——每次显式记就是新一条；重复由 subagent 侧去重（`skipped[]`）。

## 8. 图标策略

Trilium 用 [boxicons](https://boxicons.com/) 图标库，通过 `#iconClass` 标签设图标，值形如 `bx bx-<name>`。

### 8.1 分层图标

| 层级 | 位置 | 图标 |
|---|---|---|
| 类型节点 | `Knowledge/TIL/` | `bx bx-bulb`（点亮的知识） |
| | `Knowledge/Ideas/` | `bx bx-brain`（脑洞构想） |
| | `Knowledge/References/` | `bx bx-book-bookmark`（带书签的书） |
| 主题节点 | `Knowledge/<Type>/<Topic>/` | `bx bx-folder`（统一，结构性节点不允许覆盖） |
| 笔记本身 | 默认 | 继承所在类型节点图标（`TYPE_DEFAULT_ICONS` 常量） |
| | AI 语义图标 | subagent 按主题域挑（见 8.2），覆盖默认 |

### 8.2 AI 语义图标词表

由 `references/note-triage-rules.md` 约束，subagent 只从下表选（**词表以 rules 文件为准，此表为 v3.0 初始版**）：

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

**规则**：subagent 判定核心主题域 → 用对应图标；匹配多个用最具体的（Bug workaround 优先于代码）；都不匹配用类型默认。词表不主动扩展，扩表需改 `references/note-triage-rules.md`。

### 8.3 CLI 侧图标参数

- `note til/idea/ref --icon "bx bx-xxx"`：可选，只接受完整 `bx bx-xxx` 形式，不做前缀补全，不校验合法性。缺省用 `TYPE_DEFAULT_ICONS[type]`。
- `update <noteId> --icon "bx bx-xxx"`：找到已有 `#iconClass` attribute 走 `patch_attribute` 更新；不存在则 `add_label`。
- 无效 iconClass 值 Trilium 只是不显示图标，不影响功能；规范化交 rules 文件约束 subagent。

## 9. 错误处理

### 9.1 CLI 层

保留现有 `Retry(total=3, backoff_factor=0.5, status_forcelist=[502,503,504])` + `die(msg)`。

| 场景 | 响应 |
|---|---|
| config / token 缺失 | `die` |
| Trilium 不可达 | `die` |
| Token 无效 (401) | `die` |
| `#knowledgeRoot` 找不到 / 多个 | `die` |
| `#calendarRoot` 找不到 | 只在 clone 时才需要；找不到 → clone 失败 warn 而非 die |
| 主位创建失败 | `die` |
| Clone 失败 | **不 die**，stderr warn，stdout 输出 `"cloned": false` |
| stdin markdown 为空 | `die` |
| 必填参数缺失 | argparse 报错 |

**Clone 失败不回滚主位**：分类树主位是主要价值，日历副入口失败可事后人工补挂。

### 9.2 Subagent 层

- 每条候选独立调 CLI，一条失败不影响其它。
- CLI 非零退出 → 加入 `failed[]`，继续下一条。
- AI 判错（类型/主题）→ 不自动回滚，用户可 `update` / `delete` 修正。
- 空手而归 → return `{ notes: [], note: "本次会话未发现符合中等口径的候选" }`。

### 9.3 主 Claude Code 层

- Agent 工具失败（崩溃/超时/非法 JSON）→ 展示错误建议重试。
- `failed[]` 非空 → 简报里显示失败清单。
- **不自动重试、不 fallback、不缓存。**

### 9.4 边界

- **主题名含特殊字符**（引号、换行）：subagent 侧规范化；CLI 侧 ETAPI 搜索表达式改用参数化构造，修掉现有 `_child_with_label` 的 f-string 拼接隐患。
- **短时间重复记同一条**：CLI 不去重，会创建两条；批量模式下 subagent 侧 skip；单条模式下用户自己删。

### 9.5 check 命令扩展

```
✓ Trilium 可达: <url> (v0.x.x)
✓ token 有效
✓ 日历根 = <id> (#calendarRoot 标签存在)
✓ 知识根 = <id> (#knowledgeRoot 标签存在)
i TIL / Ideas / References 类型节点：<存在 / 首次写入时自动建>
```

类型节点缺失只提示不报错——首次写入时会自动建。**不新增 `--init` 参数**（YAGNI）。

## 10. 测试策略

### 10.1 分层

| 层 | 是否自动化 | 说明 |
|---|---|---|
| CLI (`trilium.py`) | ✓ 单元 + 集成（mock ETAPI） | pytest 全跑 |
| Subagent 指令 | ✗ 手动黑盒 | 见 10.4 |
| 主 Claude Code | ✗ 不测 | 只是触发和展示 |

### 10.2 CLI 测试布局

```
tests/
├─ test_pure.py          纯函数（parse_date, render_markdown, 标题构造等）
├─ test_client.py        Trilium 类方法，mock requests.Session
├─ test_commands.py      cmd_* 端到端 mock（新增）
├─ test_check.py         check 扩展场景（新增）
└─ fixtures/             ETAPI 响应样例
```

**删除**：`test_jsonl_render.py`、`test_client.py` 里所有 `TestCmdRecap*`。

**保留**：`Trilium` 类基础方法测试（`_req` 重试、search、create_note、add_label 等）；`ensure_year/month/day` 系列。

### 10.3 新增测试重点

| 测试 | 覆盖 |
|---|---|
| `test_ensure_type_path` | 首次建 TIL/Ideas/References、幂等重复调、图标标签正确 |
| `test_ensure_topic_path` | 首次建主题子笔记、重复调返回同一 ID、特殊字符参数化不注入 |
| `test_clone_note` | ETAPI branches 挂第二个父、已挂过跳过、失败返回 cloned=false 不 die |
| `test_note_til_full_flow` | mock 所有 ETAPI 调用，验证主位路径、7 个 label、clone、stdout JSON |
| `test_note_ref_with_url` | 额外 `#url` 标签存在 |
| `test_note_merge_topic` | 主题下笔记 `#topic` 改写 + 移动 + 空主题节点删 |
| `test_list_filters` | `--type` / `--topic` / `--note-date` / `--source-session` 组合的 search 表达式 |
| `test_check_reports_both_roots` | 两个 root 全通过 / 缺 knowledgeRoot 报错 / 类型节点缺失只警告 |
| `test_icon_selection` | `--icon` 覆盖默认、缺省用 `TYPE_DEFAULT_ICONS` |
| `test_update_icon_patch` | `update --icon` 走 `patch_attribute` 更新已有 iconClass |

### 10.4 手动黑盒测试

准备 3-4 个真实场景，重构完人工跑并把 subagent 简报贴回 spec 附录：

1. **单条 til**：hint = "记个 TIL，Postgres timestamp 和 timestamptz 存储上其实一样"
2. **单条 idea**：hint = "记个想法，trilium-diary 应该支持 workspace 概念"
3. **单条 ref**：hint = "记个参考，刚看的这篇 blog 讲 SQLite WAL mode，链接 https://..."
4. **批量整理**：一段真实 debug session

### 10.5 CI

保留 `.github/workflows/ci.yml`（pytest + ruff）。新增测试全部 mock 无外部依赖。冒烟/黑盒不进 CI。

## 11. 迁移与兼容

**断代式全换**：
- 撤 recap 命令、jsonl_render 模块、相关测试。
- Trilium 里已有的 `#diary` 笔记（老 recap 数据）保留但脚本不再管理——若需查看/删除用 Trilium UI 或旧脚本。
- 版本：`pyproject.toml` 升 3.0.0；description 换成"通用 Trilium 知识笔记助手"。

**不做的事**：
- 不写 `migrate-recap` 迁移命令（用户不需要）。
- 不保留 `note recap` 类型（违背"recap 可以直接去掉"）。
- 不做向后兼容 shim。

## 12. 分支与提交策略

- 起 `refactor/knowledge-notes` 分支，跟历史 recap 重构对称。
- 提交按功能分层：数据模型（`Trilium` 类扩展）→ 命令层（cmd_note_*）→ SKILL/README/agents → tests。
- 合并前完成手动黑盒清单。

## 13. 关键决策记录

| # | 决策 | 理由 |
|---|---|---|
| 1 | 方向：通用知识笔记而非"更聪明的 recap" | 用户明确选 A |
| 2 | 首批类型限定 TIL / Idea / Reference | 用户挑的三类"痛点最强" |
| 3 | AI 全自动判类型/主题/标题 | 用户选 A（打字最少） |
| 4 | 只显式触发 + 支持批量 | 用户选 A+D |
| 5 | **副产物走 subagent，主对话不污染** | 用户显式要求，架构硬约束 |
| 6 | Subagent 回报简报 + 链接 | 用户选 C |
| 7 | 批量口径：中等 | 用户选 B |
| 8 | 日期默认今天 + `--date` 可覆盖 | 用户选 D |
| 9 | 分类树主位 + 日历 clone | 用户选 C，主入口是分类树 |
| 10 | 主题：AI 自由造 + `merge-topic` 归并 | 用户选 D，兼顾灵活与治理 |
| 11 | `#knowledgeRoot` 顶层树，对称 `#calendarRoot` | 用户选 A |
| 12 | 所有类型都 clone 到日笔记 | 用户选 A1 |
| 13 | `#sourceSession` 单向指回 | 用户选 B2，recap 内容不动 |
| 14 | 命令表：`note` 命名空间 + 顶层 CRUD | 用户选 B |
| 15 | 断代式全换 recap，v3.0.0 | 用户选 A |
| 16 | 图标按类型 + AI 主题域词表选，类型默认为 bulb/brain/book-bookmark | 用户要求"按内容选" |
| 17 | CLI 唯一调用方是 AI；stdout 输出 JSON（除 check） | 用户明确 |
| 18 | 写入场景派 subagent；读改删主题查询主 Claude 直调 CLI | 只有写入需要读 JSONL + 大量判断 |
| 19 | `update` 不支持 `--topic` | 主位移动语义复杂，用 delete + 重记 / merge-topic 替代 |
| 20 | `--source-session` 必填、`#createdDate` 改名 `#noteDate` | 澄清语义 |

## 14. 附录：SKILL.md 内容清单

重写后 SKILL.md 需包含：

1. **frontmatter**：`name` / `description`（触发词列表）
2. **初始化检查**：跟现在一致——从 `etc/config.example.json` 建 `etc/config.json`，跑 `check` 命令并展示输出
3. **触发场景分派表**（第 2 段那张表）
4. **写入路径**：主 Claude 匹配到写入触发词 → 用 Agent 工具调 general-purpose subagent，prompt 用第 15 段的 XML 入参格式 + 内嵌 `agents/note-taker.md` 内容
5. **读改删路径**：主 Claude 直接 Bash 调 CLI，解析 JSON 输出转述给用户
6. **简报模板**（第 16 段）
7. **配置文件位置和权限约束**（沿用 v2.0：`etc/config.json` 权限 600，不回显 token）

## 15. 附录：subagent 入参格式

主 Claude 用 Agent 工具（`subagent_type: general-purpose`）调用，prompt 结构：

```
<input>
  <sessionId>{{$CLAUDE_CODE_SESSION_ID}}</sessionId>
  <projectDir>{{$PWD}}</projectDir>
  <mode>single | batch</mode>
  <hint>{{用户原话，如"记个 TIL，Postgres timestamp..."}}</hint>
  <noteDate>{{YYYY-MM-DD，可选，缺省用今天}}</noteDate>
</input>

<instructions>
  {{完整嵌入 agents/note-taker.md 的内容}}
</instructions>

<rules>
  {{完整嵌入 references/note-triage-rules.md 的内容}}
</rules>
```

Subagent 按 instructions 执行，逐条调 CLI，最后 return 第 17 段格式的 JSON。

## 16. 附录：主对话简报模板

Subagent 返回后主 Claude 打印：

```
✓ 已记 N 条 · 跳过 M 条 · 失败 K 条

· TIL · <topic> · <title>
  why: <一句话说明>
  → <url>

· Idea · <topic> · <title>
  why: <一句话说明>
  → <url>

（失败清单，如有）
✗ <attemptedTitle>
  <error>
```

`N=0` 且非 batch 模式：`⚠ 没记到内容：<note 字段>`。
`N=0` batch 模式：`i 本次会话未发现符合中等口径的候选`。

## 17. 附录：subagent return schema

```json
{
  "notes": [
    {
      "type": "til | idea | ref",
      "title": "...",
      "topic": "...",
      "why": "一句话说明为什么值得记",
      "noteId": "...",
      "url": "http://trilium.../#root/..."
    }
  ],
  "skipped": [
    { "reason": "...", "hint": "..." }
  ],
  "failed": [
    { "attemptedTitle": "...", "error": "..." }
  ],
  "note": "可选：整体说明（如'本次会话未发现候选'）"
}
```

## 18. 附录：CLI stdout 契约

**note til/idea/ref 成功**：
```json
{"noteId": "abc123", "url": "http://.../#root/abc123", "cloned": true}
```

**note 成功但 clone 失败**：
```json
{"noteId": "abc123", "url": "http://.../#root/abc123", "cloned": false, "cloneError": "..."}
```

**list**：
```json
{"items": [{"noteId": "...", "title": "...", "type": "til", "topic": "...", "noteDate": "...", "sourceSession": "..."}, ...]}
```

**get**（不带 `--content`）：
```json
{"noteId": "...", "title": "...", "type": "til", "topic": "...", "noteDate": "...", "sourceSession": "...", "iconClass": "...", "url": "..."}
```

**get --content**：上述字段 + `"content": "<markdown 或 html>"`。

**note topics**：
```json
{"topics": [{"type": "til", "topic": "Postgres", "noteId": "<topicNoteId>", "count": 5}, ...]}
```

**note merge-topic**：
```json
{"moved": 5, "fromNoteId": "...", "toNoteId": "...", "fromEmpty": true}
```

**update / delete**：
```json
{"noteId": "abc123", "ok": true}
```

**失败通用**：非零退出码，stderr 打错误消息。AI 通过 exit code 判成败，不解析 stderr。

