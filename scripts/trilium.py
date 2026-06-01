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
               └─ 标题  #iconClass="bx bx-bug-alt"     (entry, child of day note)

Year/month/day nodes are found-or-created by their calendar labels (idempotent),
so they match what Trilium itself recognizes. Entries are plain child notes of
the date note (no #startDate — that would render as a pinned all-day event bar
above the day title). Entries carry #diary / #diaryType / #diaryDate for filtering.

Markdown is rendered to HTML locally (Trilium text notes store HTML; the internal
render-markdown endpoint rejects ETAPI tokens). Deps managed by uv.

Commands:
    check                       verify server + token, locate the calendar root
    add --type T --title S      create an entry (content from --content-file/stdin)
    get NOTE_ID                 show entry details (--content for full content)
    update NOTE_ID [--title ..] modify entry title/type/content
    delete NOTE_ID              delete an entry by note id
    list [--date YYYY-MM-DD]    list diary entries

Run directly (uv resolves deps):  ./trilium.py check
"""

import argparse
import datetime as _dt
import json
import os
import subprocess
import sys
import tempfile

import markdown
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "..", "etc", "config.json")


def _get_version():
    """Read version from pyproject.toml (works with uv run and direct execution)."""
    import tomllib

    pyproject = os.path.join(HERE, "..", "pyproject.toml")
    try:
        with open(pyproject, "rb") as f:
            return tomllib.load(f)["project"]["version"]
    except (FileNotFoundError, KeyError):
        return "unknown"

# Boxicons class for each diary type, applied via #iconClass label.
# Trilium natively renders #iconClass in the note tree and calendar view.
# See https://boxicons.com/ for the full icon set.
TYPE_ICON = {
    "trap": "bx bx-bug-alt",
    "work": "bx bx-package",
    "decision": "bx bx-traffic-cone",
    "learn": "bx bx-bulb",
}

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


def resolve_icon(ntype, override):
    """Return the Boxicons class for the given type, or the override if provided."""
    if override is not None:
        # --prefix is repurposed as --icon override; keep backward compat
        return override
    return TYPE_ICON.get(ntype, "")


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
    root = t.calendar_root()
    print(f"✓ token 有效，日历根 = {root}")
    # Verify the root note actually has #calendarRoot
    root_note = t.get_note(root)
    has_calendar_root = any(
        a["name"] == "calendarRoot" for a in root_note.get("attributes", [])
    )
    if has_calendar_root:
        print("✓ 日历根笔记验证通过（#calendarRoot 标签存在）")
    else:
        print("⚠️  日历根笔记缺少 #calendarRoot 标签，日历功能可能异常")


def _read_content(content_file):
    """Read markdown content from file, stdin (pipe), or $EDITOR."""
    if content_file:
        with open(content_file, encoding="utf-8") as f:
            md = f.read()
    elif not sys.stdin.isatty():
        md = sys.stdin.read()
    else:
        # No content provided and stdin is a terminal — open $EDITOR
        editor = os.environ.get("EDITOR", os.environ.get("VISUAL", "vi"))
        fd, tmp = tempfile.mkstemp(suffix=".md")
        try:
            os.close(fd)
            subprocess.call([editor, tmp])
            with open(tmp, encoding="utf-8") as f:
                md = f.read()
        finally:
            os.unlink(tmp)
    if not md.strip():
        die("内容为空：用 --content-file 指定 md 文件，或通过 stdin 传入")
    return md


def cmd_add(args):
    cfg = load_config()
    t = Trilium(cfg)
    md = _read_content(args.content_file)

    date = parse_date(args.date)
    day_id = t.ensure_date_path(date)

    html = render_markdown(md)
    nid = t.create_note(day_id, args.title, html, ntype="text")["note"]["noteId"]
    # The entry shows in the calendar cell simply by being a child of the
    # #dateNote day note (same as Trilium's native day entries). We deliberately
    # do NOT add #startDate — that would render it as an all-day event bar
    # pinned above the day title. #diaryDate is a plain label for our own
    # filtering and does not affect calendar layout.
    t.add_label(nid, "diary")
    t.add_label(nid, "diaryType", args.type)
    t.add_label(nid, "diaryDate", date.isoformat())
    # Set Boxicons icon via #iconClass (rendered in tree & calendar by Trilium).
    icon = resolve_icon(args.type, getattr(args, "prefix", None))
    if icon:
        t.add_label(nid, "iconClass", icon)

    url = "{}/#root/{}".format(cfg["server"], nid)
    print(f"✓ 已写入日历: {args.title}")
    print(f"  日期: {date.isoformat()}（{WEEKDAY_ZH[date.weekday()]}）")
    print(f"  noteId: {nid}")
    print(f"  打开: {url}")


def cmd_list(args):
    cfg = load_config()
    t = Trilium(cfg)
    if args.date:
        date = parse_date(args.date)
        expr = f'#diary #diaryDate="{date.isoformat()}"'
    else:
        expr = "#diary"
    rows = t.search(
        expr, orderBy="dateCreated", orderDirection="desc", limit=str(args.limit)
    )
    if not rows:
        print("(没有匹配的日记条目)")
        return
    if getattr(args, "format", "text") == "json":
        items = []
        for n in rows:
            sd = next(
                (
                    a["value"]
                    for a in n.get("attributes", [])
                    if a["name"] == "diaryDate"
                ),
                "",
            )
            items.append(
                {"noteId": n.get("noteId"), "title": n.get("title"), "date": sd}
            )
        print(json.dumps(items, ensure_ascii=False, indent=2))
        return
    for n in rows:
        sd = next(
            (a["value"] for a in n.get("attributes", []) if a["name"] == "diaryDate"),
            "",
        )
        print(f"{n.get('noteId')}  {sd:<12} {n.get('title')}")


def cmd_delete(args):
    cfg = load_config()
    t = Trilium(cfg)
    note = t.get_note(args.note_id)
    # Show what will be deleted
    diary_type = next(
        (a["value"] for a in note.get("attributes", []) if a["name"] == "diaryType"),
        "",
    )
    diary_date = next(
        (a["value"] for a in note.get("attributes", []) if a["name"] == "diaryDate"),
        "",
    )
    title = note.get("title", "")
    info_parts = [f"  标题: {title}"]
    if diary_type:
        info_parts.append(f"  类型: {diary_type}")
    if diary_date:
        info_parts.append(f"  日期: {diary_date}")
    print("即将删除：")
    print("\n".join(info_parts))
    t.delete_note(args.note_id)
    print(f"✓ 已删除: {title}")


def cmd_get(args):
    cfg = load_config()
    t = Trilium(cfg)
    note = t.get_note(args.note_id)
    title = note.get("title", "")
    diary_type = _get_attr_value(note, "diaryType")
    diary_date = _get_attr_value(note, "diaryDate")

    print(f"标题: {title}")
    if diary_type:
        print(f"类型: {diary_type}")
    if diary_date:
        print(f"日期: {diary_date}")
    print(f"noteId: {note.get('noteId', '')}")
    url = "{}/#root/{}".format(cfg["server"], args.note_id)
    print(f"打开: {url}")

    if args.content:
        content = t.get_note_content(args.note_id)
        if content:
            print("---")
            print(content)


def cmd_update(args):
    cfg = load_config()
    t = Trilium(cfg)
    note = t.get_note(args.note_id)

    # Update title if --title provided
    if args.title is not None:
        t.update_note(args.note_id, title=args.title)

    # Update content if --content-file provided or stdin piped
    if args.content_file:
        with open(args.content_file, encoding="utf-8") as f:
            md = f.read()
        if not md.strip():
            die("内容为空")
        html = render_markdown(md)
        t.update_note_content(args.note_id, html)
    elif not sys.stdin.isatty():
        md = sys.stdin.read()
        if md.strip():
            html = render_markdown(md)
            t.update_note_content(args.note_id, html)

    # Update type label and icon if --type provided
    if args.type is not None:
        type_attr = _get_attr(note, "diaryType")
        if type_attr:
            t.patch_attribute(type_attr["attributeId"], value=args.type)
        # Update #iconClass to match new type
        icon = resolve_icon(args.type, getattr(args, "prefix", None))
        icon_attr = _get_attr(note, "iconClass")
        if icon_attr:
            t.patch_attribute(icon_attr["attributeId"], value=icon)
        elif icon:
            t.add_label(args.note_id, "iconClass", icon)

    # Show result
    updated = t.get_note(args.note_id)
    print(f"✓ 已更新: {updated.get('title', '')}")
    print(f"  noteId: {args.note_id}")
    url = "{}/#root/{}".format(cfg["server"], args.note_id)
    print(f"  打开: {url}")


def build_parser():
    p = argparse.ArgumentParser(
        prog="trilium.py", description="把工作日记写入 Trilium 日历"
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {_get_version()}")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("check", help="检查服务器、token、日历根")

    pa = sub.add_parser("add", help="新增一条日记条目（挂到当天日历）")
    pa.add_argument(
        "--type", required=True, help="类型: trap/work/decision/learn 或自定义"
    )
    pa.add_argument("--title", required=True, help="条目标题")
    pa.add_argument("--date", help="日期 YYYY-MM-DD，默认今天")
    pa.add_argument("--content-file", help="markdown 文件路径；省略则读 stdin")
    pa.add_argument("--prefix", help="覆盖默认图标（Boxicons class，如 bx bx-star）")

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
    pu.add_argument("--type", help="新类型: trap/work/decision/learn 或自定义")
    pu.add_argument("--content-file", help="新内容的 markdown 文件路径")
    pu.add_argument("--prefix", help="覆盖默认图标（Boxicons class）")
    return p


def main():
    args = build_parser().parse_args()
    {
        "check": cmd_check,
        "add": cmd_add,
        "list": cmd_list,
        "delete": cmd_delete,
        "get": cmd_get,
        "update": cmd_update,
    }[args.cmd](args)


if __name__ == "__main__":
    main()
