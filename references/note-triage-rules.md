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
