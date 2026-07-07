# Trilium 接入参考

本 skill 通过 **ETAPI**（Trilium 对外公开 REST API）把 Claude Code 会话提炼成 **Knowledge 分类树**里的知识笔记，并 clone 到内置**日历 / Journal** 作为副入口。

## 配置

`etc/config.json`（权限 600，已 gitignore）：

```json
{
  "server": "http://trilium.localhost",
  "token": "<ETAPI token>",
  "calendarRootId": "",
  "knowledgeRootId": ""
}
```

- `server`：Trilium 地址，无需结尾斜杠。
- `token`：ETAPI token，在 **Trilium → Options（设置）→ ETAPI → Create new ETAPI token** 生成，可随时吊销。
- `calendarRootId`：日历根笔记 id（Journal）。留空则脚本按 `#calendarRoot` 自动探测；探测到多个会报错要求显式指定。
- `knowledgeRootId`：知识树根笔记 id。留空则脚本按 `#knowledgeRoot` 自动探测；建议根笔记标题为 `Knowledge`。

密码换 token（应急，不推荐长期用）：

```bash
curl -s -X POST http://trilium.localhost/etapi/auth/login \
  -H 'Content-Type: application/json' -d '{"password":"<密码>"}'
# -> {"authToken":"..."}
```

## 知识笔记数据模型

主入口是 `Knowledge/<Type>/<Topic>/<Note>`：

| 层级 | 标题样例 | 识别标签 |
|---|---|---|
| 知识根 | `Knowledge` | `#knowledgeRoot` |
| 类型 | `TIL` / `Ideas` / `References` | `#typeNote=til|idea|ref` |
| 主题 | `Postgres` / `TriliumDiary` | `#topicNote=<type>:<topic>` |
| 笔记 | `TIL: ...` / `Idea: ...` / `Ref: ...` | `#knowledge` `#type` `#topic` `#noteDate` `#sourceSession` `#iconClass`；ref 额外有 `#url` |

- 正文由本地 markdown 渲染成 HTML 后写入 Trilium。
- 同一份 note 会 clone 到当天 Journal；Knowledge 是主位，Journal 是副入口。
- clone 使用同一个标题，不额外加 `踩坑 ·` 之类日历前缀。

## 日历 clone 数据模型

Journal 是 `book` 笔记，带 `#calendarRoot`、`#viewType=calendar`。层级与识别标签：

| 层级 | 标题样例 | 识别标签 |
|---|---|---|
| 年 | `2026` | `#yearNote=2026` |
| 月 | `05 - May` | `#monthNote=2026-05` |
| 日 | `29 - 周五` | `#dateNote=2026-05-29` |
| 条目 | `TIL: 标题` | 同一份 Knowledge note 的 clone；标签仍在原 note 上 |

- 条目通过 branch clone 挂在**日期笔记下**，作为其子笔记直接显示在该日的日历格子里。
- **不要给条目加 `#startDate`**：那会被日历渲染成置顶的全天事件条，排在日期标题之上，与其它条目呈现不一致。`#noteDate` 是普通检索标签，不影响布局。
- 历史 recap 版本曾使用 `踩坑 ·` 前缀；当前知识笔记使用 `TIL:` / `Idea:` / `Ref:` 标题，并以 Knowledge 树检索为主。
- 脚本按上述 label 查找/创建年月日节点，**幂等**；已有的日期笔记（含 Trilium 原生建的）会复用，不重复创建。
- 月标题用英文月名（与 Trilium 原生一致），日标题用 `DD - 周X`。

## ETAPI 完整端点参考

来源：`api.json`（OpenAPI 3.0.3）。

### 认证

- **ETAPI Token**：请求头 `Authorization: <token>`（0.93+ 也接受 `Bearer <token>`）。
- **密码换 Token**：`POST /etapi/auth/login` `{"password":"xxx"}` → `{"authToken":"..."}`。
- **吊销 Token**：`POST /etapi/auth/logout`。

### 笔记（Notes）

| 操作 | 方法 | 端点 | 说明 |
|---|---|---|---|
| 搜索 | `GET` | `/etapi/notes?search=...` | 支持 `limit`、`orderBy`、`orderDirection`、`ancestorNoteId`、`fastSearch`、`debug` |
| 获取单条 | `GET` | `/etapi/notes/{noteId}` | 返回 Note 对象（含 attributes、parentNoteIds 等） |
| 创建 | `POST` | `/etapi/create-note` | body: `parentNoteId`, `title`, `type`, `content`; 可选 `notePosition`, `prefix`, `noteId` |
| 更新 | `PATCH` | `/etapi/notes/{noteId}` | body 中只传要改的字段（`title` 等） |
| 删除 | `DELETE` | `/etapi/notes/{noteId}` | 204 |
| 恢复删除 | `POST` | `/etapi/notes/{noteId}/undelete` | 笔记必须已删除且有未删除的父节点 |

### 笔记内容（Note Content）

| 操作 | 方法 | 端点 | 说明 |
|---|---|---|---|
| 获取内容 | `GET` | `/etapi/notes/{noteId}/content` | 返回 text/html |
| 更新内容 | `PUT` | `/etapi/notes/{noteId}/content` | body: 纯文本 HTML |

### 导出/导入

| 操作 | 方法 | 端点 | 说明 |
|---|---|---|---|
| 导出 | `GET` | `/etapi/notes/{noteId}/export?format=html\|markdown\|share` | 返回 ZIP |
| 导入 | `POST` | `/etapi/notes/{noteId}/import` | 上传 ZIP |

### 标签/属性（Attributes）

| 操作 | 方法 | 端点 | 说明 |
|---|---|---|---|
| 创建 | `POST` | `/etapi/attributes` | body: `noteId`, `type`=`label`\|`relation`, `name`, `value` |
| 获取 | `GET` | `/etapi/attributes/{attributeId}` | |
| 更新 | `PATCH` | `/etapi/attributes/{attributeId}` | label 只能改 `value` 和 `position`；relation 只能改 `position` |
| 删除 | `DELETE` | `/etapi/attributes/{attributeId}` | 204 |

### 日历（Calendar）

| 操作 | 方法 | 端点 | 说明 |
|---|---|---|---|
| 日笔记 | `GET` | `/etapi/calendar/days/{date}` | date 格式 `YYYY-MM-DD`，不存在则自动创建 |
| 周笔记 | `GET` | `/etapi/calendar/weeks/{week}` | week 格式 `YYYY-Www`（ISO 8601） |
| 月笔记 | `GET` | `/etapi/calendar/months/{month}` | month 格式 `YYYY-MM` |
| 年笔记 | `GET` | `/etapi/calendar/years/{year}` | year 格式 `YYYY` |

> **注意**：配置了 `calendarRootId` 时，本项目优先使用 `GET /etapi/calendar/days/{date}` 获取或创建当天日历节点；未配置时才回退到手动查找 `#yearNote` / `#monthNote` / `#dateNote`。

### 分支（Branches）

| 操作 | 方法 | 端点 | 说明 |
|---|---|---|---|
| 创建/更新 | `POST` | `/etapi/branches` | 克隆笔记到其他位置；已存在则更新 |
| 获取 | `GET` | `/etapi/branches/{branchId}` | |
| 更新 | `PATCH` | `/etapi/branches/{branchId}` | 只能改 `prefix` 和 `notePosition` |
| 删除 | `DELETE` | `/etapi/branches/{branchId}` | 最后一个分支删除时笔记也删除 |

### 附件（Attachments）

| 操作 | 方法 | 端点 | 说明 |
|---|---|---|---|
| 创建 | `POST` | `/etapi/attachments` | |
| 获取 | `GET` | `/etapi/attachments/{attachmentId}` | |
| 更新 | `PATCH` | `/etapi/attachments/{attachmentId}` | 只能改 `role`, `mime`, `title`, `position` |
| 删除 | `DELETE` | `/etapi/attachments/{attachmentId}` | 204 |
| 获取内容 | `GET` | `/etapi/attachments/{attachmentId}/content` | |
| 更新内容 | `PUT` | `/etapi/attachments/{attachmentId}/content` | |

### 版本（Revisions）

| 操作 | 方法 | 端点 | 说明 |
|---|---|---|---|
| 创建快照 | `POST` | `/etapi/notes/{noteId}/revision` | 204 |
| 列出 | `GET` | `/etapi/notes/{noteId}/revisions` | |
| 获取 | `GET` | `/etapi/revisions/{revisionId}` | |
| 获取内容 | `GET` | `/etapi/revisions/{revisionId}/content` | |

### 其他

| 操作 | 方法 | 端点 | 说明 |
|---|---|---|---|
| 应用信息 | `GET` | `/etapi/app-info` | 版本、DB 版本、构建信息 |
| 收件箱 | `GET` | `/etapi/inbox/{date}` | 返回当天收件箱笔记 |
| 刷新排序 | `POST` | `/etapi/refresh-note-ordering/{parentNoteId}` | 修改分支位置后需调用 |
| 数据库备份 | `PUT` | `/etapi/backup/{backupName}` | |
| 变更历史 | `GET` | `/etapi/notes/history` | 可选 `ancestorNoteId` 限定子树 |

## 本项目用到的端点

| 操作 | 端点 |
|---|---|
| 校验/版本 | `GET /etapi/app-info` |
| 搜索笔记 | `GET /etapi/notes?search=...` |
| 查笔记 | `GET /etapi/notes/{noteId}` |
| 建笔记 | `POST /etapi/create-note` |
| 改笔记元数据 | `PATCH /etapi/notes/{noteId}` |
| 改笔记内容 | `PUT /etapi/notes/{noteId}/content` |
| 删笔记 | `DELETE /etapi/notes/{noteId}` |
| 获取日历日笔记 | `GET /etapi/calendar/days/{date}` |
| 创建 clone 分支 | `POST /etapi/branches` |
| 删除 clone 分支 | `DELETE /etapi/branches/{branchId}` |
| 创建标签 | `POST /etapi/attributes` |
| 更新标签 | `PATCH /etapi/attributes/{attributeId}` |
| 删除标签 | `DELETE /etapi/attributes/{attributeId}` |

## markdown 转换为何在本地做

Trilium 自带 `POST /api/other/render-markdown`，但属于**内部 API**（`/api/`），只认
session；用 ETAPI token 调会返回 `401 Logged in session not found`。ETAPI 的 zip
import 又会把 `.md` 当 `file` 笔记原样存（mime `text/markdown`）不渲染。

因此本 skill 用 Python `markdown` 库在本地把 md 渲染成 HTML 再写入，依赖由 `uv run`
经脚本头部 PEP 723 内联元数据自动安装，无需全局环境。

## 排错

- **401**：token 失效/被吊销 → 重新生成并更新 `etc/config.json`。
- **找不到知识根**：确认 Knowledge 笔记带 `#knowledgeRoot`，或在 config 写死 `knowledgeRootId`。
- **找不到日历根**：确认 Journal 笔记带 `#calendarRoot`，或在 config 写死 `calendarRootId`。
- **连接失败**：`curl -I http://trilium.localhost` 确认可达。
- **依赖解析慢**：首次 `uv run` 会下载 markdown/requests，之后走缓存。
- **代码块乱码**：用 heredoc / stdin 传正文，避免把含反引号的内容拼进 shell 参数。
