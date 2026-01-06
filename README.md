# Repr CLI

A local-first developer tool that turns your git commit history into professional narratives.

**Privacy guarantee:** Zero data leaves your machine unless you explicitly publish. Your keys, your models, your data.

[![PyPI version](https://img.shields.io/pypi/v/repr-cli.svg)](https://pypi.org/project/repr-cli/)
[![Python versions](https://img.shields.io/pypi/pyversions/repr-cli.svg)](https://pypi.org/project/repr-cli/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Build](https://github.com/repr-app/cli/actions/workflows/build-release.yml/badge.svg)](https://github.com/repr-app/cli/actions/workflows/build-release.yml)

## Why Repr

- **Local-first by default**: Your repos, diffs, and stories stay on your machine in `~/.repr/`.
- **Bring your own model**: Use a local LLM (Ollama/LocalAI) or your own API keys (OpenAI/Anthropic/etc.).
- **Opt-in cloud**: Publishing and sync are optional — you decide when data leaves your machine.

## Install

### macOS / Linux (Homebrew)

```bash
brew tap repr-app/tap
brew install repr
```

### Direct Download

Grab pre-built binaries for macOS, Linux, and Windows from the [latest release](https://github.com/repr-app/cli/releases/latest).

### Python (pipx)

```bash
pipx install repr-cli
```

## Quickstart (60 seconds)

```bash
# 1) Scan your repos and set up local config
repr init ~/code

# 2) Generate stories from your recent work (local LLM)
repr generate --local

# 3) See what you created
repr stories
repr story view <id>
```

## Common workflows

For full step-by-step guides, see the [documentation](https://repr.dev/docs/cli/workflows/). Below are the quick happy-path snippets.

### First-time setup

```bash
repr init ~/code
repr week
repr generate --local
```

[Full guide →](https://repr.dev/docs/cli/workflows/first-time-setup)

### Daily workflow

```bash
repr hooks install --all
repr generate --local
repr review
```

[Full guide →](https://repr.dev/docs/cli/workflows/daily-workflow)

### Weekly reflection

```bash
repr week
repr generate --local
repr story edit <id>
repr story feature <id>
```

[Full guide →](https://repr.dev/docs/cli/workflows/weekly-reflection)

### Interview prep (STAR stories)

```bash
repr generate --template interview --local
repr stories
repr story view <id>
```

[Full guide →](https://repr.dev/docs/cli/workflows/interview-prep)

### Publish your profile (optional)

```bash
repr login
repr push --dry-run
repr push --all
repr profile link
```

[Full guide →](https://repr.dev/docs/cli/workflows/publishing-profile)

### Privacy-focused (local only)

```bash
repr privacy lock-local
repr llm configure
repr llm test
repr generate --local
```

[Full guide →](https://repr.dev/docs/cli/workflows/privacy-local-only)

### Multi-device sync

```bash
repr login
repr sync
```

[Full guide →](https://repr.dev/docs/cli/workflows/multi-device-sync)

### Troubleshooting

```bash
repr status
repr mode
repr doctor
```

[Full guide →](https://repr.dev/docs/cli/workflows/troubleshooting)

## Configure your models

Your config lives at `~/.repr/config.json`.

### Local LLM (Ollama/LocalAI)

```bash
repr llm configure

# or set it manually:
repr config set llm.local_api_url http://localhost:11434/v1
repr config set llm.local_model llama3.2
```

### Bring your own API keys (BYOK)

```bash
repr llm add openai
repr llm add anthropic
repr llm use byok:openai
```

### Privacy modes

| Mode | Typical command | What happens |
|------|-----------------|--------------|
| **Local LLM** | `repr generate --local` | Talks only to your local endpoint. |
| **BYOK** | `repr llm add <provider>` | Calls your provider directly with your key. |
| **Cloud** | `repr generate --cloud` | Requires login; you initiate all network calls. |
| **Offline** | `repr week` / `repr stories` | Pure local operations. |

## Command help

For the full flag reference:

```bash
repr --help
repr <command> --help
```

## License

MIT License — see [LICENSE](LICENSE).
