import os
import json

# --- Robust Pathing ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONTACTS_DIR = os.path.join(SCRIPT_DIR, "contacts")

DEFAULT_PROMPT = "你是一个乐于助人、言简意赅的朋友。"
DEFAULT_TOPIC_STARTER_PROMPT = "任务：对话陷入了沉默，请根据我们之前的聊天记录，生成一条可以用来打破僵局、开启新话题的消息。可以是提问、分享一个有趣的事，或者评论一下之前聊过的内容。请确保它自然、符合我的人设。"

# Characters that are path separators or not allowed in Windows file names.
INVALID_NAME_CHARS = set('/\\:*?"<>|')
# Windows treats these as devices, even with an extension (CON.json).
RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL"} | {f"{p}{i}" for p in ("COM", "LPT") for i in range(1, 10)}


def contact_name_error(contact_name):
    """名称可用作 contacts 目录下的文件名时返回 None，否则返回错误提示。"""
    if not contact_name.strip():
        return "好友名称不能为空。"
    if contact_name in (".", "..") or any(
        c in INVALID_NAME_CHARS or ord(c) < 32 for c in contact_name
    ):
        return '好友名称不能包含 / \\ : * ? " < > | 等字符。'
    if contact_name.upper() in RESERVED_NAMES or contact_name[-1] in ". ":
        return "好友名称不能是系统保留名（如 CON、NUL），也不能以点或空格结尾。"
    return None


def get_all_contacts():
    """扫描 contacts 目录，返回所有好友的名称列表。"""
    if not os.path.exists(CONTACTS_DIR):
        os.makedirs(CONTACTS_DIR)
    
    contacts = [f.removesuffix(".json") for f in os.listdir(CONTACTS_DIR) if f.endswith(".json")]
    return sorted(contacts)

def get_contact_path(contact_name):
    """获取指定好友的数据文件路径。"""
    return os.path.join(CONTACTS_DIR, f"{contact_name}.json")

def load_contact_data(contact_name):
    """加载指定好友的数据。如果文件不存在，返回 None。"""
    filepath = get_contact_path(contact_name)
    if not os.path.exists(filepath):
        return None
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # Older contact files may lack some keys.
        data.setdefault("prompt", DEFAULT_PROMPT)
        data.setdefault("topic_starter_prompt", DEFAULT_TOPIC_STARTER_PROMPT)
        data.setdefault("settings", {})
        data.setdefault("history", [])
        return data
    except (json.JSONDecodeError, IOError) as e:
        print(f"读取 {contact_name} 的数据时出错: {e}")
        return None

def save_contact_data(contact_name, data):
    """将好友数据保存到其 .json 文件中。"""
    filepath = get_contact_path(contact_name)
    # Write a temp file and swap it in, so a failed or interrupted write never truncates the history.
    tmp_path = filepath + ".tmp"
    try:
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, filepath)
        return True
    except IOError as e:
        print(f"保存 {contact_name} 的数据时出错: {e}")
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        return False

def create_new_contact(contact_name):
    """创建一个新的好友文件，并填入默认数据。"""
    error = contact_name_error(contact_name)
    if error:
        return False, error

    filepath = get_contact_path(contact_name)
    if os.path.exists(filepath):
        return False, "该好友已存在。"

    default_data = {
        "prompt": DEFAULT_PROMPT,
        "topic_starter_prompt": DEFAULT_TOPIC_STARTER_PROMPT,
        "settings": {
            "reply_count": 3,
            "context_lookback": 10,
            "temperature": 0.7,
            "emotional_support": False
        },
        "history": []
    }
    
    if save_contact_data(contact_name, default_data):
        return True, "创建成功。"
    else:
        return False, "创建文件时出错。"

def duplicate_contact(source_name, new_name):
    """复制一个已有的好友到新名称。"""
    error = contact_name_error(new_name)
    if error:
        return False, error

    new_filepath = get_contact_path(new_name)
    if os.path.exists(new_filepath):
        return False, "该名称的好友已存在。"

    source_data = load_contact_data(source_name)
    if source_data is None:
        return False, "源好友不存在或数据无法读取。"
    
    if save_contact_data(new_name, source_data):
        return True, "复制成功。"
    else:
        return False, "创建复制文件时出错。"

def delete_contact(contact_name):
    """删除指定好友的数据文件。"""
    filepath = get_contact_path(contact_name)
    if not os.path.exists(filepath):
        return False, "该好友不存在。"
    
    try:
        os.remove(filepath)
        return True, "删除成功。"
    except OSError as e:
        print(f"删除 {contact_name} 的文件时出错: {e}")
        return False, "删除文件时出错。"
