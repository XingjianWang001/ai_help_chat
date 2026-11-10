import queue
import threading
import tkinter as tk
from tkinter import ttk, simpledialog, messagebox, Text, Frame, Label, Button, Entry, StringVar, OptionMenu, Scale

import ai_handler
import data_manager

# Contact model menu entry meaning "no model_name saved": the contact uses whatever the global default is.
FOLLOW_DEFAULT = "跟随全局默认"

class ChatMateApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ChatMate - AI 聊天助手")
        self.geometry("1100x750")

        self.current_contact = None
        self.contact_data = None

        self.MODELS = list(ai_handler.FALLBACK_MODELS)
        self.models_from_api = False
        self.busy = False
        self.settings_window = None
        # Worker threads must not touch Tk; they post callbacks here instead.
        self.ui_queue = queue.Queue()

        top_bar = Frame(self, pady=5)
        Button(top_bar, text="全局设置", command=self.open_global_settings).pack(side=tk.LEFT, padx=10)
        top_bar.pack(fill=tk.X)

        self.paned_window = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self.paned_window.pack(fill=tk.BOTH, expand=True)

        contacts_frame = Frame(self.paned_window, width=200)
        self.contacts_listbox = tk.Listbox(contacts_frame, exportselection=False)
        self.contacts_listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.contacts_listbox.bind("<<ListboxSelect>>", self.on_contact_select)
        btn_frame = Frame(contacts_frame)
        Button(btn_frame, text="新建", command=self.new_contact).pack(side=tk.LEFT, expand=True, fill=tk.X)
        Button(btn_frame, text="复制", command=self.duplicate_contact).pack(side=tk.LEFT, expand=True, fill=tk.X)
        Button(btn_frame, text="删除", command=self.delete_contact).pack(side=tk.LEFT, expand=True, fill=tk.X)
        btn_frame.pack(fill=tk.X, padx=5, pady=5)
        self.paned_window.add(contacts_frame, weight=1)

        chat_frame = Frame(self.paned_window, width=550)
        settings_container = Frame(chat_frame)
        settings_container.pack(fill=tk.X, padx=5, pady=5)

        s_frame1 = Frame(settings_container)
        Label(s_frame1, text="回复数:").pack(side=tk.LEFT)
        self.reply_count_var = StringVar()
        Entry(s_frame1, textvariable=self.reply_count_var, width=5).pack(side=tk.LEFT, padx=5)
        Label(s_frame1, text="上下文:").pack(side=tk.LEFT)
        self.context_lookback_var = StringVar()
        Entry(s_frame1, textvariable=self.context_lookback_var, width=5).pack(side=tk.LEFT, padx=5)
        s_frame1.pack(fill=tk.X)

        s_frame2 = Frame(settings_container)
        Label(s_frame2, text="模型:").pack(side=tk.LEFT)
        self.model_var = StringVar()
        self.model_menu = OptionMenu(s_frame2, self.model_var, FOLLOW_DEFAULT, *self.MODELS)
        self.model_menu.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)
        s_frame2.pack(fill=tk.X, pady=2)

        s_frame3 = Frame(settings_container)
        Label(s_frame3, text="创造力:").pack(side=tk.LEFT)
        self.temp_var = tk.DoubleVar(value=0.7)
        Scale(s_frame3, from_=0.0, to=1.0, resolution=0.1, orient=tk.HORIZONTAL, variable=self.temp_var).pack(side=tk.LEFT, expand=True, fill=tk.X)
        s_frame3.pack(fill=tk.X, pady=2)

        s_frame4 = Frame(settings_container)
        self.emo_var = tk.BooleanVar()
        tk.Checkbutton(s_frame4, text="情感支持模式", variable=self.emo_var).pack(side=tk.LEFT)
        s_frame4.pack(fill=tk.X, pady=2)

        Label(chat_frame, text="好友专属提示词:").pack(anchor=tk.W, padx=5)
        self.prompt_text = Text(chat_frame, height=4, wrap=tk.WORD)
        self.prompt_text.pack(fill=tk.X, padx=5, pady=5)

        Label(chat_frame, text="主动破冰提示词:").pack(anchor=tk.W, padx=5)
        self.topic_starter_prompt_text = Text(chat_frame, height=4, wrap=tk.WORD)
        self.topic_starter_prompt_text.pack(fill=tk.X, padx=5, pady=5)

        self.history_text = Text(chat_frame, wrap=tk.WORD, state=tk.DISABLED, font=("Arial", 11))
        self.history_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.history_text.tag_config("user", foreground="#0000AA", justify=tk.RIGHT, rmargin=10)
        self.history_text.tag_config("assistant", foreground="#007700", lmargin1=10, lmargin2=10)

        input_frame = Frame(chat_frame)
        self.input_entry = Entry(input_frame, font=("Arial", 11))
        self.input_entry.pack(fill=tk.X, expand=True, side=tk.LEFT, ipady=5)
        self.input_entry.bind("<Return>", self.send_message)
        self.send_button = Button(input_frame, text="发送", command=self.send_message)
        self.send_button.pack(side=tk.RIGHT, padx=5)
        self.topic_button = Button(input_frame, text="开启新话题", command=self.get_topic_starters)
        self.topic_button.pack(side=tk.RIGHT)
        self.undo_button = Button(input_frame, text="撤销最后一条", command=self.undo_last_entry)
        self.undo_button.pack(side=tk.RIGHT, padx=5)
        input_frame.pack(fill=tk.X, padx=5, pady=5)
        self.paned_window.add(chat_frame, weight=3)

        suggestions_frame = Frame(self.paned_window, width=350)
        Label(suggestions_frame, text="AI 回复建议").pack()
        self.suggestions_container = Frame(suggestions_frame)
        self.suggestions_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        manual_reply_frame = Frame(suggestions_frame, pady=10)
        Label(manual_reply_frame, text="或手动回复:").pack(anchor=tk.W)
        self.manual_reply_text = Text(manual_reply_frame, height=3, wrap=tk.WORD)
        self.manual_reply_text.pack(fill=tk.X, expand=True, pady=5)
        Button(manual_reply_frame, text="发送手动回复", command=self.send_manual_reply).pack()
        manual_reply_frame.pack(fill=tk.X, padx=5, side=tk.BOTTOM)
        self.paned_window.add(suggestions_frame, weight=2)

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.refresh_contacts_list()
        threading.Thread(target=self._fetch_models, daemon=True).start()
        self.poll_ui_queue()

    def poll_ui_queue(self):
        try:
            while True:
                try:
                    callback = self.ui_queue.get_nowait()
                except queue.Empty:
                    break
                callback()
        finally:
            self.after(100, self.poll_ui_queue)  # one failing callback must not stop every later reply

    def _fetch_models(self):
        models = ai_handler.fetch_available_models()
        if models:
            self.ui_queue.put(lambda: self._apply_models(models))

    def _apply_models(self, models):
        if ai_handler.DEFAULT_MODEL not in models:
            models.insert(0, ai_handler.DEFAULT_MODEL)
        self.MODELS = models
        self.models_from_api = True
        set_option_menu_items(self.model_menu, self.model_var, [FOLLOW_DEFAULT, *self.MODELS])
        if self.model_var.get():
            self.model_var.set(self.resolve_model(self.model_var.get()))
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.show_models(self.settings_window.model_var.get())  # it was built from the old list

    def resolve_model(self, model_name):
        """The contact's menu value: its pinned model, or FOLLOW_DEFAULT if none is pinned or the API no longer offers it."""
        if model_name in (None, "", FOLLOW_DEFAULT):
            return FOLLOW_DEFAULT
        if self.models_from_api and model_name not in self.MODELS:
            print(f"模型 {model_name} 已不可用，改用全局默认模型")
            return FOLLOW_DEFAULT
        return model_name

    def refresh_contacts_list(self, select_contact=None):
        self.contacts_listbox.delete(0, tk.END)
        contacts = data_manager.get_all_contacts()
        for contact in contacts: self.contacts_listbox.insert(tk.END, contact)
        if select_contact in contacts:
            idx = contacts.index(select_contact)
            self.contacts_listbox.selection_set(idx)
            self.contacts_listbox.activate(idx)
            self.on_contact_select(None)

    def on_contact_select(self, event):
        selection = self.contacts_listbox.curselection()
        if not selection: return
        name = self.contacts_listbox.get(selection[0])
        if name == self.current_contact and self.contact_data: return  # a re-click: keep the suggestions on screen
        if self.contact_data and not self.save_settings():
            # stay on the contact being left so its unsaved edits can be fixed instead of lost
            return self.reselect_current_contact()
        data = data_manager.load_contact_data(name)
        if data is None:
            messagebox.showerror("错误", f"无法读取好友 '{name}' 的数据，文件可能已损坏。")
            return self.reselect_current_contact()
        self.current_contact, self.contact_data = name, data
        self.update_ui_for_contact()

    def reselect_current_contact(self):
        names = self.contacts_listbox.get(0, tk.END)
        self.contacts_listbox.selection_clear(0, tk.END)
        if self.current_contact in names: self.contacts_listbox.selection_set(names.index(self.current_contact))

    def update_ui_for_contact(self):
        self.clear_suggestions()
        self.prompt_text.delete("1.0", tk.END)
        self.topic_starter_prompt_text.delete("1.0", tk.END)
        self.history_text.config(state=tk.NORMAL)
        self.history_text.delete("1.0", tk.END)
        if not self.contact_data:  # deleted or unreadable: don't keep showing the previous contact
            self.history_text.config(state=tk.DISABLED)
            for var in (self.reply_count_var, self.context_lookback_var, self.model_var): var.set("")
            self.temp_var.set(0.7)
            self.emo_var.set(False)
            self.input_entry.delete(0, tk.END)
            return
        settings = self.contact_data.get("settings", {})
        self.reply_count_var.set(settings.get("reply_count", 3))
        self.context_lookback_var.set(settings.get("context_lookback", 10))
        self.model_var.set(self.resolve_model(settings.get("model_name")))
        self.temp_var.set(settings.get("temperature", 0.7))
        self.emo_var.set(settings.get("emotional_support", False))
        self.prompt_text.insert("1.0", self.contact_data.get("prompt", ""))
        self.topic_starter_prompt_text.insert("1.0", self.contact_data.get("topic_starter_prompt", data_manager.DEFAULT_TOPIC_STARTER_PROMPT))
        for msg in self.contact_data.get("history", []):
            align_tag = "user" if msg["role"] == "user" else "assistant"
            self.history_text.insert(tk.END, f"{msg['content']}\n\n", align_tag)
        self.history_text.config(state=tk.DISABLED)
        self.history_text.see(tk.END)

    def new_contact(self):
        name = simpledialog.askstring("新建好友", "请输入好友名称:", parent=self)
        if name:
            success, msg = data_manager.create_new_contact(name)
            if success: self.refresh_contacts_list(select_contact=name)
            else: messagebox.showerror("错误", msg)

    def duplicate_contact(self):
        if not self.current_contact: return
        name = simpledialog.askstring("复制好友", f"为 '{self.current_contact}' 的副本输入新名称:", parent=self)
        if name:
            if not self.save_settings(): return  # the copy is read from disk, so write pending edits first
            success, msg = data_manager.duplicate_contact(self.current_contact, name)
            if success: self.refresh_contacts_list(select_contact=name)
            else: messagebox.showerror("错误", msg)

    def delete_contact(self):
        if not self.current_contact: return
        if messagebox.askyesno("确认删除", f"确定要删除好友 '{self.current_contact}' 吗？"):
            success, msg = data_manager.delete_contact(self.current_contact)
            if success:
                self.current_contact = None
                self.contact_data = None
                self.refresh_contacts_list()
                self.update_ui_for_contact()
            else: messagebox.showerror("错误", msg)

    def ui_values(self):
        """The contact fields as the UI shows them; raises if a number field can't be parsed."""
        settings = dict(self.contact_data["settings"])
        settings["reply_count"] = int(self.reply_count_var.get())
        settings["context_lookback"] = int(self.context_lookback_var.get())
        settings["temperature"] = float(self.temp_var.get())
        settings["emotional_support"] = bool(self.emo_var.get())
        settings.pop("model_name", None)
        if self.model_var.get() not in ("", FOLLOW_DEFAULT): settings["model_name"] = self.model_var.get()
        return {
            "settings": settings,
            "prompt": self.prompt_text.get("1.0", tk.END).strip(),
            "topic_starter_prompt": self.topic_starter_prompt_text.get("1.0", tk.END).strip(),
        }

    def has_unsaved_changes(self):
        try:
            values = self.ui_values()
        except Exception:
            return True  # unparsable input is an edit the user should be asked about
        # Against the file, not memory: a history entry whose save failed is unsaved too.
        return {**self.contact_data, **values} != data_manager.load_contact_data(self.current_contact)

    def on_close(self):
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.on_close()
            if self.settings_window.winfo_exists(): return  # cancelled, or its save failed
        if self.contact_data and self.has_unsaved_changes():
            answer = messagebox.askyesnocancel("保存更改", f"是否保存对 '{self.current_contact}' 的更改？", parent=self)
            if answer is None: return
            if answer and not self.save_settings(): return
        self.destroy()

    def save_settings(self):
        if not self.contact_data: return False
        try:
            self.contact_data.update(self.ui_values())
            return self.save_contact()
        except Exception as e:
            messagebox.showerror("错误", f"保存设置失败: {e}")
            return False

    def save_contact(self):
        if data_manager.save_contact_data(self.current_contact, self.contact_data):
            return True
        messagebox.showerror("错误", "保存失败，聊天记录没有写入磁盘。请检查磁盘空间或文件权限。")
        return False

    def send_message(self, event=None):
        user_input = self.input_entry.get().strip()
        if self.busy or not user_input or not self.contact_data: return
        if not self.save_settings(): return

        self.contact_data["history"].append({"role": "user", "content": user_input})
        self.save_contact()
        self.update_ui_for_contact()
        self.input_entry.delete(0, tk.END)

        self.request_suggestions(ai_handler.get_reply_suggestions, self.contact_data["prompt"])

    def get_topic_starters(self):
        if self.busy or not self.contact_data: return
        if not self.save_settings(): return

        self.request_suggestions(ai_handler.get_topic_starter_suggestions, self.contact_data["topic_starter_prompt"])

    def request_suggestions(self, generate, prompt):
        """Run an API call on a worker thread so the UI stays responsive."""
        context_len = self.contact_data["settings"]["context_lookback"]
        context = self.contact_data["history"][-max(1, context_len):]
        settings = dict(self.contact_data["settings"])
        contact, history_len = self.current_contact, len(self.contact_data["history"])

        self.set_busy(True)

        def worker():
            try:
                result, error = generate(prompt, context, settings), None
            except Exception as e:
                result, error = [], e
            self.ui_queue.put(lambda: finish(result, error))

        def finish(result, error):
            self.set_busy(False)
            if contact != self.current_contact or len(self.contact_data["history"]) != history_len:
                return  # user switched contacts or logged a reply while waiting: the suggestions are stale
            if error:
                self.display_suggestions([], f"未能获取建议：{error}")
            else:
                self.display_suggestions(result)

        threading.Thread(target=worker, daemon=True).start()

    def set_busy(self, busy):
        self.busy = busy
        state = tk.DISABLED if busy else tk.NORMAL
        self.send_button.config(state=state)
        self.topic_button.config(state=state)
        self.undo_button.config(state=state)  # suggestions in flight were made for the current history
        if busy:
            self.clear_suggestions()
            Label(self.suggestions_container, text="生成中…").pack()

    def display_suggestions(self, suggestions, message="未能获取建议。"):
        self.clear_suggestions()
        if not suggestions:
            Label(self.suggestions_container, text=message, wraplength=280, justify=tk.LEFT).pack()
            return
        for suggestion in suggestions:
            frame = Frame(self.suggestions_container, pady=5)
            text = Text(frame, wrap=tk.WORD, height=4)
            text.insert("1.0", suggestion)
            text.config(state=tk.DISABLED)
            text.pack(fill=tk.X, expand=True)
            Button(frame, text="复制并选用", command=lambda s=suggestion: self.copy_and_log(s)).pack(pady=2)
            frame.pack(fill=tk.X)

    def clear_suggestions(self):
        for widget in self.suggestions_container.winfo_children(): widget.destroy()

    def copy_and_log(self, suggestion):
        if self.log_assistant_reply(suggestion):
            self.clipboard_clear()  # Tk's clipboard needs no xclip/xsel on Linux
            self.clipboard_append(suggestion)

    def undo_last_entry(self):
        if self.busy or not self.contact_data or not self.contact_data["history"]: return
        last = self.contact_data["history"][-1]
        preview = last["content"] if len(last["content"]) <= 100 else last["content"][:100] + "…"
        if not messagebox.askyesno("撤销", f"删除最后一条聊天记录？\n\n{preview}", parent=self): return
        if not self.save_settings(): return  # update_ui_for_contact would otherwise drop unsaved setting edits
        self.contact_data["history"].pop()
        if not self.save_contact():
            self.contact_data["history"].append(last)
            return
        self.update_ui_for_contact()

    def send_manual_reply(self):
        reply_text = self.manual_reply_text.get("1.0", tk.END).strip()
        if not reply_text or not self.contact_data: return
        if self.log_assistant_reply(reply_text): self.manual_reply_text.delete("1.0", tk.END)

    def log_assistant_reply(self, reply_content):
        if not self.save_settings(): return False  # update_ui_for_contact would drop the unsaved edits
        self.contact_data["history"].append({"role": "assistant", "content": reply_content})
        self.save_contact()
        self.update_ui_for_contact()
        return True

    def open_global_settings(self):
        # A second window would save its own stale copy over the first one's changes.
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.deiconify()
            self.settings_window.lift()
            return
        self.settings_window = GlobalSettingsWindow(self)

class GlobalSettingsWindow(tk.Toplevel):
    def __init__(self, controller):
        super().__init__(controller)
        self.controller = controller
        self.title("全局设置")
        self.geometry("600x450")
        ai_handler.load_app_config()
        model_frame = Frame(self, pady=10)
        Label(model_frame, text="默认 Gemini 模型:").pack(side=tk.LEFT, padx=5)
        self.model_var = StringVar()
        self.model_menu = OptionMenu(model_frame, self.model_var, "")
        self.model_menu.pack(side=tk.LEFT)
        self.show_models(ai_handler.MODEL_NAME)
        model_frame.pack(fill=tk.X, padx=10)
        Label(self, text="全局提示词 (定义你的通用人设):").pack(anchor=tk.W, padx=10)
        self.prompt_text = Text(self, wrap=tk.WORD)
        self.prompt_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.prompt_text.insert("1.0", ai_handler.GLOBAL_PROMPT)
        Button(self, text="保存全局设置", command=self.save_settings).pack(pady=10)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
    def show_models(self, model):
        """Offer the controller's model list, showing `model`, or DEFAULT_MODEL if the API doesn't offer it."""
        set_option_menu_items(self.model_menu, self.model_var, self.controller.MODELS)
        offered = not self.controller.models_from_api or model in self.controller.MODELS
        self.model_var.set(model if offered else ai_handler.DEFAULT_MODEL)
    def has_unsaved_changes(self):
        return (self.model_var.get(), self.prompt_text.get("1.0", tk.END).strip()) != (ai_handler.MODEL_NAME, ai_handler.GLOBAL_PROMPT)
    def on_close(self):
        if self.has_unsaved_changes():
            answer = messagebox.askyesnocancel("保存更改", "是否保存对全局设置的更改？", parent=self)
            if answer is None: return
            if answer: return self.save_settings()  # closes the window only if the save works
        self.destroy()
    def save_settings(self):
        try:
            ai_handler.save_app_config(self.model_var.get(), self.prompt_text.get("1.0", tk.END).strip())
            messagebox.showinfo("成功", "全局设置已保存。", parent=self)
            self.destroy()
        except Exception as e: messagebox.showerror("错误", f"保存失败: {e}", parent=self)

def set_option_menu_items(option_menu, variable, items):
    menu = option_menu["menu"]
    menu.delete(0, tk.END)
    for item in items:
        menu.add_command(label=item, command=tk._setit(variable, item))

if __name__ == "__main__":
    app = ChatMateApp()
    app.mainloop()
