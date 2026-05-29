# Trilium 接入参考

本 skill 通过 **ETAPI**（Trilium 对外公开 REST API）把日记写入内置**日历 / Journal**。

## 配置

`etc/config.json`（权限 600，已 gitignore）：

```json
{
  "server": "http://trilium.localhost",
  "token": "<ETAPI token>",
  "calendarRootId": "iJjmKSfW5UD2"
}
```

- `server`：Trilium 地址，无需结尾斜杠。
- `token`：ETAPI token，在 **Trilium → Options（设置）→ ETAPI → Create new ETAPI token** 生成，可随时吊销。
- `calendarRootId`：日历根笔记 id（Journal）。留空则脚本按 `#calendarRoot` 自动探测；探测到多个会报错要求显式指定。

密码换 token（应急，不推荐长期用）：

```bash
curl -s -X POST http://trilium.localhost/etapi/auth/login \
  -H 'Content-Type: application/json' -d '{"password":"<密码>"}'
# -> {"authToken":"..."}
```

## 日历数据模型

Journal 是 `book` 笔记，带 `#calendarRoot`、`#viewType=calendar`。层级与识别标签：

| 层级 | 标题样例 | 识别标签 |
|---|---|---|
| 年 | `2026` | `#yearNote=2026` |
| 月 | `05 - May` | `#monthNote=2026-05` |
| 日 | `29 - 周五` | `#dateNote=2026-05-29` |
| 条目 | `踩坑 · 标题` | 无日期标签；仅 `#diary` `#diaryType=<type>` `#diaryDate=YYYY-MM-DD` |

- 条目挂在**日期笔记下**，作为其子笔记直接显示在该日的日历格子里（与 Trilium 原生当天条目相同）。
- **不要给条目加 `#startDate`**：那会被日历渲染成置顶的全天事件条，排在日期标题之上，与其它条目呈现不一致。`#diaryDate` 是普通检索标签，不影响布局。
- **标题前缀不能以方括号开头**：日历视图（FullCalendar）把日期笔记与各条目按标题做 ICU root 排序；`[`/`【` 排在数字之前，会让条目浮到数字开头的日期笔记（`29 - 周五`）上方。用 CJK 字符开头的前缀（`踩坑 · `）排在数字之后，条目稳留在日期标题下方。（已用 PyICU 验证 root collator 比较结果。）
- 脚本按上述 label 查找/创建年月日节点，**幂等**；已有的日期笔记（含 Trilium 原生建的）会复用，不重复创建。
- 月标题用英文月名（与 Trilium 原生一致），日标题用 `DD - 周X`。

## 用到的 ETAPI 端点

| 操作 | 端点 |
|---|---|
| 校验/版本 | `GET /etapi/app-info` |
| 找日历根/节点 | `GET /etapi/notes?search=#calendarRoot` / `… #dateNote="YYYY-MM-DD"` |
| 建笔记 | `POST /etapi/create-note`（parentNoteId,title,type=text,content） |
| 加标签 | `POST /etapi/attributes`（noteId,type=label,name,value） |
| 删除 | `DELETE /etapi/notes/{noteId}` |

鉴权：请求头 `Authorization: <token>`（0.93+ 也接受 `Bearer <token>`）。
搜索带连字符的标签值务必加引号：`#dateNote="2026-05-29"`（脚本已处理）。

## markdown 转换为何在本地做

Trilium 自带 `POST /api/other/render-markdown`，但属于**内部 API**（`/api/`），只认
session；用 ETAPI token 调会返回 `401 Logged in session not found`。ETAPI 的 zip
import 又会把 `.md` 当 `file` 笔记原样存（mime `text/markdown`）不渲染。

因此本 skill 用 Python `markdown` 库在本地把 md 渲染成 HTML 再写入，依赖由 `uv run`
经脚本头部 PEP 723 内联元数据自动安装，无需全局环境。

## 排错

- **401**：token 失效/被吊销 → 重新生成并更新 `etc/config.json`。
- **找不到日历根**：确认 Journal 笔记带 `#calendarRoot`，或在 config 写死 `calendarRootId`。
- **连接失败**：`curl -I http://trilium.localhost` 确认可达。
- **依赖解析慢**：首次 `uv run` 会下载 markdown/requests，之后走缓存。
- **代码块乱码**：含反引号的内容用 `--content-file` 传入，别用 shell 字符串拼接。
