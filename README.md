# Repr CLI

A local-first developer tool that turns your git commit history into professional narratives.

**Privacy Guarantee:** Zero data leaves your machine unless you explicitly publish. Your keys, your models, your data.

[![PyPI version](https://img.shields.io/pypi/v/repr-cli.svg)](https://pypi.org/project/repr-cli/)
[![Python versions](https://img.shields.io/pypi/pyversions/repr-cli.svg)](https://pypi.org/project/repr-cli/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Build](https://github.com/repr-app/cli/actions/workflows/build-release.yml/badge.svg)](https://github.com/repr-app/cli/actions/workflows/build-release.yml)

## Philosophy

Repr is built on three core principles:

1.  **Local-First:** Analysis happens on your machine. You own the output.
2.  **Bring Your Own Keys:** Use your own OpenAI API key or a local LLM (Ollama, etc.). We don't sit in the middle.
3.  **Opt-In Cloud:** Publishing to `repr.dev` is strictly optional. Use it for backup or sharing, or ignore it entirely.

## Installation

### macOS / Linux (Homebrew)
```bash
brew tap repr-app/tap
brew install repr
```

### Direct Download
Download pre-built binaries for macOS, Linux, and Windows from the [latest release](https://github.com/repr-app/cli/releases/latest).

### Python (pipx)
```bash
pipx install repr-cli
```

## The Local Workflow

You can use Repr entirely offline or with your own API keys. No account required.

### 1. Analyze a repository
Generate commit stories from your local git history.

```bash
# Using a local LLM (e.g., Ollama running Llama 3)
repr analyze ~/code/my-project --local --model llama3

# Or using your own OpenAI key
export OPENAI_API_KEY=sk-...
repr analyze ~/code/my-project --local --model gpt-4o
```

This reads your git log, diffs, and file context to generate meaningful summaries of your work. All processing happens locally or directly against the API you specify.

### 2. Inspect your stories
View the generated stories stored on your machine.

```bash
repr stories --repo my-project
```

Output is stored in `~/.repr/`, staying fully under your control.

### 3. Track multiple repositories
You can configure Repr to watch multiple projects.

```bash
repr repos add ~/code/work-project
repr repos add ~/code/side-project
```

## Optional: Cloud & Publishing

If you want to back up your stories or create a public profile (e.g., `repr.dev/yourname`), you can sync your local data to the cloud.

**This is the only time data leaves your machine.**

### 1. Authenticate
```bash
repr login
```

### 2. Sync
Push your locally generated stories to your private cloud storage.

```bash
repr sync
```

### 3. Automate (Optional)
Install git hooks to automatically analyze and sync new commits as you work.

```bash
repr hook install --all
```

## Configuration

Repr respects standard environment variables and local configuration.

**Config file:** `~/.repr/config.json`

### Using Local LLMs (Ollama, LocalAI)
Point Repr to any OpenAI-compatible endpoint:

```bash
repr config-set --api-base http://localhost:11434/v1 --model llama3
```

### Privacy Modes

| Mode | Command | Behavior |
|------|---------|----------|
| **Local LLM** | `repr analyze --local` | Uses your local LLM endpoint. Zero external network calls. |
| **BYOK** | `repr analyze --local` | Connects directly to OpenAI/Anthropic using your key. |
| **Offline** | `repr analyze --offline` | Metrics only. No LLM, no network. |
| **Cloud** | `repr analyze` | **(Requires Login)** Uses Repr's managed LLM backend. |

## Command Reference

- `repr analyze <path>`: Analyze a repo and generate stories.
- `repr stories`: List generated stories.
- `repr repos list|add|remove`: Manage tracked repositories.
- `repr config`: View current configuration.
- `repr sync`: Upload local stories to repr.dev (requires login).
- `repr whoami`: Check login status.

## License

MIT License - see [LICENSE](LICENSE).
