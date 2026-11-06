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


def select(chat, name):
    chat.contacts_listbox.selection_clear(0, tk.END)
    chat.contacts_listbox.selection_set(chat.contacts_listbox.get(0, tk.END).index(name))
    chat.on_contact_select(None)


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

    open_contact(chat, "小明")
    change_default_model(chat, OTHER)
    select(chat, "小红")  # reopen her while the default matches her model
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


def open_contact_with_history(chat, name, *contents):
    open_contact(chat, name)
    for i, content in enumerate(contents):
        chat.contact_data["history"].append({"role": "user" if i % 2 == 0 else "assistant", "content": content})
    chat.save_contact()


def test_undo_removes_the_last_history_entry_and_keeps_setting_edits(chat, monkeypatch):
    monkeypatch.setattr(app.messagebox, "askyesno", lambda *a, **k: True)
    open_contact_with_history(chat, "小明", "在吗", "在的")
    chat.prompt_text.insert("1.0", "新的提示词")

    chat.undo_last_entry()

    saved = data_manager.load_contact_data("小明")
    assert [m["content"] for m in saved["history"]] == ["在吗"]
    assert saved["prompt"].startswith("新的提示词")
    assert "在的" not in chat.history_text.get("1.0", tk.END)


def test_undo_does_nothing_when_declined(chat, monkeypatch):
    monkeypatch.setattr(app.messagebox, "askyesno", lambda *a, **k: False)
    open_contact_with_history(chat, "小明", "在吗")

    chat.undo_last_entry()

    assert len(data_manager.load_contact_data("小明")["history"]) == 1


def test_undo_keeps_the_entry_when_the_save_fails(chat, monkeypatch):
    monkeypatch.setattr(app.messagebox, "askyesno", lambda *a, **k: True)
    monkeypatch.setattr(app.messagebox, "showerror", lambda *a, **k: None)
    open_contact_with_history(chat, "小明", "在吗")
    monkeypatch.setattr(data_manager, "save_contact_data", lambda *a: False)

    chat.undo_last_entry()

    assert [m["content"] for m in chat.contact_data["history"]] == ["在吗"]


# Every action that ends in update_ui_for_contact must save the edits first, or stop when it can't.
ACTIONS = {
    "switch contact": lambda chat: select(chat, "小红"),
    "duplicate": lambda chat: chat.duplicate_contact(),
    "send": lambda chat: (chat.input_entry.insert(0, "在吗"), chat.send_message()),
    "topic starters": lambda chat: chat.get_topic_starters(),
    "copy a suggestion": lambda chat: chat.copy_and_log("好的"),
    "manual reply": lambda chat: (chat.manual_reply_text.insert("1.0", "好的"), chat.send_manual_reply()),
    "undo": lambda chat: chat.undo_last_entry(),
    "close": lambda chat: chat.on_close(),
}


@pytest.mark.parametrize("action", ACTIONS.values(), ids=ACTIONS.keys())
def test_no_action_drops_a_prompt_edit_while_a_number_field_is_unparsable(chat, monkeypatch, action):
    for dialog in ("askyesno", "askyesnocancel"):
        monkeypatch.setattr(app.messagebox, dialog, lambda *a, **k: True)
    monkeypatch.setattr(app.messagebox, "showerror", lambda *a, **k: None)
    monkeypatch.setattr(app.simpledialog, "askstring", lambda *a, **k: "小明的副本")
    open_contact(chat, "小红")
    open_contact_with_history(chat, "小明", "在吗")
    chat.prompt_text.insert("1.0", "新的提示词")
    chat.reply_count_var.set("")  # mid-retype

    action(chat)

    assert chat.prompt_text.get("1.0", tk.END).startswith("新的提示词")
    assert len(chat.contact_data["history"]) == 1


def test_a_failed_reply_log_keeps_the_manual_reply_text(chat, monkeypatch):
    monkeypatch.setattr(app.messagebox, "showerror", lambda *a, **k: None)
    open_contact(chat, "小明")
    chat.reply_count_var.set("")
    chat.manual_reply_text.insert("1.0", "好的")

    chat.send_manual_reply()

    assert chat.manual_reply_text.get("1.0", tk.END).strip() == "好的"


def test_copy_puts_the_suggestion_on_the_clipboard_and_logs_it(chat):
    open_contact(chat, "小明")

    chat.copy_and_log("好的")

    assert chat.clipboard_get() == "好的"
    assert data_manager.load_contact_data("小明")["history"] == [{"role": "assistant", "content": "好的"}]


def test_clicking_the_open_contact_again_keeps_the_suggestions(chat):
    open_contact(chat, "小明")
    chat.display_suggestions(["好呀"])

    select(chat, "小明")

    assert chat.suggestions_container.winfo_children()
