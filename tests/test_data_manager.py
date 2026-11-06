import pytest

import data_manager


@pytest.fixture(autouse=True)
def contacts_dir(tmp_path, monkeypatch):
    path = tmp_path / "contacts"
    path.mkdir()
    monkeypatch.setattr(data_manager, "CONTACTS_DIR", str(path))
    return path


def test_create_contact(contacts_dir):
    assert data_manager.create_new_contact("小明") == (True, "创建成功。")
    assert data_manager.get_all_contacts() == ["小明"]


def test_names_containing_json_are_listed_unchanged(contacts_dir):
    for name in ("notes.json", "a.jsonb"):
        data_manager.create_new_contact(name)

    assert data_manager.get_all_contacts() == ["a.jsonb", "notes.json"]


@pytest.mark.parametrize("name", [
    "../escaped", "a/b", "a\\b", "..", "a:b", "a?b", "a\nb", "CON", "nul", "com1", "a.", "a ",
])
def test_create_rejects_names_that_are_not_plain_file_names(tmp_path, contacts_dir, name):
    ok, _ = data_manager.create_new_contact(name)

    assert not ok
    assert list(tmp_path.rglob("*.json")) == []


def test_duplicate_rejects_names_outside_contacts_dir(tmp_path, contacts_dir):
    data_manager.create_new_contact("小明")

    ok, _ = data_manager.duplicate_contact("小明", "../escaped")

    assert not ok
    assert not (tmp_path / "escaped.json").exists()


def test_failed_save_keeps_previous_file(contacts_dir, monkeypatch):
    data_manager.create_new_contact("小明")
    data = data_manager.load_contact_data("小明")
    data["history"] = [{"role": "user", "content": "你好"}]
    assert data_manager.save_contact_data("小明", data)

    def disk_full(obj, f, **kwargs):  # write part of the file, then the disk fills up
        f.write("{")
        raise OSError(28, "No space left on device")

    with monkeypatch.context() as m:
        m.setattr(data_manager.json, "dump", disk_full)
        data["history"].append({"role": "user", "content": "新消息"})
        assert data_manager.save_contact_data("小明", data) is False

    assert data_manager.load_contact_data("小明")["history"] == [{"role": "user", "content": "你好"}]
    assert data_manager.get_all_contacts() == ["小明"]
    assert [p.name for p in contacts_dir.iterdir()] == ["小明.json"]


@pytest.mark.parametrize("content", [
    b"\xff\xfe not utf-8", b"[]", b"null", b'"text"',
    # a history entry the app can't show: never load it, or the next save rewrites the file around it
    '{"history": [{"role": "user", "text": "旧格式"}]}'.encode(), b'{"history": ["hi"]}',
])
def test_unreadable_or_non_object_file_loads_as_none(contacts_dir, content):
    (contacts_dir / "小明.json").write_bytes(content)

    assert data_manager.load_contact_data("小明") is None


def test_null_fields_load_as_defaults(contacts_dir):
    (contacts_dir / "小明.json").write_text(
        '{"history": null, "settings": null, "prompt": null, "topic_starter_prompt": 1}', encoding="utf-8")

    data = data_manager.load_contact_data("小明")

    assert data["history"] == [] and data["settings"] == {}
    assert data["prompt"] == data_manager.DEFAULT_PROMPT
    assert data["topic_starter_prompt"] == data_manager.DEFAULT_TOPIC_STARTER_PROMPT


def test_contact_saved_with_a_bom_loads(contacts_dir):  # older Windows Notepad adds one
    (contacts_dir / "小明.json").write_bytes('{"prompt": "老朋友"}'.encode("utf-8-sig"))

    assert data_manager.load_contact_data("小明")["prompt"] == "老朋友"
