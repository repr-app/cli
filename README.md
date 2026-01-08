# Repr CLI

**Stop trying to remember what you did.** Your git history is already a career diary—repr unlocks it.

Turn commits into professional narratives for interviews, performance reviews, and career growth. Local-first, privacy-focused, works offline.

[![PyPI version](https://img.shields.io/pypi/v/repr-cli.svg)](https://pypi.org/project/repr-cli/)
[![Python versions](https://img.shields.io/pypi/pyversions/repr-cli.svg)](https://pypi.org/project/repr-cli/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Build](https://github.com/repr-app/cli/actions/workflows/build-release.yml/badge.svg)](https://github.com/repr-app/cli/actions/workflows/build-release.yml)

## Real Developers, Real Results

> *"I used repr to prep for my Meta interview in 30 minutes. Turned 2 years of commits into 8 STAR-format stories. Nailed every behavioral question."*  
> **— Sarah, Senior Backend Engineer**

> *"Our sprint demos went from chaos to polished in 5 minutes. Just run `repr commits --days 14` and export. Stakeholders love it."*  
> **— Marcus, Engineering Manager**

> *"I run repr in a fully air-gapped environment. Zero network calls, 100% local. It's the only tool I trust for this."*  
> **— Alex, Defense Contractor**

## Perfect For

- 🎯 **Interview Prep** — Generate STAR-format stories in 30 minutes instead of hours of commit archaeology
- 📊 **Performance Reviews** — Turn 6 months of work into quantified impact with one command
- 🚀 **Sprint Demos** — Professional changelogs for stakeholders in seconds
- 👔 **Weekly 1-on-1s** — Show up with specific examples instead of vague "I worked on stuff"
- 🔒 **Sensitive Work** — Air-gapped support for defense, healthcare, finance
- 💼 **Engineering Managers** — Prep for team reviews with per-developer summaries

## Why Repr

### Privacy First (Not an Afterthought)

- ✅ **Local-first by default** — Your repos, diffs, and stories stay on your machine in `~/.repr/`
- ✅ **Air-gapped ready** — Works in fully offline environments (defense, healthcare, finance approved)
- ✅ **Bring your own model** — Use local LLMs (Ollama) or your own API keys (OpenAI/Anthropic)
- ✅ **Privacy audit** — See exactly what data (if any) left your machine with `repr privacy audit`
- ✅ **OS keychain** — API keys never touch config files, stored in system keychain
- ✅ **Zero telemetry** — No tracking, no analytics, no silent uploads

### Time Savings

| Task | Without repr | With repr | Savings |
|------|--------------|-----------|---------|
| Interview prep | 3-4 hours digging through commits | 30 minutes | **85% faster** |
| Performance review | 2 days remembering work | 5 minutes | **99% faster** |
| Sprint demo prep | 30 min asking "what did we ship?" | 2 minutes | **93% faster** |
| Weekly 1-on-1 prep | 15 min trying to remember | 30 seconds | **97% faster** |

### vs. Alternatives

**vs. Manual brag documents:**  
❌ Requires discipline to maintain  
❌ Easy to forget to update  
❌ No structure or templates  
✅ repr: Automatic, retroactive, professional templates

**vs. GitHub commit history:**  
❌ Raw commits are cryptic  
❌ No narrative or context  
❌ Not interview/resume ready  
✅ repr: LLM transforms commits into narratives

**vs. Trying to remember at review time:**  
❌ Forget 80% of your work  
❌ Can't quantify impact  
❌ Miss your best stories  
✅ repr: Never forget, always quantified

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
repr commits --days 7
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
repr commits --days 7
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

### Generate from a specific timeframe

```bash
# Last 30 days
repr generate --days 30 --local

# Since a specific date
repr generate --since 2024-01-01 --local

# Natural language dates
repr generate --since "2 weeks ago" --local
repr generate --since monday --local
```

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
| **Offline** | `repr commits` / `repr stories` | Pure local operations. |

## Command help

For the full flag reference:

```bash
repr --help
repr <command> --help
```

## Enterprise & Compliance

### Air-Gapped Environments

repr works in fully offline, air-gapped environments:

```bash
# 1. Install repr (transfer binary via USB)
# 2. Install Ollama and download models offline
# 3. Lock to local-only permanently
repr privacy lock-local --permanent

# 4. Generate stories (zero network calls)
repr generate --local
```

**Use cases:**
- Defense contractors (classified environments)
- Healthcare (HIPAA compliance)
- Finance (SOX/PCI requirements)
- Stealth startups (pre-launch confidentiality)

### Privacy Audit Trail

See exactly what data left your machine:

```bash
repr privacy audit --days 30
```

Output:
```
Network Activity Audit (Last 30 days)

No network activity detected.

Local operations:
  • 143 commits analyzed
  • 23 stories generated  
  • 0 cloud syncs
  • 0 API calls to repr.dev

Mode: LOCAL_ONLY (locked)
```

Perfect for security audits and compliance reviews.

### BYOK (Bring Your Own Key)

Use your own API keys, stored securely:

```bash
# Keys stored in OS keychain (never in config files)
repr llm add openai
repr llm add anthropic

# Calls go directly to your provider, not repr.dev
repr generate  # Uses your OpenAI key
```

- ✅ Keys stored in macOS Keychain / Windows Credential Manager / Linux Secret Service
- ✅ repr.dev never sees your keys or data
- ✅ Full control over costs and models

## Documentation

- **[Full Documentation](https://repr.dev/docs)** — Comprehensive guides
- **[USER_WORKFLOWS.md](docs/USER_WORKFLOWS.md)** — 10 detailed workflow examples
- **[Privacy Model](https://repr.dev/docs/concepts/privacy-model)** — How data is protected

## License

MIT License — see [LICENSE](LICENSE).

---

**🚀 Ready to unlock your git history?**

```bash
brew install repr
repr init ~/code
repr generate --local
```
