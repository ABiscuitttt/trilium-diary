#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.12"
# dependencies = ["markdown>=3.5", "requests>=2.31"]
# ///
"""trilium-diary: write markdown dev-diary entries into Trilium's calendar.

Targets the built-in Journal/calendar (a `book` note tagged #calendarRoot):

    Journal (#calendarRoot)
      └─ YYYY            #yearNote=YYYY
         └─ MM - Mon     #monthNote=YYYY-MM
            └─ DD - 周X   #dateNote=YYYY-MM-DD     (day note)
               └─ 标题  #iconClass="bx bx-conversation"  (entry, child of day note)

Year/month/day nodes are found-or-created by their calendar labels (idempotent),
so they match what Trilium itself recognizes. Entries are plain child notes of
the date note (no #startDate — that would render as a pinned all-day event bar
above the day title). Entries carry #diary / #sessionId / #diaryDate / #iconClass
for filtering.

Markdown is rendered to HTML locally (Trilium text notes store HTML; the internal
render-markdown endpoint rejects ETAPI tokens). Deps managed by uv.

Commands:
    check                       verify server + token, locate the calendar root
    get NOTE_ID                 show entry details (--content for full content)
    update NOTE_ID [--title ..] modify entry title/content
    delete NOTE_ID              delete an entry by note id
    list [--date YYYY-MM-DD]    list diary entries
    recap [--title-suffix ..]   render session JSONL and write to calendar

Run directly (uv resolves deps):  ./trilium.py check
"""

import argparse
import datetime as _dt
import json
import os
import re
import sys

import markdown
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "..", "etc", "config.json")

# Permissive enough to allow UUIDs and agent ids like a3eebab8e916c82ee,
# but rejects chars that could break ETAPI search expressions (quotes, spaces, etc.)
_SESSION_ID_RE = re.compile(r"^[0-9a-zA-Z._-]+$")


def resolve_jsonl_path(
    session: str | None, project_dir: str | None
) -> tuple[str, str]:
    """Compose ~/.claude/projects/<slug>/<session>.jsonl from env or args.

    Returns (path, sid) so callers have a single authoritative source for
    the session id without re-deriving it from the environment.
    """
    sid = session or os.environ.get("CLAUDE_CODE_SESSION_ID")
    if not sid:
        die(
            "缺少 sessionId。请用 --session <id> 显式指定，"
            "或确保在 Claude Code 会话中（$CLAUDE_CODE_SESSION_ID）。"
        )
    if not _SESSION_ID_RE.match(sid):
        die(
            f"sessionId 格式非法（应只含字母、数字、点、下划线、短划线）: {sid!r}"
        )
    pdir = project_dir or os.getcwd()
    pdir_abs = os.path.abspath(pdir)
    slug = pdir_abs.replace("/", "-")
    path = os.path.expanduser(f"~/.claude/projects/{slug}/{sid}.jsonl")
    return path, sid


def _get_version():
    """Read version from pyproject.toml (works with uv run and direct execution)."""
    import tomllib

    pyproject = os.path.join(HERE, "..", "pyproject.toml")
    try:
        with open(pyproject, "rb") as f:
            return tomllib.load(f)["project"]["version"]
    except (FileNotFoundError, KeyError):
        return "unknown"

RECAP_ICON = "bx bx-conversation"
TYPE_DISPLAY_NAMES = {"til": "TIL", "idea": "Ideas", "ref": "References"}
TYPE_DEFAULT_ICONS = {
    "til": "bx bx-bulb",
    "idea": "bx bx-brain",
    "ref": "bx bx-book-bookmark",
}
TOPIC_FOLDER_ICON = "bx bx-folder"

WEEKDAY_ZH = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
MONTH_EN = [
    "",
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]

MD_EXTENSIONS = ["fenced_code", "tables", "sane_lists", "nl2br", "codehilite"]
MD_EXTENSION_CONFIGS = {"codehilite": {"noclasses": True}}


def die(msg, code=1):
    print(msg, file=sys.stderr)
    sys.exit(code)


def load_config():
    if not os.path.exists(CONFIG_PATH):
        die(f"找不到配置 {CONFIG_PATH}")
    with open(CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    if not cfg.get("token"):
        die("配置缺少 token (Trilium -> Options -> ETAPI 生成)")
    cfg.setdefault("server", "http://trilium.localhost")
    cfg["server"] = cfg["server"].rstrip("/")
    # calendarRootId optional: auto-detected via #calendarRoot if absent.
    cfg.setdefault("calendarRootId", "")
    cfg.setdefault("knowledgeRootId", "")
    return cfg


class Trilium:
    """ETAPI client scoped to the diary-into-calendar use case."""

    def __init__(self, cfg):
        self.base = cfg["server"] + "/etapi"
        self.cfg = cfg
        self.s = requests.Session()
        self.s.headers["Authorization"] = cfg["token"]
        retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[502, 503, 504])
        self.s.mount("http://", HTTPAdapter(max_retries=retry))
        self.s.mount("https://", HTTPAdapter(max_retries=retry))

    def _req(self, method, path, **kw):
        try:
            r = self.s.request(method, self.base + path, timeout=15, **kw)
        except requests.RequestException as e:
            die(f"连接 Trilium 失败 ({self.base}): {e}")
        if r.status_code == 401:
            die(
                "ETAPI token 无效或已吊销 (401)。"
                "请在 Trilium -> Options -> ETAPI 重新生成。"
            )
        if r.status_code >= 400:
            die(f"ETAPI {method} {path} -> HTTP {r.status_code}\n{r.text[:500]}")
        return r

    def app_info(self):
        return self._req("GET", "/app-info").json()

    def search(self, expr, **params):
        params["search"] = expr
        return self._req("GET", "/notes", params=params).json().get("results", [])

    def create_note(self, parent_id, title, content, ntype="text"):
        body = {
            "parentNoteId": parent_id,
            "title": title,
            "type": ntype,
            "content": content,
        }
        return self._req("POST", "/create-note", json=body).json()

    def add_label(self, note_id, name, value=""):
        body = {"noteId": note_id, "type": "label", "name": name, "value": value}
        return self._req("POST", "/attributes", json=body).json()

    def get_note(self, note_id):
        return self._req("GET", f"/notes/{note_id}").json()

    def get_note_content(self, note_id):
        return self._req("GET", f"/notes/{note_id}/content").text

    def update_note_content(self, note_id, content):
        return self._req(
            "PUT",
            f"/notes/{note_id}/content",
            data=content.encode("utf-8"),
            headers={"Content-Type": "text/plain; charset=utf-8"},
        )

    def delete_note(self, note_id):
        return self._req("DELETE", f"/notes/{note_id}")

    def update_note(self, note_id, **fields):
        return self._req("PATCH", f"/notes/{note_id}", json=fields).json()

    def patch_attribute(self, attr_id, **fields):
        return self._req("PATCH", f"/attributes/{attr_id}", json=fields).json()

    def delete_attribute(self, attr_id):
        return self._req("DELETE", f"/attributes/{attr_id}")

    # ---- calendar navigation ------------------------------------------------

    def calendar_root(self):
        """Resolve the calendar root note id (config override or #calendarRoot)."""
        if self.cfg.get("calendarRootId"):
            return self.cfg["calendarRootId"]
        hits = self.search("#calendarRoot", limit="5")
        if not hits:
            die(
                "找不到日历根（带 #calendarRoot 的笔记）。"
                "请在 etc/config.json 设置 calendarRootId，或在 Trilium 里建立日历。"
            )
        if len(hits) > 1:
            ids = ", ".join("{}({})".format(h["noteId"], h["title"]) for h in hits)
            die(
                f"发现多个 #calendarRoot：{ids}\n"
                "请在 etc/config.json 用 calendarRootId 指定。"
            )
        return hits[0]["noteId"]

    def knowledge_root(self):
        """Resolve the knowledge root note id (config override or #knowledgeRoot)."""
        if self.cfg.get("knowledgeRootId"):
            return self.cfg["knowledgeRootId"]
        hits = self.search("#knowledgeRoot", limit="5")
        if not hits:
            die(
                "找不到知识根（带 #knowledgeRoot 的笔记）。"
                "请在 etc/config.json 设置 knowledgeRootId，"
                "或在 Trilium 里建一条笔记打 #knowledgeRoot 标签。"
            )
        if len(hits) > 1:
            ids = ", ".join("{}({})".format(h["noteId"], h["title"]) for h in hits)
            die(
                f"发现多个 #knowledgeRoot：{ids}\n"
                "请在 etc/config.json 用 knowledgeRootId 指定。"
            )
        return hits[0]["noteId"]

    def ensure_type_path(self, type_key: str) -> str:
        """Find-or-create `Knowledge/<Type>/`; return its noteId."""
        if type_key not in TYPE_DISPLAY_NAMES:
            die(f"未知的知识笔记类型: {type_key!r}（应为 til/idea/ref）")
        root_id = self.knowledge_root()
        found = self._child_with_label(root_id, "typeNote", type_key)
        if found:
            return found
        title = TYPE_DISPLAY_NAMES[type_key]
        nid = self.create_note(root_id, title, "")["note"]["noteId"]
        self.add_label(nid, "typeNote", type_key)
        self.add_label(nid, "iconClass", TYPE_DEFAULT_ICONS[type_key])
        return nid

    def ensure_topic_path(self, type_key: str, topic: str) -> str:
        """Find-or-create `Knowledge/<Type>/<Topic>/`; return its noteId."""
        if not topic or not topic.strip():
            die("主题名不能为空")
        topic = topic.strip()
        type_node = self.ensure_type_path(type_key)
        key = f"{type_key}:{topic}"
        found = self._child_with_label(type_node, "topicNote", key)
        if found:
            return found
        nid = self.create_note(type_node, topic, "")["note"]["noteId"]
        self.add_label(nid, "topicNote", key)
        self.add_label(nid, "iconClass", TOPIC_FOLDER_ICON)
        return nid

    def clone_note(self, note_id: str, parent_id: str) -> dict:
        """Attach note_id as an additional child of parent_id (idempotent).

        Uses ETAPI POST /branches. Returns a structured result; never dies.
        """
        try:
            note = self.get_note(note_id)
        except SystemExit as e:
            return {"cloned": False, "alreadyPresent": False, "error": str(e)}
        if parent_id in (note.get("parentNoteIds") or []):
            return {"cloned": True, "alreadyPresent": True, "error": None}
        try:
            self._req(
                "POST",
                "/branches",
                json={"noteId": note_id, "parentNoteId": parent_id},
            )
        except SystemExit as e:
            return {"cloned": False, "alreadyPresent": False, "error": str(e)}
        return {"cloned": True, "alreadyPresent": False, "error": None}

    def find_branch(self, note_id: str, parent_id: str) -> str | None:
        """Return the branchId connecting note_id to parent_id, or None."""
        note = self.get_note(note_id)
        branch_ids = note.get("parentBranchIds") or []
        parent_ids = note.get("parentNoteIds") or []
        for bid, pid in zip(branch_ids, parent_ids):
            if pid == parent_id:
                return bid
        return None

    def delete_branch(self, branch_id: str):
        return self._req("DELETE", f"/branches/{branch_id}")

    def create_branch(self, note_id: str, parent_id: str):
        return self._req(
            "POST",
            "/branches",
            json={"noteId": note_id, "parentNoteId": parent_id},
        ).json()

    def _child_with_label(self, parent_id, label, value):
        """Find a direct child of parent_id carrying #label=value (calendar key)."""
        expr = f'note.parents.noteId="{parent_id}" #{label}="{value}"'
        for n in self.search(expr, limit="30"):
            if parent_id in (n.get("parentNoteIds") or []) and any(
                a["name"] == label and a["value"] == value
                for a in n.get("attributes", [])
            ):
                return n["noteId"]
        return None

    def find_session_note(self, day_id: str, session_id: str) -> str | None:
        """Find an existing recap note for the given session under day_id."""
        expr = f'note.parents.noteId="{day_id}" #sessionId="{session_id}"'
        for n in self.search(expr, limit="5"):
            if day_id not in (n.get("parentNoteIds") or []):
                continue
            attrs = n.get("attributes", []) or []
            if any(
                a["name"] == "sessionId" and a["value"] == session_id
                for a in attrs
            ):
                return n["noteId"]
        return None

    def ensure_year(self, root_id, date):
        val = f"{date.year:04d}"
        found = self._child_with_label(root_id, "yearNote", val)
        if found:
            return found
        nid = self.create_note(root_id, val, "")["note"]["noteId"]
        self.add_label(nid, "yearNote", val)
        return nid

    def ensure_month(self, year_id, date):
        val = f"{date.year:04d}-{date.month:02d}"
        found = self._child_with_label(year_id, "monthNote", val)
        if found:
            return found
        title = f"{date.month:02d} - {MONTH_EN[date.month]}"
        nid = self.create_note(year_id, title, "")["note"]["noteId"]
        self.add_label(nid, "monthNote", val)
        return nid

    def ensure_day(self, month_id, date):
        val = date.isoformat()
        found = self._child_with_label(month_id, "dateNote", val)
        if found:
            return found
        title = f"{date.day:02d} - {WEEKDAY_ZH[date.weekday()]}"
        nid = self.create_note(month_id, title, "")["note"]["noteId"]
        self.add_label(nid, "dateNote", val)
        return nid

    def ensure_date_path(self, date):
        """Find-or-create year/month/day; return the day note id.

        Uses ETAPI calendar day endpoint when calendarRootId is configured,
        falls back to manual label-based navigation otherwise.
        """
        root_id = self.cfg.get("calendarRootId")
        if root_id:
            # Use ETAPI's built-in calendar endpoint for direct day note access
            return self._req("GET", f"/calendar/days/{date.isoformat()}").json()[
                "noteId"
            ]
        year = self.ensure_year(self.calendar_root(), date)
        month = self.ensure_month(year, date)
        return self.ensure_day(month, date)


def render_markdown(text):
    return markdown.markdown(
        text, extensions=MD_EXTENSIONS, extension_configs=MD_EXTENSION_CONFIGS
    )


def parse_date(s):
    if not s:
        return _dt.date.today()
    try:
        return _dt.datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        die(f"日期格式应为 YYYY-MM-DD，收到: {s}")


def _get_attr(note, name):
    """Return the first attribute dict matching name, or None."""
    return next((a for a in note.get("attributes", []) if a["name"] == name), None)


def _get_attr_value(note, name, default=""):
    """Return the value of the first attribute matching name."""
    attr = _get_attr(note, name)
    return attr["value"] if attr else default


# ---- commands ---------------------------------------------------------------


def cmd_check(args):
    cfg = load_config()
    t = Trilium(cfg)
    info = t.app_info()
    print("✓ Trilium 可达: {} (v{})".format(cfg["server"], info.get("appVersion")))
    print("✓ token 有效")

    cal = t.calendar_root()
    cal_note = t.get_note(cal)
    cal_ok = any(a["name"] == "calendarRoot" for a in cal_note.get("attributes", []))
    tag = "#calendarRoot 标签存在" if cal_ok else "⚠ 缺少 #calendarRoot 标签"
    print(f"✓ 日历根 = {cal}（{tag}）")

    know = t.knowledge_root()
    know_note = t.get_note(know)
    know_ok = any(
        a["name"] == "knowledgeRoot" for a in know_note.get("attributes", [])
    )
    tag = "#knowledgeRoot 标签存在" if know_ok else "⚠ 缺少 #knowledgeRoot 标签"
    print(f"✓ 知识根 = {know}（{tag}）")

    for type_key in ("til", "idea", "ref"):
        hits = t.search(f'#typeNote="{type_key}"', limit="5")
        display = TYPE_DISPLAY_NAMES[type_key]
        status = "存在" if hits else "首次写入时自动建"
        print(f"i {display} 类型节点：{status}")


def cmd_list(args):
    cfg = load_config()
    t = Trilium(cfg)

    parts = ["#knowledge"]
    if args.type:
        parts.append(f'#type="{args.type}"')
    if args.topic:
        parts.append(f'#topic="{args.topic}"')
    if args.note_date:
        parts.append(f'#noteDate="{args.note_date}"')
    if args.source_session:
        parts.append(f'#sourceSession="{args.source_session}"')
    expr = " ".join(parts)

    rows = t.search(
        expr,
        orderBy="dateCreated",
        orderDirection="desc",
        limit=str(args.limit),
    )
    items = []
    for n in rows:
        attrs = {a["name"]: a["value"] for a in n.get("attributes", [])}
        items.append({
            "noteId": n.get("noteId"),
            "title": n.get("title"),
            "type": attrs.get("type", ""),
            "topic": attrs.get("topic", ""),
            "noteDate": attrs.get("noteDate", ""),
            "sourceSession": attrs.get("sourceSession", ""),
        })
    print(json.dumps({"items": items}, ensure_ascii=False))


def cmd_delete(args):
    cfg = load_config()
    t = Trilium(cfg)
    t.delete_note(args.note_id)
    print(json.dumps(
        {"noteId": args.note_id, "ok": True}, ensure_ascii=False
    ))


def cmd_get(args):
    cfg = load_config()
    t = Trilium(cfg)
    note = t.get_note(args.note_id)
    attrs = {a["name"]: a["value"] for a in note.get("attributes", [])}
    out = {
        "noteId": note.get("noteId", args.note_id),
        "title": note.get("title", ""),
        "type": attrs.get("type", ""),
        "topic": attrs.get("topic", ""),
        "noteDate": attrs.get("noteDate", ""),
        "sourceSession": attrs.get("sourceSession", ""),
        "iconClass": attrs.get("iconClass", ""),
        "url": _note_url(cfg, args.note_id),
    }
    if args.content:
        out["content"] = t.get_note_content(args.note_id)
    print(json.dumps(out, ensure_ascii=False))


def cmd_update(args):
    cfg = load_config()
    t = Trilium(cfg)

    if args.title is not None:
        t.update_note(args.note_id, title=args.title)

    if not sys.stdin.isatty():
        md = sys.stdin.read()
        if md.strip():
            html = render_markdown(md)
            t.update_note_content(args.note_id, html)

    if args.icon:
        note = t.get_note(args.note_id)
        existing = next(
            (a for a in note.get("attributes", []) if a["name"] == "iconClass"),
            None,
        )
        if existing:
            t.patch_attribute(existing["attributeId"], value=args.icon)
        else:
            t.add_label(args.note_id, "iconClass", args.icon)

    print(json.dumps(
        {"noteId": args.note_id, "ok": True}, ensure_ascii=False
    ))


def _note_url(cfg, note_id: str) -> str:
    return "{}/#root/{}".format(cfg["server"], note_id)


def _read_stdin_markdown() -> str:
    md = sys.stdin.read()
    if not md or not md.strip():
        die("正文为空，请从 stdin 传入 markdown")
    return md


def _cmd_note_write(args, type_key: str) -> None:
    cfg = load_config()
    t = Trilium(cfg)

    md = _read_stdin_markdown()
    html = render_markdown(md)

    topic_id = t.ensure_topic_path(type_key, args.topic)
    nid = t.create_note(topic_id, args.title, html, ntype="text")["note"]["noteId"]

    icon = args.icon if args.icon else TYPE_DEFAULT_ICONS[type_key]
    t.add_label(nid, "knowledge", "")
    t.add_label(nid, "type", type_key)
    t.add_label(nid, "topic", args.topic)
    t.add_label(nid, "sourceSession", args.source_session)
    t.add_label(nid, "noteDate", args.note_date)
    t.add_label(nid, "iconClass", icon)
    if type_key == "ref":
        t.add_label(nid, "url", args.url)

    date = parse_date(args.note_date)
    day_id = t.ensure_date_path(date)
    clone = t.clone_note(nid, day_id)

    out: dict = {
        "noteId": nid,
        "url": _note_url(cfg, nid),
        "cloned": clone["cloned"],
    }
    if not clone["cloned"] and clone.get("error"):
        out["cloneError"] = clone["error"]
        print(
            "clone 到日历失败：{}".format(clone["error"]),
            file=sys.stderr,
        )
    print(json.dumps(out, ensure_ascii=False))


def cmd_note_til(args) -> None:
    _cmd_note_write(args, "til")


def cmd_note_idea(args) -> None:
    _cmd_note_write(args, "idea")


def cmd_note_ref(args) -> None:
    if not getattr(args, "url", None):
        die("note ref 必须提供 --url")
    _cmd_note_write(args, "ref")


def cmd_note_topics(args):
    cfg = load_config()
    t = Trilium(cfg)
    hits = t.search("#topicNote", limit="1000")
    topics = []
    for n in hits:
        key = next(
            (a["value"] for a in n.get("attributes", []) if a["name"] == "topicNote"),
            "",
        )
        if ":" not in key:
            continue
        type_key, topic = key.split(":", 1)
        cnt_hits = t.search(
            f'#knowledge #type="{type_key}" #topic="{topic}"',
            limit="1000",
        )
        topics.append({
            "type": type_key,
            "topic": topic,
            "noteId": n.get("noteId"),
            "count": len(cnt_hits),
        })
    print(json.dumps({"topics": topics}, ensure_ascii=False))


def cmd_note_merge_topic(args):
    cfg = load_config()
    t = Trilium(cfg)

    if args.type not in TYPE_DISPLAY_NAMES:
        die(f"未知的知识笔记类型: {args.type!r}（应为 til/idea/ref）")
    if args.from_topic == args.to_topic:
        die("源主题与目标主题相同")

    src_notes = t.search(
        f'#knowledge #type="{args.type}" #topic="{args.from_topic}"',
        limit="1000",
    )
    src_topic_hits = t.search(
        f'#topicNote="{args.type}:{args.from_topic}"',
        limit="5",
    )
    src_topic_id = src_topic_hits[0]["noteId"] if src_topic_hits else None

    dst_topic_id = t.ensure_topic_path(args.type, args.to_topic)

    moved = 0
    for n in src_notes:
        topic_attr = next(
            (a for a in n.get("attributes", []) if a["name"] == "topic"),
            None,
        )
        if topic_attr:
            t.patch_attribute(topic_attr["attributeId"], value=args.to_topic)
        if src_topic_id:
            bid = t.find_branch(n["noteId"], src_topic_id)
            if bid:
                t.delete_branch(bid)
        t.create_branch(n["noteId"], dst_topic_id)
        moved += 1

    from_empty = False
    if src_topic_id:
        remaining = t.search(
            f'#knowledge #type="{args.type}" #topic="{args.from_topic}"',
            limit="1",
        )
        if not remaining:
            t.delete_note(src_topic_id)
            from_empty = True

    print(json.dumps({
        "moved": moved,
        "fromNoteId": src_topic_id or "",
        "toNoteId": dst_topic_id,
        "fromEmpty": from_empty,
    }, ensure_ascii=False))


def cmd_recap(args):
    from jsonl_render import EmptyTranscriptError, render_jsonl

    cfg = load_config()
    t = Trilium(cfg)

    jsonl_path, session_id = resolve_jsonl_path(
        getattr(args, "session", None), getattr(args, "project_dir", None)
    )
    if not os.path.exists(jsonl_path):
        die(f"找不到 session JSONL: {jsonl_path}")

    try:
        md = render_jsonl(jsonl_path)
    except EmptyTranscriptError:
        die(f"session JSONL 没有可渲染内容: {jsonl_path}")

    date = parse_date(getattr(args, "date", None))
    day_id = t.ensure_date_path(date)

    suffix = getattr(args, "title_suffix", None)
    title = f"Recap：{suffix}" if suffix else "Recap"

    html = render_markdown(md)

    existing = t.find_session_note(day_id, session_id)
    if existing:
        t.update_note_content(existing, html)
        cur = t.get_note(existing)
        if cur.get("title") != title:
            t.update_note(existing, title=title)
        nid = existing
        action = "已更新"
    else:
        nid = t.create_note(day_id, title, html, ntype="text")["note"]["noteId"]
        t.add_label(nid, "diary")
        t.add_label(nid, "sessionId", session_id)
        t.add_label(nid, "diaryDate", date.isoformat())
        t.add_label(nid, "iconClass", RECAP_ICON)
        action = "已创建"

    print(f"✓ {action}: {title}")
    print(f"  noteId: {nid}")
    url = "{}/#root/{}".format(cfg["server"], nid)
    print(f"  打开: {url}")


def build_parser():
    p = argparse.ArgumentParser(
        prog="trilium.py", description="把工作日记写入 Trilium 日历"
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {_get_version()}")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("check", help="检查服务器、token、日历根")

    pl = sub.add_parser("list", help="列出日记条目")
    pl.add_argument("--date", help="只列某天 YYYY-MM-DD")
    pl.add_argument("--limit", type=int, default=50, help="最多条数，默认 50")
    pl.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="输出格式，默认 text",
    )

    pd = sub.add_parser("delete", help="删除一条日记条目")
    pd.add_argument("note_id", help="要删除的笔记 ID")

    pg = sub.add_parser("get", help="查看一条日记的详情")
    pg.add_argument("note_id", help="笔记 ID")
    pg.add_argument("--content", action="store_true", help="同时显示笔记内容")

    pu = sub.add_parser("update", help="修改一条日记")
    pu.add_argument("note_id", help="笔记 ID")
    pu.add_argument("--title", help="新标题")
    pu.add_argument("--icon", help="新图标 (iconClass 值)")

    pr = sub.add_parser("recap", help="把当前 session JSONL 渲染并写入日历")
    pr.add_argument("--title-suffix", help="标题后缀（Recap：<suffix>）")
    pr.add_argument("--session", help="覆盖 sessionId，默认读 $CLAUDE_CODE_SESSION_ID")
    pr.add_argument("--project-dir", help="覆盖项目目录，默认 $PWD")
    pr.add_argument("--date", help="覆盖日期 YYYY-MM-DD，默认今天")

    return p


def main():
    args = build_parser().parse_args()
    {
        "check": cmd_check,
        "list": cmd_list,
        "delete": cmd_delete,
        "get": cmd_get,
        "update": cmd_update,
        "recap": cmd_recap,
    }[args.cmd](args)


if __name__ == "__main__":
    main()
