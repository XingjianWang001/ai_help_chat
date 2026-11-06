"""Gemini API access: configuration, model discovery and reply generation."""
import json
import os
import shutil
from concurrent.futures import ThreadPoolExecutor

from google import genai
from google.genai import errors, types

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "config.json")

DEFAULT_MODEL = "gemini-flash-latest"
# Used when the model list cannot be fetched from the API.
FALLBACK_MODELS = [
    "gemini-flash-latest",
    "gemini-3.8-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash-lite",
    "gemini-4-argon",
]
# Models matching these are not text-chat models (speech, images, robotics...).
NON_CHAT_MODEL_KEYWORDS = (
    "tts", "image", "transcribe", "robotics", "computer-use",
    "embedding", "customtools", "nano-banana", "omni",
)
REQUEST_TIMEOUT_MS = 30_000

EMOTIONAL_SUPPORT_INSTRUCTION = (
    "【情感支持模式】对方此刻可能需要情感上的支持。请优先倾听和共情，"
    "认可对方的感受，给予温暖的支持与鼓励；不要急于说教或给出解决方案。"
)
TOPIC_STARTER_NUDGE = "（对话陷入了沉默，请直接给出一条用来开启新话题的消息。）"

API_KEY = None
GLOBAL_PROMPT = ""
MODEL_NAME = DEFAULT_MODEL

# Models that rejected candidate_count > 1 during this session.
_single_candidate_models = set()


def load_app_config():
    """Load global settings from config.json; GEMINI_API_KEY env var overrides the file."""
    global API_KEY, GLOBAL_PROMPT, MODEL_NAME
    config = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8-sig") as f:  # -sig: Notepad may add a BOM
                config = json.load(f)
        except (ValueError, OSError) as e:  # ValueError covers bad JSON and non-UTF-8 files
            print(f"读取 config.json 时出错: {e}")
        if not isinstance(config, dict):
            print("读取 config.json 时出错: 文件内容不是 JSON 对象")
            config = {}

    API_KEY = os.environ.get("GEMINI_API_KEY") or config.get("gemini_api_key")
    if API_KEY == "YOUR_API_KEY_HERE":
        API_KEY = None
    GLOBAL_PROMPT = config.get("global_prompt")
    if not isinstance(GLOBAL_PROMPT, str): GLOBAL_PROMPT = ""  # hand-edited null or number
    MODEL_NAME = config.get("model_name") or DEFAULT_MODEL


def save_app_config(model_name, global_prompt):
    """Persist global settings, keeping any other keys (e.g. the API key) intact."""
    config = {}
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8-sig") as f:
            config = json.load(f)
    config.setdefault("gemini_api_key", "YOUR_API_KEY_HERE")
    config["model_name"] = model_name
    config["global_prompt"] = global_prompt
    # Write a temp file and swap it in, so a failed write never truncates the API key.
    tmp_path = CONFIG_FILE + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            if os.path.exists(CONFIG_FILE): shutil.copymode(CONFIG_FILE, tmp_path)  # keep a chmod 600, before the key is written
            json.dump(config, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, CONFIG_FILE)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    load_app_config()


def _client():
    if not API_KEY:
        raise RuntimeError(
            "未配置 Gemini API 密钥：请在 config.json 中填写 gemini_api_key，或设置环境变量 GEMINI_API_KEY。"
        )
    return genai.Client(
        api_key=API_KEY,
        http_options=types.HttpOptions(timeout=REQUEST_TIMEOUT_MS),
    )


def fetch_available_models():
    """Return the names of Gemini models that support generateContent, or None on failure."""
    try:
        client = _client()  # keep a reference: the pager needs the client alive
        names = []
        for model in client.models.list():
            actions = model.supported_actions or []
            name = (model.name or "").removeprefix("models/")
            if (
                "generateContent" in actions
                and name.startswith("gemini")
                and not any(word in name for word in NON_CHAT_MODEL_KEYWORDS)
            ):
                names.append(name)
        return sorted(set(names)) or None
    except Exception as e:
        print(f"获取模型列表失败，使用内置列表: {e!r}")
        return None


def _to_contents(history):
    return [
        types.Content(
            role="user" if msg["role"] == "user" else "model",
            parts=[types.Part(text=msg["content"])],
        )
        for msg in history
    ]


def _extract_texts(response):
    texts = []
    for candidate in response.candidates or []:
        parts = candidate.content.parts if candidate.content else None
        text = "".join(p.text for p in parts or [] if p.text and not p.thought)
        if text.strip():
            texts.append(text.strip())
    return texts


def _generate(system_instruction, contents, settings):
    """Ask Gemini for `reply_count` alternative replies.

    Some models reject candidate_count > 1; for those the replies come from
    parallel single-candidate requests.
    """
    client = _client()
    model_name = settings.get("model_name") or MODEL_NAME
    reply_count = min(max(1, int(settings.get("reply_count", 3))), 8)  # up to one request per reply
    temperature = float(settings.get("temperature", 0.7))

    def request(n):
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            candidate_count=n,
            temperature=temperature,
        )
        response = client.models.generate_content(model=model_name, contents=contents, config=config)
        return _extract_texts(response)

    print(f"正在请求 Gemini API (模型: {model_name}, 数量: {reply_count}, 创造力: {temperature})...")
    texts = []
    if reply_count > 1 and model_name not in _single_candidate_models:
        try:
            return request(reply_count)  # the model takes candidate_count: fewer or no replies (blocked) is the answer
        except errors.ClientError as e:
            # Only a rejected request (400) means the model can't do candidate_count > 1;
            # retrying a quota error (429) as several requests would only make it worse.
            if e.code != 400:
                raise
            # A bad key or prompt is also a 400; only a single-candidate request that works blames candidate_count.
            texts = request(1)
            print(f"多候选请求失败，改为逐条请求: {e!r}")
            _single_candidate_models.add(model_name)
            if not texts: return []  # the prompt was blocked: the other single requests would be too

    missing = reply_count - len(texts)
    if missing > 0:
        with ThreadPoolExecutor(max_workers=missing) as pool:
            futures = [pool.submit(request, 1) for _ in range(missing)]
        failures = [f.exception() for f in futures if f.exception()]
        for f in futures:
            if not f.exception(): texts.extend(f.result())
        if failures:
            if not texts: raise failures[0]  # keep the replies we got; fail only if there are none
            print(f"{len(failures)} 条回复请求失败: {failures[0]!r}")
    return texts[:reply_count]


def _system_instruction(task_prompt, settings):
    parts = [GLOBAL_PROMPT, f"当前对话任务提示词:\n{task_prompt}"]
    if settings.get("emotional_support"):
        parts.append(EMOTIONAL_SUPPORT_INSTRUCTION)
    return "\n\n---\n\n".join(p for p in parts if p.strip())


def get_reply_suggestions(contact_prompt, history, settings):
    """Generate reply suggestions for the latest message from the friend."""
    return _generate(_system_instruction(contact_prompt, settings), _to_contents(history), settings)


def get_topic_starter_suggestions(topic_starter_prompt, history, settings):
    """Generate suggestions for starting a new topic."""
    contents = _to_contents(history)
    if not contents or contents[-1].role != "user":
        contents.append(types.Content(role="user", parts=[types.Part(text=TOPIC_STARTER_NUDGE)]))
    return _generate(_system_instruction(topic_starter_prompt, settings), contents, settings)


load_app_config()
