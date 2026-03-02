<div align="center">

# ⚡ SwiftAgent

### AI Task Automation Made Simple

**The easiest way to automate coding tasks with AI — no complex setup, no heavy frameworks.**

Run AI agents that write code, manage files, and execute commands — all from your browser.

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=flat&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18+-61DAFB?style=flat&logo=react&logoColor=black)](https://react.dev)
[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=flat)](LICENSE)

</div>

---

## What is SwiftAgent?

SwiftAgent is a **lightweight, self-hosted AI assistant** that runs in your browser. Describe a task in plain English, and SwiftAgent handles it for you — writing code, editing files, running commands, and more.

**No Electron. No native dependencies. Just Python + React.**

### Why SwiftAgent?

| Feature | SwiftAgent | Traditional AI agents |
|---|---|---|
| **Setup time** | 2 minutes | 30+ minutes |
| **Dependencies** | Python + Node.js | Electron, native C++ modules, etc. |
| **Memory usage** | ~50MB | 500MB+ (Electron + Chromium) |
| **LLM providers** | 7 built-in | Usually 1-2 |
| **Configuration** | Single `.env` file | Complex JSON configs |

---

## Supported AI Providers

SwiftAgent works with **7 major AI providers** out of the box. Use whichever you prefer:

| Provider | Models | Best For |
|---|---|---|
| **OpenAI** | GPT-4o, GPT-4o Mini | General-purpose, great all-rounder |
| **Anthropic** | Claude Sonnet 4, Opus 4.5, Haiku 3.5 | Complex reasoning, long documents |
| **Google Gemini** | Gemini 2.5 Flash, 2.5 Pro | Speed, large context windows (1M tokens) |
| **xAI** | Grok 3, Grok 3 Mini | Real-time knowledge, conversational |
| **DeepSeek** | DeepSeek Chat, Reasoner | Cost-effective, strong at code |
| **Z-AI** | GLM-4 Plus, GLM-4 | Multilingual, Chinese language support |
| **Ollama** | Any local model | Privacy, offline use, no API key needed |

> 💡 **Don't have an API key yet?** Use [Ollama](https://ollama.com) to run models locally for free — no account required.

---

## Quick Start (2 Minutes)

### Prerequisites

You only need two things installed on your computer:

- **Python 3.10+** — [Download Python](https://python.org/downloads/)
- **Node.js 18+** — [Download Node.js](https://nodejs.org/)

> 🤔 **Not sure if you have them?** Open a terminal and run:
> ```bash
> python --version    # Should show 3.10 or higher
> node --version      # Should show 18 or higher
> ```

### Step 1: Download SwiftAgent

```bash
git clone https://github.com/OthmaneBlial/swiftagent.git
cd swiftagent
```

> 📦 **Don't have Git?** You can also [download the ZIP](https://github.com/OthmaneBlial/swiftagent/archive/main.zip) and extract it.

### Step 2: Set Up Your AI Provider

Run the interactive setup wizard — it will guide you through everything:

```bash
make onboard
```

The wizard will:
1. **Show you all available AI providers** (OpenAI, Anthropic, Gemini, etc.)
2. **Ask for your API key** (you'll need one from your chosen provider)
3. **Let you pick a model** (or use the default)
4. **Save everything** to a `.env` file

> 🔑 **Where to get API keys:**
>
> | Provider | Get your key at |
> |---|---|
> | OpenAI | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
> | Anthropic | [console.anthropic.com](https://console.anthropic.com) |
> | Google Gemini | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) |
> | xAI | [console.x.ai](https://console.x.ai) |
> | DeepSeek | [platform.deepseek.com](https://platform.deepseek.com) |
> | Z-AI | [open.bigmodel.cn](https://open.bigmodel.cn) |
> | Ollama | No key needed — [install Ollama](https://ollama.com/download) |

### Step 3: Install Dependencies

```bash
make install
```

This installs both the Python backend and the React frontend. It takes about 30 seconds.

### Step 4: Start SwiftAgent

```bash
make dev
```

That's it! 🎉 Your browser will open to **http://localhost:5173** with SwiftAgent ready to use.

---

## How to Use

1. **Type a task** in the input box on the home page
2. **Press Enter** (or click the send button)
3. **Watch the AI work** — you'll see real-time updates as it thinks, writes code, and executes commands
4. **Review the results** — all task history is saved and accessible from the sidebar

### Example Tasks

```
Build a Python script that scrapes the top 10 Hacker News stories and saves them to a CSV file.
```

```
Create a REST API with FastAPI that has CRUD endpoints for a todo list with SQLite storage.
```

```
Find and fix the bug in my login.py file — users are getting 403 errors after password reset.
```

---

## All Commands

| Command | What it does |
|---|---|
| `make onboard` | 🧙 Interactive setup wizard — pick your AI provider, enter API key, choose model |
| `make onboard-show` | 📋 Show current configuration status (which providers are set up) |
| `make install` | 📦 Install all dependencies (Python + Node.js) |
| `make dev` | 🚀 Start SwiftAgent in development mode (server + client) |
| `make dev-server` | Start only the Python backend server |
| `make dev-client` | Start only the React frontend |
| `make start` | Start in production mode (server only) |
| `make test` | Run all tests |
| `make clean` | Remove build artifacts and caches |

---

## Configuration

### The `.env` File

All configuration lives in a single `.env` file in the project root. The `make onboard` command creates this for you automatically, but you can also edit it manually:

```env
# Which AI provider to use
LLM_PROVIDER=openai          # openai | xai | anthropic | gemini | deepseek | zai
LLM_MODEL=gpt-4o             # or "latest" for auto-select

# Your API key (set the one matching your provider)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GEMINI_API_KEY=AI...

# Server settings (optional — defaults work fine)
SWIFTAGENT_PORT=8000
SWIFTAGENT_HOST=127.0.0.1
```

> 🔒 **Security:** Your API keys are encrypted with AES-256-GCM before being stored. They never leave your machine.

### Switching Providers

Want to try a different AI provider? Just edit your `.env` file:

```env
LLM_PROVIDER=anthropic
LLM_MODEL=claude-sonnet-4-20250514
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

Or run `make onboard` again to use the interactive wizard.

### Check Your Config

Not sure what's configured? Run:

```bash
make onboard-show
```

You'll see a table showing which providers have API keys set up:

```
  ┌──────────────┬──────────────────────┬──────────┐
  │ Provider     │ Env Var              │ Status   │
  ├──────────────┼──────────────────────┼──────────┤
  │ openai       │ OPENAI_API_KEY       │ ✓ ready  │
  │ xai          │ XAI_API_KEY          │ ✗ empty  │
  │ anthropic    │ ANTHROPIC_API_KEY    │ ✓ ready  │
  │ gemini       │ GEMINI_API_KEY       │ ✗ empty  │
  │ deepseek     │ DEEPSEEK_API_KEY     │ ✗ empty  │
  │ zai          │ ZAI_API_KEY          │ ✗ empty  │
  │ ollama       │ (local)              │ ✓ local  │
  └──────────────┴──────────────────────┴──────────┘
```

---

## Using Ollama (Free, Local AI)

Don't want to pay for API keys? Use **Ollama** to run AI models locally on your own computer — completely free and private.

### Step 1: Install Ollama

Download from [ollama.com/download](https://ollama.com/download) (available for macOS, Linux, and Windows).

### Step 2: Pull a Model

```bash
ollama pull llama3.1        # 8B model, good balance of speed and quality
ollama pull codellama       # Specialized for coding tasks
ollama pull mistral         # Fast and capable
```

### Step 3: Configure SwiftAgent

```env
LLM_PROVIDER=ollama
LLM_MODEL=llama3.1
```

That's it — SwiftAgent will connect to your local Ollama instance automatically.

---

## Project Structure

```
swiftagent/
├── server/                  # Python backend (FastAPI)
│   ├── swiftagent/
│   │   ├── main.py          # App entry point
│   │   ├── cli.py           # Onboard CLI wizard
│   │   ├── config.py        # Environment config loader
│   │   ├── api/
│   │   │   ├── routes.py    # REST API endpoints
│   │   │   └── websocket.py # Real-time WebSocket handler
│   │   ├── models/          # Pydantic data models
│   │   ├── storage/         # SQLite + encrypted key storage
│   │   └── engine/          # Task execution engine
│   ├── pyproject.toml
│   └── requirements.txt
├── client/                  # React frontend (Vite)
│   ├── src/
│   │   ├── pages/           # Home, Execution, History
│   │   ├── components/      # Layout, shared UI
│   │   └── lib/             # API client, utilities
│   ├── tailwind.config.js
│   └── package.json
├── .env.example             # Config template
├── Makefile                 # All commands
└── README.md
```

---

## Tech Stack

| Component | Technology | Why |
|---|---|---|
| **Backend** | Python + FastAPI | Fast, modern, no native C++ deps |
| **Frontend** | React + Vite + Tailwind CSS | Instant hot reload, beautiful UI |
| **Database** | SQLite (Python stdlib) | Zero-config, embedded, reliable |
| **Real-time** | WebSockets | Live task streaming, instant updates |
| **Security** | AES-256-GCM encryption | API keys encrypted at rest |
| **Task runner** | asyncio subprocess | Lightweight process management |

---

## Troubleshooting

### "Command not found: make"

**On macOS:**
```bash
xcode-select --install
```

**On Ubuntu/Debian:**
```bash
sudo apt install build-essential
```

**On Windows:** Use [WSL](https://learn.microsoft.com/en-us/windows/wsl/install) (Windows Subsystem for Linux), then follow the Linux instructions.

### "Python not found" or wrong version

Make sure Python 3.10+ is installed and in your PATH:
```bash
python3 --version
```

If you have multiple Python versions, you may need to use `python3` instead of `python`.

### "npm: command not found"

Install Node.js from [nodejs.org](https://nodejs.org/). The LTS version is recommended.

### The browser doesn't open automatically

Navigate manually to **http://localhost:5173** after running `make dev`.

### API key errors

1. Check your key is correct: `make onboard-show`
2. Make sure the `.env` file is in the project root (not inside `server/` or `client/`)
3. Re-run `make onboard` to set up fresh

---

## API Reference

SwiftAgent exposes a REST API on port 8000 (configurable via `SWIFTAGENT_PORT`):

| Endpoint | Method | Description |
|---|---|---|
| `/health` | GET | Health check |
| `/api/tasks` | GET | List all tasks |
| `/api/tasks/{id}` | GET | Get a specific task |
| `/api/settings` | GET/PUT | App settings |
| `/api/providers` | GET | Active provider config |
| `/api/providers/catalog` | GET | All available providers with models |
| `/api/onboard/status` | GET | Which providers have keys configured |
| `/api/keys/{provider}` | GET/POST/DELETE | Manage API keys |
| `/ws` | WebSocket | Real-time task streaming |

---

## Contributing

Contributions are welcome! SwiftAgent is intentionally small and focused.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Commit your changes (`git commit -m 'Add my feature'`)
4. Push to the branch (`git push origin feature/my-feature`)
5. Open a Pull Request

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

<div align="center">

**Built with ❤️ by [Othmane BLIAL](https://github.com/OthmaneBlial)**

⭐ **Star this repo** if you find it useful!

</div>
