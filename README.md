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

### 1. Initialize
Scan for repositories and set up local config.

```bash
repr init ~/code
```

### 2. Generate stories
Create stories from your commit history.

```bash
# Using a local LLM (e.g., Ollama running Llama 3)
repr generate --local

# Or configure your own API key (BYOK)
repr llm add openai
repr generate

# Or use cloud (requires login)
repr login
repr generate --cloud
```

This reads your git log, diffs, and file context to generate meaningful summaries of your work. All processing happens locally or directly against the API you specify.

### 3. View your stories
Inspect the generated stories stored on your machine.

```bash
repr stories
repr story view <id>
```

Output is stored in `~/.repr/`, staying fully under your control.

### 4. Track multiple repositories
Configure Repr to watch multiple projects.

```bash
repr repos add ~/code/work-project
repr repos add ~/code/side-project
```

## Optional: Cloud & Publishing

If you want convenience without managing your own API keys, you can use Repr's backend. It processes your code with proprietary models but operates under a **zero data retention (ZDR) policy**—no logging, no storage beyond ephemeral processing.

Alternatively, use the cloud for backup and sharing: sync your locally generated stories or create a public profile (e.g., `repr.dev/yourname`).

**This is the only time data leaves your machine.**

### 1. Authenticate
```bash
repr login
```

### 2. Push stories
Publish your locally generated stories to your profile.

```bash
repr push
```

### 3. Sync across devices
Keep your stories in sync.

```bash
repr sync
```

### 4. Automate (Optional)
Install git hooks to automatically track new commits as you work.

```bash
repr hooks install --all
```

## Configuration

Repr respects standard environment variables and local configuration.

**Config file:** `~/.repr/config.json`

### Using Local LLMs (Ollama, LocalAI)
Point Repr to any OpenAI-compatible endpoint:

```bash
repr llm configure
# Or manually:
repr config set llm.local_api_url http://localhost:11434/v1
repr config set llm.local_model llama3.2
```

### Bring Your Own Key (BYOK)
Configure your own API keys:

```bash
repr llm add openai
repr llm add anthropic
repr llm use byok:openai
```

### Privacy Modes

| Mode | Command | Behavior |
|------|---------|----------|
| **Local LLM** | `repr generate --local` | Uses your local LLM endpoint (Ollama, etc.). Zero external network calls. |
| **BYOK** | `repr llm add <provider>` | Configure your own API keys (OpenAI, Anthropic, etc.). Direct connection, no middleman. |
| **Cloud** | `repr generate --cloud` | **(Requires Login)** Uses Repr's backend. Sends metadata + diffs. Zero data retention (ZDR) policy—no logging, ephemeral processing only. |
| **Offline** | Local operations only | Works without network. View stories, repos, export profiles. |

## Command Reference

### Getting Started
- `repr init [path]` - Initialize repr, scan for repositories
- `repr login` - Authenticate with repr.dev
- `repr whoami` - Show current user
- `repr logout` - Sign out
- `repr status` - Show overall status and health
- `repr mode` - Show current execution mode
- `repr doctor` - Run health checks and diagnostics

### Generation & Analysis
- `repr generate [--local|--cloud]` - Generate stories from commits
  - `--repo <path>` - Generate for specific repo
  - `--commits <sha1,sha2>` - Generate from specific commits
  - `--template <name>` - Use template (resume, changelog, narrative, interview)
  - `--dry-run` - Preview what would be sent
- `repr week [--save]` - Show work from this week
- `repr since <date> [--save]` - Show work since a date
- `repr standup [--days N]` - Quick summary for standup

### Stories
- `repr stories [--repo NAME] [--needs-review]` - List all stories
- `repr story <action> <id>` - Manage a story (view, edit, delete, hide, feature)
- `repr review` - Interactive review workflow
- `repr commits [--repo NAME] [--limit N]` - List recent commits

### Cloud Operations
- `repr push [--story ID] [--all]` - Publish stories to repr.dev
- `repr sync` - Sync stories across devices
- `repr pull` - Pull remote stories to local

### Repositories
- `repr repos [list|add|remove|pause|resume] [path]` - Manage tracked repos

### Git Hooks
- `repr hooks install [--all|--repo PATH]` - Install post-commit hooks
- `repr hooks remove [--all|--repo PATH]` - Remove hooks
- `repr hooks status` - Show hook status

### LLM Configuration
- `repr llm add <provider>` - Configure BYOK provider (openai, anthropic, groq, together)
- `repr llm remove <provider>` - Remove BYOK provider
- `repr llm use <mode>` - Set default mode (local, cloud, byok:<provider>)
- `repr llm configure` - Configure local LLM interactively
- `repr llm test` - Test LLM connection

### Privacy
- `repr privacy explain` - Show privacy guarantees
- `repr privacy audit [--days N]` - Show what data was sent to cloud
- `repr privacy lock-local [--permanent]` - Disable cloud features
- `repr privacy unlock-local` - Re-enable cloud features

### Configuration
- `repr config show [key]` - Display configuration
- `repr config set <key> <value>` - Set configuration value
- `repr config edit` - Open config in $EDITOR

### Data Management
- `repr data` - Show local storage info
- `repr data backup [--output FILE]` - Backup all local data
- `repr data restore <file> [--merge]` - Restore from backup
- `repr data clear-cache` - Clear local cache

### Profile
- `repr profile` - View profile
- `repr profile update [--preview]` - Generate/update profile from stories
- `repr profile set-bio <text>` - Set profile bio
- `repr profile set-location <text>` - Set location
- `repr profile set-available <bool>` - Set availability status
- `repr profile export [--format FORMAT]` - Export profile (md, json)
- `repr profile link` - Get shareable profile link

## License

MIT License - see [LICENSE](LICENSE).
