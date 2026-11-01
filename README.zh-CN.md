# ChatMate

[English](README.md) | **简体中文**

ChatMate 是一个帮你回复朋友消息的桌面小助手，可以配合任何聊天软件使用。把朋友刚发来的话粘贴进来，它会调用 Google Gemini，根据你设定的人设和你们最近的聊天记录，用*你的*口吻生成几条回复草稿。聊天冷场时，它也能帮你想一句开启新话题的话。

基于 Python + Tkinter 开发。

## 功能

- **每个好友独立档案**：每位好友都有自己的提示词、参数和聊天记录，以 JSON 文件保存在本地。
- **全局人设**：用一段全局提示词描述"你是谁"，它会和每个好友的提示词组合使用。
- **多条回复建议**：可以设置生成几条、创造力高低。一键复制到剪贴板，同时记入聊天记录。
- **开启新话题**：根据已有对话，生成一句破冰的话。
- **情感支持模式**：让模型优先倾听和共情，不急于说教或给出解决方案。
- **上下文长度可调**：自己决定把最近多少条消息发给模型。
- **动态模型列表**：启动时从 API 获取可用的 Gemini 模型，失败时使用内置列表。

## 使用方式

你照常在微信、QQ 等软件里聊天，ChatMate 只是旁边的一个辅助窗口：

1. 选中好友，把对方的最新消息粘贴到输入框，按回车或点击 **发送**。
2. 右侧会出现几条回复建议。
3. 点击 **复制并选用**，回复会被复制到剪贴板并记入聊天记录，然后粘贴到聊天软件里发出即可。也可以在 **手动回复** 里自己写。

聊天记录中，`user` 是朋友说的话，`assistant` 是你的回复。

## 环境要求

- Python 3.9 及以上（需要自带 Tkinter；Linux 上可能需要安装 `python3-tk`）
- Gemini API Key，可在 [Google AI Studio](https://aistudio.google.com/apikey) 免费申请

## 快速开始

```bash
git clone https://github.com/XingjianWang001/ai_help_chat.git
cd ai_help_chat
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

cp config.example.json config.json   # 然后编辑 config.json
python app.py
```

### 配置 API Key

二选一：

- 在 `config.json` 的 `gemini_api_key` 字段里填写；或者
- 设置环境变量 `GEMINI_API_KEY`（优先级高于配置文件）。

`config.json` 已加入 `.gitignore`，不会被提交。

### 示例好友

想用示例数据体验，可以把示例好友复制到 `contacts/`：

```bash
mkdir -p contacts
cp contacts.example/*.json contacts/
```

## 配置说明

| 位置 | 设置项 | 含义 |
| --- | --- | --- |
| `config.json` / 全局设置 | `model_name` | 默认 Gemini 模型（默认是 `gemini-flash-latest`） |
| | `global_prompt` | 你的通用人设，所有好友共用 |
| 每个好友 | 好友专属提示词 | 这位好友是谁、你们的关系、回复风格 |
| | 主动破冰提示词 | 点击 **开启新话题** 时使用的指令 |
| | 回复数 | 生成几条建议 |
| | 上下文 | 发送给模型的最近消息条数 |
| | 模型 / 创造力 | 这位好友使用的模型和温度（0–1） |
| | 情感支持模式 | 追加一段"优先共情"的指令 |

如果保存的模型已经不在 API 提供的列表里，会自动改用默认模型。

## 项目结构

```
app.py             Tkinter 界面
ai_handler.py      Gemini API 调用、配置读取、模型列表获取
data_manager.py    好友文件的增删改查（contacts/*.json）
config.example.json
contacts.example/  示例好友
```

## 隐私

好友档案和聊天记录只保存在本机的 `contacts/` 目录，该目录已加入 `.gitignore`。请求回复建议时，最近的聊天内容和提示词会发送给 Google Gemini API。

## 许可证

[MIT](LICENSE)
