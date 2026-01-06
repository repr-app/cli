# Repr CLI

A local-first developer tool that turns your git commit history into professional narratives.

**Privacy guarantee:** Zero data leaves your machine unless you explicitly publish. Your keys, your models, your data.

[![PyPI version](https://img.shields.io/pypi/v/repr-cli.svg)](https://pypi.org/project/repr-cli/)
[![Python versions](https://img.shields.io/pypi/pyversions/repr-cli.svg)](https://pypi.org/project/repr-cli/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Build](https://github.com/repr-app/cli/actions/workflows/build-release.yml/badge.svg)](https://github.com/repr-app/cli/actions/workflows/build-release.yml)

## Why Repr

- **Local-first by default**: Your repos, diffs, and stories live on your machine in `~/.repr/`.
- **Bring your own model**: Use a local LLM (Ollama/LocalAI) or your own API keys (OpenAI/Anthropic/etc.).
- **Opt-in cloud**: Publishing/sync is optional and always user-initiated.

## Install

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

## Quickstart (60 seconds)

```bash
# 1) Scan for repos and set up local config
repr init ~/code

# 2) Generate stories from your recent work (local LLM)
repr generate --local

# 3) View what was created
repr stories
repr story view <id>
```

## Workflows (how people actually use Repr)

The full journeys live in `docs/USER_WORKFLOWS.md`. The snippets below are the “happy paths”.

### First-time setup

```bash
repr init ~/code
repr week
repr generate --local
```

See: `docs/USER_WORKFLOWS.md#1-first-time-setup-new-user`

### Daily developer workflow

```bash
repr hooks install --all
repr generate --local
repr review
```

See: `docs/USER_WORKFLOWS.md#2-daily-developer-workflow`

### Weekly reflection

```bash
repr week
repr generate --local
repr story edit <id>
repr story feature <id>
```

See: `docs/USER_WORKFLOWS.md#3-weekly-reflection`

### Interview prep (STAR stories)

```bash
repr generate --template interview --local
repr stories
repr story view <id>
```

See: `docs/USER_WORKFLOWS.md#4-preparing-for-a-job-interview`

### Publishing your profile (optional)

```bash
repr login
repr push --dry-run
repr push --all
repr profile link
```

See: `docs/USER_WORKFLOWS.md#5-publishing-your-profile`

### Privacy-focused (local only)

```bash
repr privacy lock-local
repr llm configure
repr llm test
repr generate --local
```

See: `docs/USER_WORKFLOWS.md#6-privacy-focused-workflow-local-only`

### Multi-device sync

```bash
repr login
repr sync
```

See: `docs/USER_WORKFLOWS.md#7-multi-device-sync`

### Troubleshooting

```bash
repr status
repr mode
repr doctor
```

See: `docs/USER_WORKFLOWS.md#10-troubleshooting--diagnostics`

## Configure models

**Config file:** `~/.repr/config.json`

### Local LLM (Ollama/LocalAI)

```bash
repr llm configure

# or manually:
repr config set llm.local_api_url http://localhost:11434/v1
repr config set llm.local_model llama3.2
```

### Bring your own API keys (BYOK)

```bash
repr llm add openai
repr llm add anthropic
repr llm use byok:openai
```

### Privacy modes (mental model)

| Mode | Typical command | What happens |
|------|------------------|-------------|
| **Local LLM** | `repr generate --local` | Talks only to your local endpoint. |
| **BYOK** | `repr llm add <provider>` | Direct calls to your provider using your key. |
| **Cloud** | `repr generate --cloud` | Requires login; user-initiated network calls. |
| **Offline** | `repr week` / `repr stories` | Local operations only. |

## Command help

If you want the full flag reference:

```bash
repr --help
repr <command> --help
```

## License

MIT License — see [LICENSE](LICENSE).
