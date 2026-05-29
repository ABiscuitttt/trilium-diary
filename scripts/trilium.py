#!/usr/bin/env -S uv run --quiet
# /// script
# requires-python = ">=3.9"
# dependencies = ["markdown>=3.5", "requests>=2.31"]
# ///
"""trilium-diary: write markdown dev-diary entries into Trilium's calendar.

Targets the built-in Journal/calendar (a `book` note tagged #calendarRoot):

    Journal (#calendarRoot)
      └─ YYYY            #yearNote=YYYY
         └─ MM - Mon     #monthNote=YYYY-MM
            └─ DD - 周X   #dateNote=YYYY-MM-DD     (day note)
               └─ 🪤 · 标题                        (entry, child of day note)

Year/month/day nodes are found-or-created by their calendar labels (idempotent),
so they match what Trilium itself recognizes. Entries are plain child notes of
the date note (no #startDate — that would render as a pinned all-day event bar
above the day title). Entries carry #diary / #diaryType / #diaryDate for filtering.

Markdown is rendered to HTML locally (Trilium text notes store HTML; the internal
render-markdown endpoint rejects ETAPI tokens). Deps managed by uv.

Commands:
    check                       verify server + token, locate the calendar root
    add --type T --title S      create an entry (content from --content-file/stdin)
    list [--date YYYY-MM-DD]     list diary entries

Run directly (uv resolves deps):  ./trilium.py check
"""
import argparse
import datetime as _dt
import json
import os
import sys

import markdown
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "..", "etc", "config.json")

# Prefixes intentionally start with a emoji (NOT a bracket or CJK char). The calendar
# renders the day note and its entries as all-day events ordered by title via
# ICU collation; titles beginning with '[' / '【' sort BEFORE the digit-led day
# note ("29 - 周五") and float above it. A Emoji-led prefix sorts after the digits,
# so entries stay below the day-note title like Trilium's native entries.
# Joined to the title as "<prefix> · <title>".
TYPE_PREFIX = {
    "trap": "🪤",
    "work": "📦",
    "decision": "🚦",
    "learn": "💡",
}

WEEKDAY_ZH = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
MONTH_EN = ["", "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"]

MD_EXTENSIONS = ["fenced_code", "tables", "sane_lists", "nl2br", "codehilite"]
MD_EXTENSION_CONFIGS = {"codehilite": {"noclasses": True}}


def die(msg, code=1):
    print(msg, file=sys.stderr)
    sys.exit(code)


def load_config():
    if not os.path.exists(CONFIG_PATH):
        die("找不到配置 %s" % CONFIG_PATH)
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

    def _req(self, method, path, **kw):
        try:
            r = self.s.request(method, self.base + path, timeout=15, **kw)
        except requests.RequestException as e:
            die("连接 Trilium 失败 (%s): %s" % (self.base, e))
        if r.status_code == 401:
            die("ETAPI token 无效或已吊销 (401)。请在 Trilium -> Options -> ETAPI 重新生成。")
        if r.status_code >= 400:
            die("ETAPI %s %s -> HTTP %d\n%s" % (method, path, r.status_code, r.text[:500]))
        return r

    def app_info(self):
        return self._req("GET", "/app-info").json()

    def search(self, expr, **params):
        params["search"] = expr
        return self._req("GET", "/notes", params=params).json().get("results", [])

    def create_note(self, parent_id, title, content, ntype="text"):
        body = {"parentNoteId": parent_id, "title": title,
                "type": ntype, "content": content}
        return self._req("POST", "/create-note", json=body).json()

    def add_label(self, note_id, name, value=""):
        body = {"noteId": note_id, "type": "label", "name": name, "value": value}
        return self._req("POST", "/attributes", json=body).json()

    # ---- calendar navigation ------------------------------------------------

    def calendar_root(self):
        """Resolve the calendar root note id (config override or #calendarRoot)."""
        if self.cfg.get("calendarRootId"):
            return self.cfg["calendarRootId"]
        hits = self.search("#calendarRoot", limit="5")
        if not hits:
            die("找不到日历根（带 #calendarRoot 的笔记）。"
                "请在 etc/config.json 设置 calendarRootId，或在 Trilium 里建立日历。")
        if len(hits) > 1:
            ids = ", ".join("%s(%s)" % (h["noteId"], h["title"]) for h in hits)
            die("发现多个 #calendarRoot：%s\n请在 etc/config.json 用 calendarRootId 指定。" % ids)
        return hits[0]["noteId"]

    def _child_with_label(self, parent_id, label, value):
        """Find a direct child of parent_id carrying #label=value (calendar key)."""
        expr = 'note.parents.noteId="%s" #%s="%s"' % (parent_id, label, value)
        for n in self.search(expr, limit="30"):
            if parent_id in (n.get("parentNoteIds") or []):
                if any(a["name"] == label and a["value"] == value
                       for a in n.get("attributes", [])):
                    return n["noteId"]
        return None

    def ensure_year(self, root_id, date):
        val = "%04d" % date.year
        found = self._child_with_label(root_id, "yearNote", val)
        if found:
            return found
        nid = self.create_note(root_id, val, "")["note"]["noteId"]
        self.add_label(nid, "yearNote", val)
        return nid

    def ensure_month(self, year_id, date):
        val = "%04d-%02d" % (date.year, date.month)
        found = self._child_with_label(year_id, "monthNote", val)
        if found:
            return found
        title = "%02d - %s" % (date.month, MONTH_EN[date.month])
        nid = self.create_note(year_id, title, "")["note"]["noteId"]
        self.add_label(nid, "monthNote", val)
        return nid

    def ensure_day(self, month_id, date):
        val = date.isoformat()
        found = self._child_with_label(month_id, "dateNote", val)
        if found:
            return found
        title = "%02d - %s" % (date.day, WEEKDAY_ZH[date.weekday()])
        nid = self.create_note(month_id, title, "")["note"]["noteId"]
        self.add_label(nid, "dateNote", val)
        return nid

    def ensure_date_path(self, date):
        """Find-or-create year/month/day; return the day note id."""
        root = self.calendar_root()
        year = self.ensure_year(root, date)
        month = self.ensure_month(year, date)
        return self.ensure_day(month, date)


def render_markdown(text):
    return markdown.markdown(
        text, extensions=MD_EXTENSIONS, extension_configs=MD_EXTENSION_CONFIGS)


def resolve_prefix(ntype, override):
    return override if override is not None else TYPE_PREFIX.get(ntype, "")


def parse_date(s):
    if not s:
        return _dt.date.today()
    try:
        return _dt.datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        die("日期格式应为 YYYY-MM-DD，收到: %s" % s)


# ---- commands ---------------------------------------------------------------

def cmd_check(args):
    cfg = load_config()
    t = Trilium(cfg)
    info = t.app_info()
    print("✓ Trilium 可达: %s (v%s)" % (cfg["server"], info.get("appVersion")))
    root = t.calendar_root()
    print("✓ token 有效，日历根 = %s" % root)


def cmd_add(args):
    cfg = load_config()
    t = Trilium(cfg)

    if args.content_file:
        with open(args.content_file, encoding="utf-8") as f:
            md = f.read()
    else:
        md = sys.stdin.read()
    if not md.strip():
        die("内容为空：用 --content-file 指定 md 文件，或通过 stdin 传入")

    date = parse_date(args.date)
    day_id = t.ensure_date_path(date)

    prefix = resolve_prefix(args.type, args.prefix)
    title = ("%s · %s" % (prefix, args.title)) if prefix else args.title
    html = render_markdown(md)

    nid = t.create_note(day_id, title, html, ntype="text")["note"]["noteId"]
    # The entry shows in the calendar cell simply by being a child of the
    # #dateNote day note (same as Trilium's native day entries). We deliberately
    # do NOT add #startDate — that would render it as an all-day event bar
    # pinned above the day title. #diaryDate is a plain label for our own
    # filtering and does not affect calendar layout.
    t.add_label(nid, "diary")
    t.add_label(nid, "diaryType", args.type)
    t.add_label(nid, "diaryDate", date.isoformat())

    url = "%s/#root/%s" % (cfg["server"], nid)
    print("✓ 已写入日历: %s" % title)
    print("  日期: %s（%s）" % (date.isoformat(), WEEKDAY_ZH[date.weekday()]))
    print("  noteId: %s" % nid)
    print("  打开: %s" % url)


def cmd_list(args):
    cfg = load_config()
    t = Trilium(cfg)
    if args.date:
        date = parse_date(args.date)
        expr = '#diary #diaryDate="%s"' % date.isoformat()
    else:
        expr = "#diary"
    rows = t.search(expr, orderBy="dateCreated", orderDirection="desc",
                    limit=str(args.limit))
    if not rows:
        print("(没有匹配的日记条目)")
        return
    for n in rows:
        sd = next((a["value"] for a in n.get("attributes", [])
                   if a["name"] == "diaryDate"), "")
        print("%s  %-12s %s" % (n.get("noteId"), sd, n.get("title")))


def build_parser():
    p = argparse.ArgumentParser(prog="trilium.py", description="把工作日记写入 Trilium 日历")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("check", help="检查服务器、token、日历根")

    pa = sub.add_parser("add", help="新增一条日记条目（挂到当天日历）")
    pa.add_argument("--type", required=True, help="类型: trap/work/decision/learn 或自定义")
    pa.add_argument("--title", required=True, help="条目标题（不含类型前缀）")
    pa.add_argument("--date", help="日期 YYYY-MM-DD，默认今天")
    pa.add_argument("--content-file", help="markdown 文件路径；省略则读 stdin")
    pa.add_argument("--prefix", help="覆盖默认标题前缀（如 [复盘]）")

    pl = sub.add_parser("list", help="列出日记条目")
    pl.add_argument("--date", help="只列某天 YYYY-MM-DD")
    pl.add_argument("--limit", type=int, default=50, help="最多条数，默认 50")
    return p


def main():
    args = build_parser().parse_args()
    {"check": cmd_check, "add": cmd_add, "list": cmd_list}[args.cmd](args)


if __name__ == "__main__":
    main()
