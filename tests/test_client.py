"""Tests for Trilium client with mocked HTTP, and command-level integration tests."""

import datetime as _dt
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from trilium import (
    RECAP_ICON,
    Trilium,
    cmd_check,
    cmd_delete,
    cmd_get,
    cmd_list,
    cmd_recap,
    cmd_update,
    load_config,
    resolve_jsonl_path,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(tmp_path, **overrides):
    """Write a minimal config.json and return its path."""
    cfg = {
        "server": "http://localhost:8080",
        "token": "test-token",
        "calendarRootId": "root123",
    }
    cfg.update(overrides)
    p = tmp_path / "etc" / "config.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg), encoding="utf-8")
    return str(p)


def _mock_response(status_code=200, json_data=None, text=""):
    r = MagicMock()
    r.status_code = status_code
    r.text = text
    r.json.return_value = json_data or {}
    return r


# ---------------------------------------------------------------------------
# Trilium client unit tests (mocked HTTP)
# ---------------------------------------------------------------------------
class TestTriliumClient:
    def _client(self, cfg=None):
        if cfg is None:
            cfg = {
                "server": "http://localhost:8080",
                "token": "tok",
                "calendarRootId": "root1",
            }
        return Trilium(cfg)

    def test_calendar_root_from_config(self):
        t = self._client({"server": "http://x", "token": "t", "calendarRootId": "abc"})
        assert t.calendar_root() == "abc"

    def test_calendar_root_auto_detect_single(self):
        t = self._client({"server": "http://x", "token": "t", "calendarRootId": ""})
        with patch.object(
            t, "search", return_value=[{"noteId": "cal1", "title": "Journal"}]
        ):
            assert t.calendar_root() == "cal1"

    def test_calendar_root_auto_detect_none_exits(self):
        t = self._client({"server": "http://x", "token": "t", "calendarRootId": ""})
        with patch.object(t, "search", return_value=[]), pytest.raises(SystemExit):
            t.calendar_root()

    def test_calendar_root_auto_detect_multiple_exits(self):
        t = self._client({"server": "http://x", "token": "t", "calendarRootId": ""})
        with (
            patch.object(
                t,
                "search",
                return_value=[
                    {"noteId": "a", "title": "J1"},
                    {"noteId": "b", "title": "J2"},
                ],
            ),
            pytest.raises(SystemExit),
        ):
            t.calendar_root()

    def test_ensure_year_existing(self):
        t = self._client()
        with patch.object(t, "_child_with_label", return_value="y2026"):
            assert t.ensure_year("root", _dt.date(2026, 6, 1)) == "y2026"

    def test_ensure_year_creates(self):
        t = self._client()
        with (
            patch.object(t, "_child_with_label", return_value=None),
            patch.object(
                t, "create_note", return_value={"note": {"noteId": "new2026"}}
            ),
            patch.object(t, "add_label"),
        ):
            assert t.ensure_year("root", _dt.date(2026, 6, 1)) == "new2026"

    def test_ensure_month_existing(self):
        t = self._client()
        with patch.object(t, "_child_with_label", return_value="m05"):
            assert t.ensure_month("y2026", _dt.date(2026, 5, 15)) == "m05"

    def test_ensure_month_creates(self):
        t = self._client()
        with (
            patch.object(t, "_child_with_label", return_value=None),
            patch.object(t, "create_note", return_value={"note": {"noteId": "new05"}}),
            patch.object(t, "add_label"),
        ):
            assert t.ensure_month("y2026", _dt.date(2026, 5, 15)) == "new05"

    def test_ensure_day_existing(self):
        t = self._client()
        with patch.object(t, "_child_with_label", return_value="d15"):
            assert t.ensure_day("m05", _dt.date(2026, 5, 15)) == "d15"

    def test_ensure_day_creates(self):
        t = self._client()
        with (
            patch.object(t, "_child_with_label", return_value=None),
            patch.object(t, "create_note", return_value={"note": {"noteId": "new15"}}),
            patch.object(t, "add_label"),
        ):
            assert t.ensure_day("m05", _dt.date(2026, 5, 15)) == "new15"

    def test_ensure_date_path_chains(self):
        """ensure_date_path uses manual chain when no calendarRootId."""
        cfg = {"server": "http://localhost:8080", "token": "test-token"}
        t = Trilium(cfg)
        with (
            patch.object(t, "calendar_root", return_value="r"),
            patch.object(t, "ensure_year", return_value="y"),
            patch.object(t, "ensure_month", return_value="m"),
            patch.object(t, "ensure_day", return_value="d"),
        ):
            assert t.ensure_date_path(_dt.date(2026, 6, 1)) == "d"

    def test_ensure_date_path_calendar_api(self):
        """ensure_date_path uses ETAPI calendar endpoint
        when calendarRootId is configured.
        """
        cfg = {
            "server": "http://localhost:8080",
            "token": "test-token",
            "calendarRootId": "calRoot123",
        }
        t = Trilium(cfg)
        with patch.object(t, "_req") as mock_req:
            mock_req.return_value.json.return_value = {"noteId": "day123"}
            assert t.ensure_date_path(_dt.date(2026, 6, 1)) == "day123"
            mock_req.assert_called_once_with("GET", "/calendar/days/2026-06-01")

    def test__req_401_exits(self):
        t = self._client()
        with (
            patch.object(t.s, "request", return_value=_mock_response(401)),
            pytest.raises(SystemExit),
        ):
            t._req("GET", "/test")

    def test__req_500_exits(self):
        t = self._client()
        with (
            patch.object(t.s, "request", return_value=_mock_response(500, text="err")),
            pytest.raises(SystemExit),
        ):
            t._req("GET", "/test")

    def test__req_connection_error_exits(self):
        import requests as _req

        t = self._client()
        with (
            patch.object(t.s, "request", side_effect=_req.ConnectionError("fail")),
            pytest.raises(SystemExit),
        ):
            t._req("GET", "/test")

    def test_get_note(self):
        t = self._client()
        with patch.object(
            t,
            "_req",
            return_value=MagicMock(json=lambda: {"noteId": "n1", "title": "T"}),
        ):
            result = t.get_note("n1")
            assert result["noteId"] == "n1"

    def test_delete_note(self):
        t = self._client()
        with patch.object(t, "_req", return_value=MagicMock()):
            t.delete_note("n1")
            t._req.assert_called_with("DELETE", "/notes/n1")

    def test_get_note_content(self):
        t = self._client()
        mock_resp = MagicMock()
        mock_resp.text = "<p>hello</p>"
        with patch.object(t, "_req", return_value=mock_resp):
            content = t.get_note_content("n1")
            assert content == "<p>hello</p>"
            t._req.assert_called_with("GET", "/notes/n1/content")

    def test_update_note_content(self):
        t = self._client()
        with patch.object(t, "_req", return_value=MagicMock()):
            t.update_note_content("n1", "<p>new</p>")
            t._req.assert_called_once()
            call_args = t._req.call_args
            assert call_args[0] == ("PUT", "/notes/n1/content")

    def test_update_note(self):
        t = self._client()
        with patch.object(
            t, "_req", return_value=MagicMock(json=lambda: {"noteId": "n1"})
        ):
            t.update_note("n1", title="new title")
            t._req.assert_called_with("PATCH", "/notes/n1", json={"title": "new title"})

    def test_patch_attribute(self):
        t = self._client()
        with patch.object(
            t, "_req", return_value=MagicMock(json=lambda: {"attributeId": "a1"})
        ):
            t.patch_attribute("a1", value="newval")
            t._req.assert_called_with(
                "PATCH", "/attributes/a1", json={"value": "newval"}
            )

    def test_delete_attribute(self):
        t = self._client()
        with patch.object(t, "_req", return_value=MagicMock()):
            t.delete_attribute("a1")
            t._req.assert_called_with("DELETE", "/attributes/a1")


# ---------------------------------------------------------------------------
# Command-level integration tests (mocked Trilium + config)
# ---------------------------------------------------------------------------
class TestCmdCheck:
    def test_check_success(self, tmp_path, capsys):
        config_path = _make_config(tmp_path)
        with (
            patch("trilium.CONFIG_PATH", config_path),
            patch("trilium.Trilium") as MockTril,
        ):
            inst = MockTril.return_value
            inst.app_info.return_value = {"appVersion": "0.63.0"}
            inst.calendar_root.return_value = "abc"
            args = MagicMock(cmd="check")
            cmd_check(args)
            out = capsys.readouterr().out
            assert "✓" in out
            assert "0.63.0" in out


class TestCmdList:
    def test_list_with_results(self, tmp_path, capsys):
        config_path = _make_config(tmp_path)
        with (
            patch("trilium.CONFIG_PATH", config_path),
            patch("trilium.Trilium") as MockTril,
        ):
            inst = MockTril.return_value
            inst.search.return_value = [
                {
                    "noteId": "n1",
                    "title": "🪤 · bug",
                    "attributes": [{"name": "diaryDate", "value": "2026-06-01"}],
                },
            ]
            args = MagicMock(cmd="list", date="2026-06-01", limit=50)
            cmd_list(args)
            out = capsys.readouterr().out
            assert "🪤 · bug" in out
            assert "2026-06-01" in out

    def test_list_empty(self, tmp_path, capsys):
        config_path = _make_config(tmp_path)
        with (
            patch("trilium.CONFIG_PATH", config_path),
            patch("trilium.Trilium") as MockTril,
        ):
            inst = MockTril.return_value
            inst.search.return_value = []
            args = MagicMock(cmd="list", date=None, limit=50)
            cmd_list(args)
            out = capsys.readouterr().out
            assert "没有" in out


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------
class TestLoadConfig:
    def test_missing_config_exits(self):
        with (
            patch("trilium.CONFIG_PATH", "/nonexistent/path.json"),
            pytest.raises(SystemExit),
        ):
            load_config()

    def test_loads_valid_config(self, tmp_path):
        cfg = {"server": "http://myserver", "token": "abc", "calendarRootId": "id1"}
        p = tmp_path / "config.json"
        p.write_text(json.dumps(cfg), encoding="utf-8")

        with patch("trilium.CONFIG_PATH", str(p)):
            result = load_config()
        assert result["server"] == "http://myserver"
        assert result["token"] == "abc"
        assert result["calendarRootId"] == "id1"

    def test_missing_token_exits(self, tmp_path):
        cfg = {"server": "http://x"}
        p = tmp_path / "config.json"
        p.write_text(json.dumps(cfg), encoding="utf-8")

        with patch("trilium.CONFIG_PATH", str(p)), pytest.raises(SystemExit):
            load_config()

    def test_server_trailing_slash_stripped(self, tmp_path):
        cfg = {"server": "http://x/", "token": "t"}
        p = tmp_path / "config.json"
        p.write_text(json.dumps(cfg), encoding="utf-8")

        with patch("trilium.CONFIG_PATH", str(p)):
            result = load_config()
        assert result["server"] == "http://x"

    def test_default_server_and_calendar_root(self, tmp_path):
        cfg = {"token": "t"}
        p = tmp_path / "config.json"
        p.write_text(json.dumps(cfg), encoding="utf-8")

        with patch("trilium.CONFIG_PATH", str(p)):
            result = load_config()
        assert result["server"] == "http://trilium.localhost"
        assert result["calendarRootId"] == ""


class TestCmdDelete:
    def test_delete_success(self, tmp_path, capsys):
        config_path = _make_config(tmp_path)
        with (
            patch("trilium.CONFIG_PATH", config_path),
            patch("trilium.Trilium") as MockTril,
        ):
            inst = MockTril.return_value
            inst.get_note.return_value = {
                "noteId": "abc123",
                "title": "🪤 · some bug",
                "attributes": [
                    {"name": "diaryType", "value": "trap"},
                    {"name": "diaryDate", "value": "2026-06-01"},
                ],
            }
            inst.delete_note.return_value = MagicMock()

            args = MagicMock(cmd="delete", note_id="abc123")
            cmd_delete(args)
            out = capsys.readouterr().out
            assert "🪤 · some bug" in out
            assert "trap" in out
            assert "2026-06-01" in out
            assert "✓ 已删除" in out
            inst.delete_note.assert_called_once_with("abc123")

    def test_delete_no_diary_labels(self, tmp_path, capsys):
        """Delete a note without diary labels still works."""
        config_path = _make_config(tmp_path)
        with (
            patch("trilium.CONFIG_PATH", config_path),
            patch("trilium.Trilium") as MockTril,
        ):
            inst = MockTril.return_value
            inst.get_note.return_value = {
                "noteId": "xyz",
                "title": "plain note",
                "attributes": [],
            }
            inst.delete_note.return_value = MagicMock()

            args = MagicMock(cmd="delete", note_id="xyz")
            cmd_delete(args)
            out = capsys.readouterr().out
            assert "plain note" in out
            assert "✓ 已删除" in out


class TestCmdGet:
    def test_get_shows_metadata(self, tmp_path, capsys):
        config_path = _make_config(tmp_path)
        with (
            patch("trilium.CONFIG_PATH", config_path),
            patch("trilium.Trilium") as MockTril,
        ):
            inst = MockTril.return_value
            inst.get_note.return_value = {
                "noteId": "n1",
                "title": "🪤 · bug fix",
                "attributes": [
                    {"name": "diaryType", "value": "trap"},
                    {"name": "diaryDate", "value": "2026-06-01"},
                ],
            }

            args = MagicMock(note_id="n1", content=False)
            cmd_get(args)
            out = capsys.readouterr().out
            assert "🪤 · bug fix" in out
            assert "trap" in out
            assert "2026-06-01" in out
            assert "n1" in out
            # content not fetched without --content
            inst.get_note_content.assert_not_called()

    def test_get_with_content(self, tmp_path, capsys):
        config_path = _make_config(tmp_path)
        with (
            patch("trilium.CONFIG_PATH", config_path),
            patch("trilium.Trilium") as MockTril,
        ):
            inst = MockTril.return_value
            inst.get_note.return_value = {
                "noteId": "n1",
                "title": "📦 · release",
                "attributes": [
                    {"name": "diaryType", "value": "work"},
                    {"name": "diaryDate", "value": "2026-05-28"},
                ],
            }
            inst.get_note_content.return_value = "<p>release notes</p>"

            args = MagicMock(note_id="n1", content=True)
            cmd_get(args)
            out = capsys.readouterr().out
            assert "---" in out
            assert "release notes" in out
            inst.get_note_content.assert_called_once_with("n1")

    def test_get_no_diary_labels(self, tmp_path, capsys):
        config_path = _make_config(tmp_path)
        with (
            patch("trilium.CONFIG_PATH", config_path),
            patch("trilium.Trilium") as MockTril,
        ):
            inst = MockTril.return_value
            inst.get_note.return_value = {
                "noteId": "n2",
                "title": "plain note",
                "attributes": [],
            }

            args = MagicMock(note_id="n2", content=False)
            cmd_get(args)
            out = capsys.readouterr().out
            assert "plain note" in out
            assert "n2" in out


class TestCmdUpdate:
    def test_update_title(self, tmp_path, capsys):
        config_path = _make_config(tmp_path)
        with (
            patch("trilium.CONFIG_PATH", config_path),
            patch("trilium.Trilium") as MockTril,
            patch("sys.stdin.isatty", return_value=True),
        ):
            inst = MockTril.return_value
            inst.get_note.return_value = {
                "noteId": "n1",
                "title": "old bug",
                "attributes": [
                    {"name": "diaryType", "value": "trap", "attributeId": "at1"},
                    {"name": "diaryDate", "value": "2026-06-01"},
                ],
            }

            args = MagicMock(note_id="n1", title="new bug", content_file=None)
            cmd_update(args)
            out = capsys.readouterr().out
            assert "✓ 已更新" in out
            inst.update_note.assert_called_with("n1", title="new bug")

    def test_update_content(self, tmp_path, capsys):
        config_path = _make_config(tmp_path)
        content_file = tmp_path / "new.md"
        content_file.write_text("## Updated\nnew content", encoding="utf-8")

        with (
            patch("trilium.CONFIG_PATH", config_path),
            patch("trilium.Trilium") as MockTril,
        ):
            inst = MockTril.return_value
            inst.get_note.return_value = {
                "noteId": "n1",
                "title": "bug",
                "attributes": [],
            }

            args = MagicMock(
                note_id="n1",
                title=None,
                content_file=str(content_file),
            )
            cmd_update(args)
            inst.update_note_content.assert_called_once()
            call_content = inst.update_note_content.call_args[0][1]
            assert "Updated" in call_content

    def test_update_content_empty_exits(self, tmp_path):
        config_path = _make_config(tmp_path)
        content_file = tmp_path / "empty.md"
        content_file.write_text("   ", encoding="utf-8")

        with (
            patch("trilium.CONFIG_PATH", config_path),
            patch("trilium.Trilium") as MockTril,
        ):
            inst = MockTril.return_value
            inst.get_note.return_value = {
                "noteId": "n1",
                "title": "t",
                "attributes": [],
            }

            args = MagicMock(
                note_id="n1",
                title=None,
                content_file=str(content_file),
            )
            with pytest.raises(SystemExit):
                cmd_update(args)

    def test_update_nothing(self, tmp_path, capsys):
        """update with no flags still shows the note info."""
        config_path = _make_config(tmp_path)
        with (
            patch("trilium.CONFIG_PATH", config_path),
            patch("trilium.Trilium") as MockTril,
            patch("sys.stdin.isatty", return_value=True),
        ):
            inst = MockTril.return_value
            inst.get_note.return_value = {
                "noteId": "n1",
                "title": "bug",
                "attributes": [],
            }

            args = MagicMock(note_id="n1", title=None, content_file=None)
            cmd_update(args)
            out = capsys.readouterr().out
            assert "✓ 已更新" in out
            inst.update_note.assert_not_called()

    def test_update_stdin_content(self, tmp_path, capsys):
        """update reads content from stdin when no content-file and stdin is piped."""
        config_path = _make_config(tmp_path)
        with (
            patch("trilium.CONFIG_PATH", config_path),
            patch("trilium.Trilium") as MockTril,
            patch("sys.stdin.isatty", return_value=False),
            patch("sys.stdin.read", return_value="## Updated via stdin"),
        ):
            inst = MockTril.return_value
            inst.get_note.return_value = {
                "noteId": "n1",
                "title": "test",
                "attributes": [],
            }

            args = MagicMock(note_id="n1", title=None, content_file=None)
            cmd_update(args)
            inst.update_note_content.assert_called_once()
            call_content = inst.update_note_content.call_args[0][1]
            assert "Updated via stdin" in call_content


class TestCmdListJson:
    def test_list_json_format(self, tmp_path, capsys):
        config_path = _make_config(tmp_path)
        with (
            patch("trilium.CONFIG_PATH", config_path),
            patch("trilium.Trilium") as MockTril,
        ):
            inst = MockTril.return_value
            inst.search.return_value = [
                {
                    "noteId": "n1",
                    "title": "🪤 · bug",
                    "attributes": [{"name": "diaryDate", "value": "2026-06-01"}],
                },
                {
                    "noteId": "n2",
                    "title": "💡 · insight",
                    "attributes": [{"name": "diaryDate", "value": "2026-06-02"}],
                },
            ]

            args = MagicMock(date=None, limit=50, format="json")
            cmd_list(args)
            out = capsys.readouterr().out
            data = json.loads(out)
            assert len(data) == 2
            assert data[0]["noteId"] == "n1"
            assert data[1]["title"] == "💡 · insight"

    def test_list_text_format_default(self, tmp_path, capsys):
        config_path = _make_config(tmp_path)
        with (
            patch("trilium.CONFIG_PATH", config_path),
            patch("trilium.Trilium") as MockTril,
        ):
            inst = MockTril.return_value
            inst.search.return_value = [
                {
                    "noteId": "n1",
                    "title": "🪤 · bug",
                    "attributes": [{"name": "diaryDate", "value": "2026-06-01"}],
                },
            ]

            args = MagicMock(date=None, limit=50, format="text")
            cmd_list(args)
            out = capsys.readouterr().out
            assert "n1" in out
            assert "🪤 · bug" in out
            # Should NOT be JSON
            assert not out.strip().startswith("[")


class TestNetworkRetry:
    def test_retry_adapter_mounted(self):
        """Session has retry adapter mounted for http and https."""
        cfg = {"server": "http://localhost:8080", "token": "test-token"}
        t = Trilium(cfg)
        adapter = t.s.get_adapter("http://localhost")
        assert adapter is not None
        assert adapter.max_retries.total == 3
        adapter_https = t.s.get_adapter("https://localhost")
        assert adapter_https is not None
        assert adapter_https.max_retries.total == 3


class TestCmdCheckEnhanced:
    def test_check_validates_calendar_root_label(self, tmp_path, capsys):
        config_path = _make_config(tmp_path)
        with (
            patch("trilium.CONFIG_PATH", config_path),
            patch("trilium.Trilium") as MockTril,
        ):
            inst = MockTril.return_value
            inst.app_info.return_value = {"appVersion": "0.63.0"}
            inst.calendar_root.return_value = "abc"
            inst.get_note.return_value = {
                "noteId": "abc",
                "attributes": [{"name": "calendarRoot", "value": ""}],
            }
            args = MagicMock(cmd="check")
            cmd_check(args)
            out = capsys.readouterr().out
            assert "#calendarRoot" in out
            assert "验证通过" in out

    def test_check_warns_missing_calendar_root_label(self, tmp_path, capsys):
        config_path = _make_config(tmp_path)
        with (
            patch("trilium.CONFIG_PATH", config_path),
            patch("trilium.Trilium") as MockTril,
        ):
            inst = MockTril.return_value
            inst.app_info.return_value = {"appVersion": "0.63.0"}
            inst.calendar_root.return_value = "abc"
            inst.get_note.return_value = {
                "noteId": "abc",
                "attributes": [],
            }
            args = MagicMock(cmd="check")
            cmd_check(args)
            out = capsys.readouterr().out
            assert "缺少" in out or "⚠" in out


class TestResolveJsonlPath:
    def test_explicit_session_and_project_dir(self, tmp_path):
        proj = tmp_path / "myproj"
        proj.mkdir()
        path = resolve_jsonl_path("abc-123", str(proj))
        slug = str(proj).replace("/", "-")
        assert path.endswith(f"{slug}/abc-123.jsonl")

    def test_falls_back_to_env(self, tmp_path, monkeypatch):
        proj = tmp_path / "p"
        proj.mkdir()
        monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "envsess")
        monkeypatch.chdir(proj)
        path = resolve_jsonl_path(None, None)
        assert path.endswith("envsess.jsonl")

    def test_missing_session_exits(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
        monkeypatch.chdir(tmp_path)
        with pytest.raises(SystemExit):
            resolve_jsonl_path(None, None)


class TestCmdRecapCreate:
    def test_creates_new_note_with_labels(self, tmp_path, monkeypatch, capsys):
        # config
        cfg_path = _make_config(tmp_path)
        monkeypatch.setattr("trilium.CONFIG_PATH", cfg_path)

        # jsonl fixture
        jsonl = tmp_path / "sess.jsonl"
        jsonl.write_text(
            '{"type":"user","message":{"role":"user","content":[{"type":"text","text":"hi"}]}}\n',
            encoding="utf-8",
        )

        args = MagicMock()
        args.title_suffix = "重构设计"
        args.session = "sess"
        args.project_dir = str(tmp_path)
        args.date = None

        # Patch the actual jsonl path resolution to return our fixture
        monkeypatch.setattr(
            "trilium.resolve_jsonl_path",
            lambda s, p: str(jsonl),
        )

        with patch.object(Trilium, "ensure_date_path", return_value="day123"), \
             patch.object(Trilium, "find_session_note", return_value=None), \
             patch.object(
                 Trilium, "create_note",
                 return_value={"note": {"noteId": "newnote"}},
             ) as create, \
             patch.object(Trilium, "add_label") as add_label:
            cmd_recap(args)

        create.assert_called_once()
        # The note title is "Recap：重构设计"
        assert create.call_args.args[1] == "Recap：重构设计"
        # Labels: #diary, #sessionId=sess, #diaryDate=<today>, #iconClass
        names = [c.args[1] for c in add_label.call_args_list]
        assert "diary" in names
        assert "sessionId" in names
        assert "diaryDate" in names
        assert "iconClass" in names
        # Verify iconClass value is RECAP_ICON
        icon_call = next(
            c for c in add_label.call_args_list if c.args[1] == "iconClass"
        )
        assert icon_call.args[2] == RECAP_ICON


class TestCmdRecapUpdate:
    def test_updates_existing_note_when_session_matches(
        self, tmp_path, monkeypatch
    ):
        cfg_path = _make_config(tmp_path)
        monkeypatch.setattr("trilium.CONFIG_PATH", cfg_path)

        jsonl = tmp_path / "sess.jsonl"
        jsonl.write_text(
            '{"type":"user","message":{"role":"user","content":[{"type":"text","text":"hi"}]}}\n',
            encoding="utf-8",
        )

        args = MagicMock()
        args.title_suffix = "v2"
        args.session = "sess"
        args.project_dir = str(tmp_path)
        args.date = None

        monkeypatch.setattr(
            "trilium.resolve_jsonl_path",
            lambda s, p: str(jsonl),
        )

        with patch.object(Trilium, "ensure_date_path", return_value="day"), \
             patch.object(Trilium, "find_session_note", return_value="existing-id"), \
             patch.object(Trilium, "update_note_content") as upd_content, \
             patch.object(
                 Trilium, "get_note",
                 return_value={"title": "Recap：v1"},
             ), \
             patch.object(Trilium, "update_note") as upd_note, \
             patch.object(Trilium, "create_note") as create, \
             patch.object(Trilium, "add_label") as add_label:
            cmd_recap(args)

        upd_content.assert_called_once()
        assert upd_content.call_args.args[0] == "existing-id"
        upd_note.assert_called_once_with("existing-id", title="Recap：v2")
        create.assert_not_called()
        add_label.assert_not_called()

    def test_skips_title_patch_when_unchanged(self, tmp_path, monkeypatch):
        cfg_path = _make_config(tmp_path)
        monkeypatch.setattr("trilium.CONFIG_PATH", cfg_path)
        jsonl = tmp_path / "s.jsonl"
        jsonl.write_text(
            '{"type":"user","message":{"role":"user","content":[{"type":"text","text":"hi"}]}}\n',
            encoding="utf-8",
        )
        args = MagicMock()
        args.title_suffix = "same"
        args.session = "s"
        args.project_dir = str(tmp_path)
        args.date = None
        monkeypatch.setattr("trilium.resolve_jsonl_path", lambda a, b: str(jsonl))
        with patch.object(Trilium, "ensure_date_path", return_value="day"), \
             patch.object(Trilium, "find_session_note", return_value="eid"), \
             patch.object(Trilium, "update_note_content"), \
             patch.object(
                 Trilium, "get_note", return_value={"title": "Recap：same"}
             ), \
             patch.object(Trilium, "update_note") as upd_note:
            cmd_recap(args)
        upd_note.assert_not_called()
