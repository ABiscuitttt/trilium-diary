"""Integration tests for cmd_note_* / cmd_list / cmd_get / cmd_update / cmd_delete."""

import io
import json
import os
import sys
from argparse import Namespace
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from trilium import (
    TYPE_DEFAULT_ICONS,
    cmd_delete,
    cmd_get,
    cmd_list,
    cmd_note_idea,
    cmd_note_merge_topic,
    cmd_note_ref,
    cmd_note_til,
    cmd_note_topics,
    cmd_update,
)


def _make_config(tmp_path):
    cfg = {
        "server": "http://localhost:8080",
        "token": "test-token",
        "calendarRootId": "cal",
        "knowledgeRootId": "know",
    }
    p = tmp_path / "etc" / "config.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg), encoding="utf-8")
    return str(p)


class TestNoteTilHappyPath:
    def test_creates_note_labels_and_clone(self, tmp_path, capsys, monkeypatch):
        monkeypatch.setattr("trilium.CONFIG_PATH", _make_config(tmp_path))
        monkeypatch.setattr("sys.stdin", io.StringIO("# body\ncontent"))

        with patch("trilium.Trilium") as TClass:
            t = TClass.return_value
            t.ensure_topic_path.return_value = "topicNoteId"
            t.ensure_date_path.return_value = "dayNoteId"
            t.create_note.return_value = {"note": {"noteId": "abc123"}}
            t.clone_note.return_value = {
                "cloned": True, "alreadyPresent": False, "error": None,
            }

            args = Namespace(
                topic="Postgres",
                title="TIL: timestamps",
                source_session="sess-1",
                note_date="2026-07-03",
                icon=None,
            )
            cmd_note_til(args)

        # verify structure calls
        t.ensure_topic_path.assert_called_once_with("til", "Postgres")
        # 6 generic labels
        label_names = {c.args[1] for c in t.add_label.call_args_list}
        assert label_names == {
            "knowledge", "type", "topic", "sourceSession", "noteDate", "iconClass",
        }
        # default icon
        icon_val = next(
            c.args[2] for c in t.add_label.call_args_list if c.args[1] == "iconClass"
        )
        assert icon_val == TYPE_DEFAULT_ICONS["til"]
        # clone to day note
        t.clone_note.assert_called_once_with("abc123", "dayNoteId")

        # stdout JSON
        out = json.loads(capsys.readouterr().out)
        assert out == {
            "noteId": "abc123",
            "url": "http://localhost:8080/#root/abc123",
            "cloned": True,
        }

    def test_uses_custom_icon_when_provided(self, tmp_path, capsys, monkeypatch):
        monkeypatch.setattr("trilium.CONFIG_PATH", _make_config(tmp_path))
        monkeypatch.setattr("sys.stdin", io.StringIO("body"))

        with patch("trilium.Trilium") as TClass:
            t = TClass.return_value
            t.ensure_topic_path.return_value = "topic"
            t.ensure_date_path.return_value = "day"
            t.create_note.return_value = {"note": {"noteId": "n1"}}
            t.clone_note.return_value = {
                "cloned": True, "alreadyPresent": False, "error": None,
            }

            args = Namespace(
                topic="Postgres",
                title="t",
                source_session="s",
                note_date="2026-07-03",
                icon="bx bx-data",
            )
            cmd_note_til(args)

        icon_val = next(
            c.args[2] for c in t.add_label.call_args_list if c.args[1] == "iconClass"
        )
        assert icon_val == "bx bx-data"

    def test_normalizes_topic_label_to_match_topic_path(
        self, tmp_path, capsys, monkeypatch
    ):
        monkeypatch.setattr("trilium.CONFIG_PATH", _make_config(tmp_path))
        monkeypatch.setattr("sys.stdin", io.StringIO("body"))

        with patch("trilium.Trilium") as TClass:
            t = TClass.return_value
            t.ensure_topic_path.return_value = "topic"
            t.ensure_date_path.return_value = "day"
            t.create_note.return_value = {"note": {"noteId": "n1"}}
            t.clone_note.return_value = {
                "cloned": True, "alreadyPresent": False, "error": None,
            }

            args = Namespace(
                topic="  Postgres  ",
                title="TIL: tz",
                source_session="s",
                note_date="2026-07-03",
                icon=None,
            )
            cmd_note_til(args)

        t.ensure_topic_path.assert_called_once_with("til", "Postgres")
        topic_val = next(
            c.args[2] for c in t.add_label.call_args_list if c.args[1] == "topic"
        )
        assert topic_val == "Postgres"

    def test_invalid_note_date_fails_before_writing(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr("trilium.CONFIG_PATH", _make_config(tmp_path))
        monkeypatch.setattr("sys.stdin", io.StringIO("body"))

        with patch("trilium.Trilium") as TClass:
            t = TClass.return_value
            args = Namespace(
                topic="Postgres",
                title="TIL: tz",
                source_session="s",
                note_date="not-a-date",
                icon=None,
            )
            with pytest.raises(SystemExit):
                cmd_note_til(args)

        t.ensure_topic_path.assert_not_called()
        t.create_note.assert_not_called()

    def test_note_date_label_is_canonical_isoformat(
        self, tmp_path, capsys, monkeypatch
    ):
        monkeypatch.setattr("trilium.CONFIG_PATH", _make_config(tmp_path))
        monkeypatch.setattr("sys.stdin", io.StringIO("body"))

        with patch("trilium.Trilium") as TClass:
            t = TClass.return_value
            t.ensure_topic_path.return_value = "topic"
            t.ensure_date_path.return_value = "day"
            t.create_note.return_value = {"note": {"noteId": "n1"}}
            t.clone_note.return_value = {
                "cloned": True, "alreadyPresent": False, "error": None,
            }

            args = Namespace(
                topic="Postgres",
                title="TIL: tz",
                source_session="s",
                note_date="2026-7-3",
                icon=None,
            )
            cmd_note_til(args)

        note_date_val = next(
            c.args[2] for c in t.add_label.call_args_list if c.args[1] == "noteDate"
        )
        assert note_date_val == "2026-07-03"

    def test_empty_stdin_dies(self, tmp_path, monkeypatch):
        monkeypatch.setattr("trilium.CONFIG_PATH", _make_config(tmp_path))
        monkeypatch.setattr("sys.stdin", io.StringIO("   \n\n"))

        args = Namespace(
            topic="X", title="t", source_session="s",
            note_date="2026-07-03", icon=None,
        )
        with pytest.raises(SystemExit):
            cmd_note_til(args)


class TestNoteIdea:
    def test_type_key_is_idea(self, tmp_path, capsys, monkeypatch):
        monkeypatch.setattr("trilium.CONFIG_PATH", _make_config(tmp_path))
        monkeypatch.setattr("sys.stdin", io.StringIO("body"))
        with patch("trilium.Trilium") as TClass:
            t = TClass.return_value
            t.ensure_topic_path.return_value = "topic"
            t.ensure_date_path.return_value = "day"
            t.create_note.return_value = {"note": {"noteId": "i1"}}
            t.clone_note.return_value = {
                "cloned": True, "alreadyPresent": False, "error": None,
            }
            args = Namespace(
                topic="Trilium", title="t", source_session="s",
                note_date="2026-07-03", icon=None,
            )
            cmd_note_idea(args)
        t.ensure_topic_path.assert_called_once_with("idea", "Trilium")
        type_val = next(
            c.args[2] for c in t.add_label.call_args_list if c.args[1] == "type"
        )
        assert type_val == "idea"


class TestNoteRef:
    def test_adds_url_label(self, tmp_path, capsys, monkeypatch):
        monkeypatch.setattr("trilium.CONFIG_PATH", _make_config(tmp_path))
        monkeypatch.setattr("sys.stdin", io.StringIO("body"))
        with patch("trilium.Trilium") as TClass:
            t = TClass.return_value
            t.ensure_topic_path.return_value = "topic"
            t.ensure_date_path.return_value = "day"
            t.create_note.return_value = {"note": {"noteId": "r1"}}
            t.clone_note.return_value = {
                "cloned": True, "alreadyPresent": False, "error": None,
            }
            args = Namespace(
                topic="SQLite", title="t", source_session="s",
                note_date="2026-07-03", icon=None, url="https://example.com/x",
            )
            cmd_note_ref(args)
        labels = {c.args[1]: c.args[2] for c in t.add_label.call_args_list}
        assert labels["url"] == "https://example.com/x"

    def test_missing_url_dies(self, tmp_path, monkeypatch):
        monkeypatch.setattr("trilium.CONFIG_PATH", _make_config(tmp_path))
        monkeypatch.setattr("sys.stdin", io.StringIO("body"))
        args = Namespace(
            topic="X", title="t", source_session="s",
            note_date="2026-07-03", icon=None, url=None,
        )
        with pytest.raises(SystemExit):
            cmd_note_ref(args)


class TestCloneFallback:
    def test_clone_failure_reports_and_continues(
        self, tmp_path, capsys, monkeypatch
    ):
        monkeypatch.setattr("trilium.CONFIG_PATH", _make_config(tmp_path))
        monkeypatch.setattr("sys.stdin", io.StringIO("body"))
        with patch("trilium.Trilium") as TClass:
            t = TClass.return_value
            t.ensure_topic_path.return_value = "topic"
            t.ensure_date_path.return_value = "day"
            t.create_note.return_value = {"note": {"noteId": "n1"}}
            t.clone_note.return_value = {
                "cloned": False, "alreadyPresent": False, "error": "http 500",
            }
            args = Namespace(
                topic="X", title="t", source_session="s",
                note_date="2026-07-03", icon=None,
            )
            cmd_note_til(args)
        cap = capsys.readouterr()
        out = json.loads(cap.out)
        assert out["cloned"] is False
        assert out["cloneError"] == "http 500"
        assert "clone 到日历失败" in cap.err


class TestList:
    def _make_hits(self):
        return [
            {
                "noteId": "n1",
                "title": "TIL: pg tz",
                "attributes": [
                    {"name": "type", "value": "til"},
                    {"name": "topic", "value": "Postgres"},
                    {"name": "noteDate", "value": "2026-07-03"},
                    {"name": "sourceSession", "value": "sess-1"},
                ],
            },
            {
                "noteId": "n2",
                "title": "Idea: workspaces",
                "attributes": [
                    {"name": "type", "value": "idea"},
                    {"name": "topic", "value": "Trilium"},
                    {"name": "noteDate", "value": "2026-07-03"},
                    {"name": "sourceSession", "value": "sess-1"},
                ],
            },
        ]

    def test_list_default_uses_knowledge_tag(
        self, tmp_path, capsys, monkeypatch
    ):
        monkeypatch.setattr("trilium.CONFIG_PATH", _make_config(tmp_path))
        with patch("trilium.Trilium") as TClass:
            t = TClass.return_value
            t.search.return_value = self._make_hits()
            args = Namespace(
                type=None, topic=None, note_date=None,
                source_session=None, limit=50,
            )
            cmd_list(args)
        expr = t.search.call_args.args[0]
        assert "#knowledge" in expr
        out = json.loads(capsys.readouterr().out)
        assert len(out["items"]) == 2
        first = out["items"][0]
        assert first["noteId"] == "n1"
        assert first["type"] == "til"
        assert first["topic"] == "Postgres"
        assert first["noteDate"] == "2026-07-03"
        assert first["sourceSession"] == "sess-1"
        assert first["url"] == "http://localhost:8080/#root/n1"

    def test_list_filters_compose(self, tmp_path, capsys, monkeypatch):
        monkeypatch.setattr("trilium.CONFIG_PATH", _make_config(tmp_path))
        with patch("trilium.Trilium") as TClass:
            t = TClass.return_value
            t.search.return_value = []
            args = Namespace(
                type="til", topic="Postgres", note_date="2026-07-03",
                source_session="sess-1", limit=10,
            )
            cmd_list(args)
        expr = t.search.call_args.args[0]
        assert "#knowledge" in expr
        assert '#type="til"' in expr
        assert '#topic="Postgres"' in expr
        assert '#noteDate="2026-07-03"' in expr
        assert '#sourceSession="sess-1"' in expr
        assert t.search.call_args.kwargs["limit"] == "10"

    def test_list_empty_returns_empty_items(
        self, tmp_path, capsys, monkeypatch
    ):
        monkeypatch.setattr("trilium.CONFIG_PATH", _make_config(tmp_path))
        with patch("trilium.Trilium") as TClass:
            t = TClass.return_value
            t.search.return_value = []
            args = Namespace(
                type=None, topic=None, note_date=None,
                source_session=None, limit=50,
            )
            cmd_list(args)
        out = json.loads(capsys.readouterr().out)
        assert out == {"items": []}


class TestGet:
    def _note(self):
        return {
            "noteId": "n1",
            "title": "TIL: tz",
            "attributes": [
                {"name": "type", "value": "til"},
                {"name": "topic", "value": "Postgres"},
                {"name": "noteDate", "value": "2026-07-03"},
                {"name": "sourceSession", "value": "sess-1"},
                {"name": "iconClass", "value": "bx bx-data"},
                {"name": "url", "value": "https://example.com/ref"},
            ],
        }

    def test_get_returns_metadata_json(
        self, tmp_path, capsys, monkeypatch
    ):
        monkeypatch.setattr("trilium.CONFIG_PATH", _make_config(tmp_path))
        with patch("trilium.Trilium") as TClass:
            t = TClass.return_value
            t.get_note.return_value = self._note()
            args = Namespace(note_id="n1", content=False)
            cmd_get(args)
        out = json.loads(capsys.readouterr().out)
        assert out == {
            "noteId": "n1",
            "title": "TIL: tz",
            "type": "til",
            "topic": "Postgres",
            "noteDate": "2026-07-03",
            "sourceSession": "sess-1",
            "iconClass": "bx bx-data",
            "sourceUrl": "https://example.com/ref",
            "url": "http://localhost:8080/#root/n1",
        }

    def test_get_with_content_adds_content_field(
        self, tmp_path, capsys, monkeypatch
    ):
        monkeypatch.setattr("trilium.CONFIG_PATH", _make_config(tmp_path))
        with patch("trilium.Trilium") as TClass:
            t = TClass.return_value
            t.get_note.return_value = self._note()
            t.get_note_content.return_value = "<p>body</p>"
            args = Namespace(note_id="n1", content=True)
            cmd_get(args)
        out = json.loads(capsys.readouterr().out)
        assert out["content"] == "<p>body</p>"


class TestUpdate:
    def _note_with_icon(self):
        return {
            "noteId": "n1",
            "title": "old title",
            "attributes": [
                {"attributeId": "attrIcon", "name": "iconClass", "value": "bx bx-x"},
            ],
        }

    def _note_without_icon(self):
        return {"noteId": "n1", "title": "old", "attributes": []}

    def test_update_title_only(self, tmp_path, capsys, monkeypatch):
        monkeypatch.setattr("trilium.CONFIG_PATH", _make_config(tmp_path))
        fake = io.StringIO("")
        fake.isatty = lambda: True
        monkeypatch.setattr("sys.stdin", fake)
        with patch("trilium.Trilium") as TClass:
            t = TClass.return_value
            t.get_note.return_value = self._note_without_icon()
            args = Namespace(note_id="n1", title="new title", icon=None)
            cmd_update(args)
        t.update_note.assert_called_once_with("n1", title="new title")
        t.update_note_content.assert_not_called()
        out = json.loads(capsys.readouterr().out)
        assert out == {"noteId": "n1", "ok": True}

    def test_update_content_from_stdin(self, tmp_path, capsys, monkeypatch):
        monkeypatch.setattr("trilium.CONFIG_PATH", _make_config(tmp_path))
        fake = io.StringIO("## new body")
        fake.isatty = lambda: False
        monkeypatch.setattr("sys.stdin", fake)
        with patch("trilium.Trilium") as TClass:
            t = TClass.return_value
            t.get_note.return_value = self._note_without_icon()
            args = Namespace(note_id="n1", title=None, icon=None)
            cmd_update(args)
        t.update_note_content.assert_called_once()
        html_arg = t.update_note_content.call_args.args[1]
        assert "<h2>new body" in html_arg

    def test_update_icon_patches_existing_attr(
        self, tmp_path, capsys, monkeypatch
    ):
        monkeypatch.setattr("trilium.CONFIG_PATH", _make_config(tmp_path))
        fake = io.StringIO("")
        fake.isatty = lambda: True
        monkeypatch.setattr("sys.stdin", fake)
        with patch("trilium.Trilium") as TClass:
            t = TClass.return_value
            t.get_note.return_value = self._note_with_icon()
            args = Namespace(note_id="n1", title=None, icon="bx bx-data")
            cmd_update(args)
        t.patch_attribute.assert_called_once_with("attrIcon", value="bx bx-data")
        t.add_label.assert_not_called()

    def test_update_icon_adds_label_when_missing(
        self, tmp_path, capsys, monkeypatch
    ):
        monkeypatch.setattr("trilium.CONFIG_PATH", _make_config(tmp_path))
        fake = io.StringIO("")
        fake.isatty = lambda: True
        monkeypatch.setattr("sys.stdin", fake)
        with patch("trilium.Trilium") as TClass:
            t = TClass.return_value
            t.get_note.return_value = self._note_without_icon()
            args = Namespace(note_id="n1", title=None, icon="bx bx-cog")
            cmd_update(args)
        t.add_label.assert_called_once_with("n1", "iconClass", "bx bx-cog")
        t.patch_attribute.assert_not_called()

    def test_update_icon_empty_string_is_noop(
        self, tmp_path, capsys, monkeypatch
    ):
        monkeypatch.setattr("trilium.CONFIG_PATH", _make_config(tmp_path))
        fake = io.StringIO("")
        fake.isatty = lambda: True
        monkeypatch.setattr("sys.stdin", fake)
        with patch("trilium.Trilium") as TClass:
            t = TClass.return_value
            args = Namespace(note_id="n1", title=None, icon="")
            cmd_update(args)
        t.get_note.assert_not_called()
        t.patch_attribute.assert_not_called()
        t.add_label.assert_not_called()


class TestDelete:
    def test_delete_emits_json(self, tmp_path, capsys, monkeypatch):
        monkeypatch.setattr("trilium.CONFIG_PATH", _make_config(tmp_path))
        with patch("trilium.Trilium") as TClass:
            t = TClass.return_value
            args = Namespace(note_id="n1")
            cmd_delete(args)
        t.delete_note.assert_called_once_with("n1")
        out = json.loads(capsys.readouterr().out)
        assert out == {"noteId": "n1", "ok": True}


class TestNoteTopics:
    def _topic_notes(self):
        # 主题节点自身
        return [
            {
                "noteId": "topicPg",
                "title": "Postgres",
                "attributes": [
                    {"name": "topicNote", "value": "til:Postgres"},
                ],
            },
            {
                "noteId": "topicRust",
                "title": "Rust",
                "attributes": [
                    {"name": "topicNote", "value": "idea:Rust"},
                ],
            },
        ]

    def test_topics_lists_and_counts(self, tmp_path, capsys, monkeypatch):
        monkeypatch.setattr("trilium.CONFIG_PATH", _make_config(tmp_path))

        def _search(expr, **_):
            if "#topicNote" in expr:
                return self._topic_notes()
            # count queries: match by #knowledge #type=X #topic=Y
            if 'topic="Postgres"' in expr:
                return [{"noteId": "n1"}, {"noteId": "n2"}]
            if 'topic="Rust"' in expr:
                return [{"noteId": "n3"}]
            return []

        with patch("trilium.Trilium") as TClass:
            t = TClass.return_value
            t.search.side_effect = _search
            args = Namespace()
            cmd_note_topics(args)

        out = json.loads(capsys.readouterr().out)
        topics = sorted(out["topics"], key=lambda x: x["topic"])
        assert topics == [
            {"type": "til", "topic": "Postgres", "noteId": "topicPg", "count": 2},
            {"type": "idea", "topic": "Rust", "noteId": "topicRust", "count": 1},
        ]


class TestMergeTopic:
    def test_merge_moves_notes_and_removes_empty_source(
        self, tmp_path, capsys, monkeypatch
    ):
        monkeypatch.setattr("trilium.CONFIG_PATH", _make_config(tmp_path))

        source_notes = [
            {
                "noteId": "n1",
                "attributes": [
                    {"attributeId": "at1", "name": "topic", "value": "OldPg"},
                ],
            },
            {
                "noteId": "n2",
                "attributes": [
                    {"attributeId": "at2", "name": "topic", "value": "OldPg"},
                ],
            },
        ]
        source_topic_hits = [
            {
                "noteId": "topicOld",
                "attributes": [{"name": "topicNote", "value": "til:OldPg"}],
            }
        ]

        empty_after_move = {"called": False}

        def _search(expr, **_):
            if "#knowledge" in expr and 'topic="OldPg"' in expr:
                if empty_after_move["called"]:
                    return []
                empty_after_move["called"] = True
                return source_notes
            if '#topicNote="til:OldPg"' in expr:
                return source_topic_hits
            return []

        with patch("trilium.Trilium") as TClass:
            t = TClass.return_value
            t.search.side_effect = _search
            t.ensure_topic_path.return_value = "topicNew"
            t.find_branch.side_effect = ["b1", "b2"]

            args = Namespace(type="til", from_topic="OldPg", to_topic="Postgres")
            cmd_note_merge_topic(args)

        patch_calls = t.patch_attribute.call_args_list
        assert any(c.args[0] == "at1" for c in patch_calls)
        assert any(c.args[0] == "at2" for c in patch_calls)
        t.ensure_topic_path.assert_called_once_with("til", "Postgres")
        assert t.delete_branch.call_count == 2
        assert t.create_branch.call_count == 2
        t.delete_note.assert_called_once_with("topicOld")

        out = json.loads(capsys.readouterr().out)
        assert out == {
            "moved": 2,
            "fromNoteId": "topicOld",
            "toNoteId": "topicNew",
            "fromEmpty": True,
        }
