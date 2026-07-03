"""Tests for cmd_check (v3)."""

import json
import os
import sys
from argparse import Namespace
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from trilium import cmd_check


def _make_config(tmp_path):
    cfg = {
        "server": "http://localhost:8080",
        "token": "t",
        "calendarRootId": "cal",
        "knowledgeRootId": "know",
    }
    p = tmp_path / "etc" / "config.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg), encoding="utf-8")
    return str(p)


class TestCheck:
    def test_check_all_good_reports_both_roots_and_types(
        self, tmp_path, capsys, monkeypatch
    ):
        monkeypatch.setattr("trilium.CONFIG_PATH", _make_config(tmp_path))
        with patch("trilium.Trilium") as TClass:
            t = TClass.return_value
            t.app_info.return_value = {"appVersion": "0.99.0"}
            t.calendar_root.return_value = "cal"
            t.knowledge_root.return_value = "know"

            def _get(nid):
                if nid == "cal":
                    return {"attributes": [{"name": "calendarRoot"}]}
                if nid == "know":
                    return {"attributes": [{"name": "knowledgeRoot"}]}
                return {"attributes": []}

            t.get_note.side_effect = _get
            # type node search results: TIL exists, Ideas missing, Reference exists
            def _search(expr, **_):
                if 'typeNote="til"' in expr:
                    return [{"noteId": "tilN"}]
                if 'typeNote="idea"' in expr:
                    return []
                if 'typeNote="ref"' in expr:
                    return [{"noteId": "refN"}]
                return []
            t.search.side_effect = _search

            cmd_check(Namespace())

        out = capsys.readouterr().out
        assert "Trilium 可达: http://localhost:8080 (v0.99.0)" in out
        assert "token 有效" in out
        assert "日历根 = cal" in out
        assert "#calendarRoot 标签存在" in out
        assert "知识根 = know" in out
        assert "#knowledgeRoot 标签存在" in out
        assert "TIL 类型节点" in out and "存在" in out.split("TIL")[1].splitlines()[0]
        assert "Ideas 类型节点" in out
        assert "首次写入时自动建" in out
        assert "References 类型节点" in out
