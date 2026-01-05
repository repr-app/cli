# Repr CLI

A privacy-first CLI that converts your git commit history into a living professional profile at `repr.dev/{username}`. Track repositories, extract commit stories, and keep your profile automatically up-to-date.

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

### 1. Authenticate

```bash
repr login
```

### 2. Add repositories to track

```bash
# Add a specific repo or directory with multiple repos
repr repos add ~/code/myproject

# Or auto-discover repos in a directory
repr repos scan
```

### 3. Sync your work

```bash
# Sync all tracked repos (analyzes new commits and pushes stories)
repr sync

# Or sync just one repo
repr sync --repo ~/code/myproject
```

### 4. Optional: Enable automatic syncing

```bash
# Install git hooks for auto-sync on commit
repr hook install --all
```

### 5. View your stories

```bash
# List recent commit stories
repr stories

# Filter by repo or technology
repr stories --repo myproject --technologies React
```

### 6. Share your profile

```bash
# Get your public profile URL
repr whoami
```

Your profile lives at `repr.dev/{username}` and updates automatically as you work!

## Core workflow

The modern workflow uses **tracked repositories** for automatic syncing:

```bash
# 1. Add repos to track
repr repos add ~/code

# 2. Sync new commits (manual)
repr sync

# 3. Or install hooks for auto-sync on commit
repr hook install --all
```

Stories are synced to `repr.dev` and your public profile updates automatically.

## One-off analysis

For analyzing repos without tracking them:

```bash
# Analyze once and push (doesn't add to tracked list)
repr analyze ~/code/external-project
```

## Commands

### Repository tracking & syncing

- `repr repos list [--json]`: list tracked repositories with sync status
- `repr repos add <path>`: add repository or directory to tracking
- `repr repos remove <path>`: stop tracking a repository
- `repr repos scan`: auto-discover repos in configured paths
- `repr sync [--repo PATH] [--all] [--json]`: sync tracked repos (analyze new commits and push)

### Git hooks (auto-sync)

- `repr hook install [--repo PATH|--all]`: install post-commit hooks for auto-sync
- `repr hook remove [--repo PATH|--all]`: remove post-commit hooks
- `repr hook status [--json]`: show hook installation status

### Stories & data

- `repr stories [--repo NAME] [--since ...] [--technologies ...] [--limit N] [--json]`: list commit stories
- `repr analyze <paths...> [--json] [--since ...] [--offline] [--local]`: one-off analysis (auto-pushes unless `--offline`)

### Auth & status

- `repr login`: authenticate with repr.dev
- `repr logout`: clear authentication
- `repr whoami [--json]`: show user info and public profile URL
- `repr status [--json]`: health/status overview

### Configuration

- `repr config [--json]`: show config and endpoints
- `repr config-set [...]`: configure LLM models and local endpoints

Environment variables:

```bash
REPR_DEV=1         # enable dev mode (localhost backend)
REPR_API_BASE=URL  # override API base URL
```

Config location: `~/.repr/config.json`

## Privacy modes

For one-off analysis without cloud LLM:

| Mode | How | Notes |
|------|-----|-------|
| **Cloud** | `repr analyze <paths...>` | Default, requires `repr login` |
| **Local LLM** | `repr analyze <paths...> --local` | Uses OpenAI-compatible local endpoint |
| **Offline** | `repr analyze <paths...> --offline` | Metrics-only, no network, no push |

Local LLM examples:

```bash
repr analyze ~/code --local --model llama3.2
repr analyze ~/code --local --api-base http://localhost:11434/v1
```

## VS Code Extension integration

Commands support `--json` for machine-readable output (no Rich formatting):

```bash
repr repos list --json
repr stories --json
repr sync --json
repr status --json
repr whoami --json
repr hook status --json
```

## Requirements

- Python 3.10+
- Git
- For `--local`: an OpenAI-compatible local endpoint (e.g. Ollama)

## License

MIT License - see [LICENSE](LICENSE).
