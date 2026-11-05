# ChatMate

**English** | [简体中文](README.zh-CN.md)

ChatMate is a small desktop assistant that helps you reply to friends in any chat app. Paste in what a friend just said and it uses Google Gemini to draft several replies in *your* voice, based on a persona you define and your recent conversation with that friend. It can also suggest messages to restart a conversation that has gone quiet.

Built with Python and Tkinter. The interface is in Chinese.

## Features

- **Per-friend profiles.** Each friend has their own prompt, settings and chat history, stored as a local JSON file.
- **Global persona.** One global prompt describes who "you" are. It is combined with each friend's prompt.
- **Multiple reply suggestions.** Choose how many drafts to generate and how creative they should be. One click copies a draft to the clipboard and logs it to the history.
- **Topic starters.** Generate an icebreaker based on the conversation so far.
- **Undo.** 撤销最后一条 (undo last entry) removes the last history entry, e.g. a draft picked by mistake or a message pasted into the wrong friend, so it isn't sent to the model again.
- **Emotional support mode.** Tells the model to listen and empathise first, rather than lecture or jump to solutions.
- **Adjustable context window.** Choose how many past messages are sent to the model.
- **Live model list.** Available Gemini models are fetched from the API at startup, with a built-in fallback list.

## How it works

You keep chatting in your usual app (WeChat, QQ, …). ChatMate is a side window:

1. Select a friend and paste their latest message into the input box. Press Enter or click **发送** (Send).
2. ChatMate shows several suggested replies on the right.
3. Click **复制并选用** (Copy & use) to copy a reply to your clipboard and save it to the history. Then paste it into your chat app. You can also type your own reply under **手动回复** (Manual reply).

In the history, "user" messages are your friend's and "assistant" messages are yours.

## Requirements

- Python 3.9+ (Tkinter included; on Linux you may need `python3-tk`)
- A Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey)

## Getting started

```bash
git clone https://github.com/XingjianWang001/ai_help_chat.git
cd ai_help_chat
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

cp config.example.json config.json   # then edit config.json
python app.py
```

### API key

Use either of these:

- Put it in `config.json` as `gemini_api_key`, or
- Set the `GEMINI_API_KEY` environment variable. It takes precedence over the file.

`config.json` is git-ignored, so your key will not be committed.

### Example contact

To try the app with sample data, copy the example contact into `contacts/`:

```bash
mkdir -p contacts
cp contacts.example/*.json contacts/
```

## Configuration

| Where | Setting | Meaning |
| --- | --- | --- |
| `config.json` / 全局设置 (Global settings) | `model_name` | Default Gemini model (`gemini-flash-latest` by default) |
| | `global_prompt` | Your general persona, shared by all friends |
| Per friend | 好友专属提示词 (Friend prompt) | Who this friend is, your relationship, reply style |
| | 主动破冰提示词 (Topic starter prompt) | Instructions used by **开启新话题** (New topic) |
| | 回复数 (Reply count) | Number of suggestions to generate |
| | 上下文 (Context) | Number of recent messages sent to the model |
| | 模型 / 创造力 (Model / Creativity) | Model and temperature (0–1) for this friend; 跟随全局默认 (follow global default) uses the default model, including after you change it |
| | 情感支持模式 (Emotional support mode) | Adds an empathy-first instruction |

If a friend's model is no longer offered by the API, that friend falls back to 跟随全局默认.

## Project structure

```
app.py             Tkinter UI
ai_handler.py      Gemini API calls, config loading, model discovery
data_manager.py    Contact file CRUD (contacts/*.json)
config.example.json
contacts.example/  Sample contact
```

## Privacy

Your contacts and chat history are stored only on your machine, in `contacts/`, which is git-ignored. When you request suggestions, the recent messages and prompts are sent to the Google Gemini API.

## License

[MIT](LICENSE)
