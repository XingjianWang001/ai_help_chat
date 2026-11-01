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
