import pytest

tk = pytest.importorskip("tkinter")

import ai_handler  # noqa: E402
import app  # noqa: E402
import data_manager  # noqa: E402

OLD_DEFAULT, NEW_DEFAULT, OTHER = "gemini-3.6-flash", "gemini-3.8-flash", "gemini-3.5-flash-lite"


@pytest.fixture
def chat(tmp_path, monkeypatch):
    monkeypatch.setattr(ai_handler, "CONFIG_FILE", str(tmp_path / "config.json"))
    monkeypatch.setattr(data_manager, "CONTACTS_DIR", str(tmp_path / "contacts"))
    for name in ("API_KEY", "GLOBAL_PROMPT", "MODEL_NAME"):  # save_app_config reloads these globals
        monkeypatch.setattr(ai_handler, name, getattr(ai_handler, name))
    monkeypatch.setattr(ai_handler, "fetch_available_models", lambda: None)
    monkeypatch.setattr(app.messagebox, "showinfo", lambda *a, **k: None)
    ai_handler.save_app_config(OLD_DEFAULT, "")
    try:
        window = app.ChatMateApp()
    except tk.TclError:
        pytest.skip("needs a display (on Linux, run under xvfb-run)")
    window.withdraw()
    yield window
    window.destroy()


def open_contact(chat, name):
    data_manager.create_new_contact(name)
    chat.refresh_contacts_list(select_contact=name)


def change_default_model(chat, model):
    window = app.GlobalSettingsWindow(chat)
    window.model_var.set(model)
    window.save_settings()


def test_contact_on_the_default_model_follows_a_new_default(chat):
    open_contact(chat, "小明")

    change_default_model(chat, NEW_DEFAULT)

    assert not chat.has_unsaved_changes()
    assert chat.save_settings()
    assert "model_name" not in data_manager.load_contact_data("小明")["settings"]


def test_contact_on_its_own_model_keeps_it_when_the_default_changes(chat):
    open_contact(chat, "小红")
    chat.model_var.set(OTHER)
    chat.save_settings()

    change_default_model(chat, NEW_DEFAULT)

    assert chat.save_settings()
    assert data_manager.load_contact_data("小红")["settings"]["model_name"] == OTHER


def test_contact_pinned_to_a_model_keeps_it_while_the_default_matches(chat):
    open_contact(chat, "小红")
    chat.model_var.set(OTHER)
    chat.save_settings()

    change_default_model(chat, OTHER)
    chat.refresh_contacts_list(select_contact="小红")
    assert chat.save_settings()
    change_default_model(chat, OLD_DEFAULT)

    assert chat.save_settings()
    assert data_manager.load_contact_data("小红")["settings"]["model_name"] == OTHER


def test_contact_following_the_default_stays_unpinned_when_the_model_list_arrives(chat):
    open_contact(chat, "小明")

    chat._apply_models([NEW_DEFAULT, OTHER])  # the configured default is no longer offered

    assert chat.save_settings()
    assert "model_name" not in data_manager.load_contact_data("小明")["settings"]


def test_second_settings_click_reuses_the_open_window(chat):
    chat.open_global_settings()
    first = chat.settings_window
    chat.open_global_settings()

    assert chat.settings_window is first
