# 🚀 ResumeFlow CLI

> A beautiful CLI that analyzes your code repositories and generates a compelling developer profile using AI.

[![PyPI version](https://img.shields.io/pypi/v/resumeflow.svg)](https://pypi.org/project/resumeflow/)
[![Python versions](https://img.shields.io/pypi/pyversions/resumeflow.svg)](https://pypi.org/project/resumeflow/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## ✨ Features

- 🤖 **AI-Powered Analysis** — Deep code understanding, not just stats
- 🔒 **Zero Data Retention** — Your code is analyzed but never stored
- 🏠 **Local LLM Support** — Use Ollama for completely local processing
- 📊 **Deep Repository Analysis** — Architecture, frameworks, complexity metrics
- 🎨 **Beautiful UI** — Rich terminal interface with progress indicators
- 📝 **Markdown Output** — Clean, readable profiles you can share anywhere

## 🔐 Privacy Options

Choose your privacy level:

| Mode | Description | Data Flow |
|------|-------------|-----------|
| **Cloud (ZDR)** | Zero Data Retention with cloud LLMs | Code sent → analyzed → immediately discarded |
| **Local** | Completely local with Ollama | Code never leaves your machine |
| **Offline** | Basic stats only, no AI | No network required |

### Zero Data Retention (Default)

When using cloud analysis:
- ✅ Code is sent over encrypted connections (TLS)
- ✅ Analysis happens in ephemeral containers
- ✅ **No code is ever stored or logged**
- ✅ LLM providers configured for zero retention
- ✅ Results returned, data discarded immediately

### Local LLM Mode

For complete local control:
```bash
# Use Ollama (recommended)
rf analyze ~/code --local --model llama3.2

# Use any OpenAI-compatible local server
rf analyze ~/code --local --api-base http://localhost:11434/v1
```

## 📸 Demo

```bash
$ rf analyze ~/code

╭──────────────────────────────────────────────────────────────╮
│  🚀  ResumeFlow CLI v0.1.0                                     │
╰──────────────────────────────────────────────────────────────╯

Discovering repositories...
Found 12 repositories in 1 path(s)

                        Analyzing                               
╭────────────────────┬──────────┬──────────┬──────────┬─────────╮
│ Repository         │ Language │  Commits │      Age │  Status │
├────────────────────┼──────────┼──────────┼──────────┼─────────┤
│ ecommerce-api      │ Python   │      340 │   1.5 yr │ ✓ Done  │
│ react-dashboard    │ TypeScript│     156 │   8 mo   │ ✓ Done  │
│ ml-experiments     │ Python   │      89 │   4 mo   │ ✓ Done  │
╰────────────────────┴──────────┴──────────┴──────────┴─────────╯

✓ Profile saved: ~/.resumeflow/profiles/2024-01-15.md
```

## 🚦 Quick Start

### Installation

```bash
pip install resumeflow
```

### For Local LLM (Optional)

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull a model
ollama pull llama3.2
```

### Usage

**Generate your profile (cloud, ZDR):**

```bash
# Analyze repos with cloud AI (zero data retention)
rf analyze ~/code
```

**Use local LLM:**

```bash
# Use Ollama locally
rf analyze ~/code --local

# Specify model
rf analyze ~/code --local --model codellama

# Use custom local endpoint
rf analyze ~/code --local --api-base http://localhost:1234/v1
```

**Offline mode (stats only):**

```bash
# No AI, no network - just code metrics
rf analyze ~/code --offline
```

**View your profile:**

```bash
rf view
rf view --raw > profile.md
```

## 🛠️ Commands

### `rf analyze`

Analyze repositories and generate a developer profile.

```bash
rf analyze <paths...> [OPTIONS]

Options:
  --local              Use local LLM (Ollama) instead of cloud
  --model NAME         Local model to use (default: llama3.2)
  --api-base URL       Custom local LLM API endpoint
  --offline            Stats only, no AI analysis
  --no-cache           Re-analyze all repositories
  --verbose, -V        Show detailed logs
```

### `rf view`

View your generated profile.

```bash
rf view [OPTIONS]

Options:
  --profile NAME  View a specific profile
  --raw, -r       Output plain markdown
```

### `rf login`

Authenticate for cloud analysis.

```bash
rf login
```

### `rf logout`

Clear authentication.

```bash
rf logout
```

### `rf push`

Upload profile to resumeflow.dev.

```bash
rf push [--profile NAME]
```

### `rf profiles`

List all saved profiles.

```bash
rf profiles
```

## ⚙️ Configuration

Config stored in `~/.resumeflow/config.json`:

```json
{
  "version": 1,
  "settings": {
    "default_paths": ["~/code"],
    "skip_patterns": ["node_modules", "venv", ".venv", "vendor", "__pycache__", ".git"]
  },
  "llm": {
    "extraction_model": "gpt-4o-mini",
    "synthesis_model": "gpt-4o",
    "local_api_url": "http://localhost:11434/v1",
    "local_api_key": "ollama"
  }
}
```

### Environment Variables

```bash
# Use local LLM by default
export RESUMEFLOW_LOCAL=true
export RESUMEFLOW_MODEL=codellama

# Custom Ollama endpoint
export OLLAMA_HOST=http://localhost:11434
```

## 🔍 What Gets Analyzed

The CLI performs deep analysis of your repositories:

**Code Metrics:**
- Lines of code, comments, complexity
- Function/class counts
- Average file and function sizes

**Architecture Detection:**
- Project type (web app, API, CLI, library, ML project)
- Architecture patterns (MVC, clean architecture, microservices)
- Framework detection (React, Django, FastAPI, etc.)

**Quality Indicators:**
- Test coverage and test frameworks
- Documentation presence and quality
- Docstring coverage

**Technical Stack:**
- Languages and percentages
- Dependencies and notable libraries
- API endpoints detection

## 📋 Requirements

- Python 3.10+
- Git
- For local mode: [Ollama](https://ollama.com/) or compatible LLM server

## 📁 Directory Structure

```
~/.resumeflow/
├── config.json          # Settings
├── profiles/            # Generated profiles
│   ├── 2024-01-15.md
│   └── 2024-01-20.md
└── cache/              # Analysis cache
```

## 🤝 Contributing

Contributions welcome! See [CONTRIBUTING.md](https://github.com/resumeflow/cli/blob/main/CONTRIBUTING.md).

```bash
git clone https://github.com/resumeflow-ai/cli.git
cd cli
pip install -e ".[dev]"
pytest
```

## 📄 License

MIT License - see [LICENSE](LICENSE).

## 🔗 Links

- [Website](https://resumeflow.dev)
- [Documentation](https://resumeflow.dev/docs)
- [GitHub](https://github.com/resumeflow/cli)

## 💬 Support

- Email: [hello@resumeflow.dev](mailto:hello@resumeflow.dev)
- Discord: [discord.gg/resumeflow](https://discord.gg/resumeflow)

---

<p align="center">
  Made with ❤️ by the ResumeFlow team
</p>
