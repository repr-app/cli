# Repr CLI

A privacy-first CLI that analyzes your git repositories to generate per-repo profiles, extract commit stories, and sync them to `repr.dev`.

[![PyPI version](https://img.shields.io/pypi/v/repr-cli.svg)](https://pypi.org/project/repr-cli/)
[![Python versions](https://img.shields.io/pypi/pyversions/repr-cli.svg)](https://pypi.org/project/repr-cli/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Build](https://github.com/repr-app/cli/actions/workflows/build-release.yml/badge.svg)](https://github.com/repr-app/cli/actions/workflows/build-release.yml)
[![Tests](https://github.com/repr-app/cli/actions/workflows/test.yml/badge.svg)](https://github.com/repr-app/cli/actions/workflows/test.yml)

## Install

### Option 1: Homebrew (macOS/Linux) 🍺

```bash
brew tap repr-app/tap
brew install repr
```

### Option 2: One-Line Installer (macOS/Linux) ⚡

```bash
curl -sSL https://repr.dev/install.sh | sh
```

### Option 3: Binary Download (No Python Required) 📦

Download pre-built binaries from the [latest release](https://github.com/repr-app/cli/releases/latest):

**macOS:**
```bash
curl -L https://github.com/repr-app/cli/releases/latest/download/repr-macos.tar.gz -o repr-macos.tar.gz
tar -xzf repr-macos.tar.gz
sudo mv repr /usr/local/bin/
```

**Linux:**
```bash
curl -L https://github.com/repr-app/cli/releases/latest/download/repr-linux.tar.gz -o repr-linux.tar.gz
tar -xzf repr-linux.tar.gz
sudo mv repr /usr/local/bin/
```

**Windows:**
Download `repr-windows.exe` from releases, rename to `repr.exe`, and add to your PATH.

### Option 4: Python Package Manager 🐍

Recommended (isolated):

```bash
pipx install repr-cli
```

Alternative:

```bash
pip install repr-cli
```

## Quick start

Authenticate (required for non-offline flows):

```bash
repr login
```

Analyze repositories (generates one profile per repo; pushes automatically):

```bash
repr analyze ~/code
```

View the latest profile:

```bash
repr view
```

## Privacy modes

| Mode | How | Notes |
|------|-----|-------|
| **Cloud** | `repr analyze <paths...>` | Requires `repr login` |
| **Local LLM** | `repr analyze <paths...> --local` | Uses OpenAI-compatible local endpoint |
| **Offline** | `repr analyze <paths...> --offline` | Metrics-only, no network, no push |

Local LLM examples:

```bash
repr analyze ~/code --local --model llama3.2
repr analyze ~/code --local --api-base http://localhost:11434/v1
```

## VS Code Extension integration (`--json`)

Several commands support `--json` for machine-readable output (no Rich formatting). This is intended for the VS Code extension / other integrations.

Examples:

```bash
repr analyze ~/code --json
repr status --json
repr whoami --json
repr repos list --json
repr stories --json
repr sync --json
repr hook status --json
```

## Commands

### Analyze + profiles

- `repr analyze <paths...>`: analyze repositories, save per-repo profiles, auto-push (unless `--offline`)
- `repr view [--profile NAME] [--raw] [--json]`: view latest (or named) profile
- `repr profiles [--json]`: list saved profiles
- `repr push [--profile NAME]`: push unsynced profiles

### Auth + status

- `repr login`: device-code login
- `repr logout`: clear auth
- `repr whoami [--json]`: show current user + public profile url (if set)
- `repr status [--json]`: health/status overview (auth, profiles, sync state)

### Stories + sync automation

- `repr stories [--repo NAME] [--since ...] [--technologies ...] [--limit N] [--json]`: list commit stories
- `repr repos list|add|remove|scan [--json]`: manage tracked repositories
- `repr sync [--repo PATH] [--all] [--background] [--json]`: analyze new commits and push updates for tracked repos
- `repr hook install|remove|status [--repo PATH|--all] [--json]`: manage post-commit hooks

### Configuration

- `repr config [--json]`: show config + endpoints
- `repr config-set [...]`: set LLM models / local endpoint defaults

Environment variables:

```bash
REPR_DEV=1         # enable dev mode (localhost backend)
REPR_API_BASE=URL  # override API base URL
```

Config + output locations:

```text
~/.repr/
  config.json
  profiles/
  cache/
```

## Requirements

- Python 3.10+
- Git
- For `--local`: an OpenAI-compatible local endpoint (e.g. Ollama)

## License

MIT License - see [LICENSE](LICENSE).
