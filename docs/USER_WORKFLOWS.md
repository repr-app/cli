# Repr CLI: User Workflows & Journeys

**Version:** 1.1  
**Date:** January 28, 2026  
**For:** repr CLI v0.2.0+

## The Context Layer Model

repr is the **developer context layer** — it captures what you build and makes it available everywhere. The workflows below are different **lenses** into the same underlying context:

| Lens | Workflow | What It Produces |
|------|----------|------------------|
| **Interview** | [Job Interview Prep](#4-preparing-for-a-job-interview) | STAR-format behavioral stories |
| **Resume** | Weekly Reflection | Career narratives, quantified impact |
| **Changelog** | Team/Manager Review | Sprint summaries, release notes |
| **Content** | Build in Public | Social posts from commits |
| **AI Context** | MCP Integration | Persistent context for coding agents |

All lenses use the same captured stories — just different views.

---

This document describes common user workflows and journeys for the repr CLI. Each journey shows the typical commands a user would run for different goals.

---

## Table of Contents

1. [First-Time Setup (New User)](#1-first-time-setup-new-user)
2. [Daily Developer Workflow](#2-daily-developer-workflow)
3. [Weekly Reflection](#3-weekly-reflection)
4. [Preparing for a Job Interview](#4-preparing-for-a-job-interview)
5. [Publishing Your Profile](#5-publishing-your-profile)
6. [Privacy-Focused Workflow (Local Only)](#6-privacy-focused-workflow-local-only)
7. [Multi-Device Sync](#7-multi-device-sync)
8. [Team Lead / Manager Review](#8-team-lead--manager-review)
9. [Data Backup & Migration](#9-data-backup--migration)
10. [Troubleshooting & Diagnostics](#10-troubleshooting--diagnostics)

---

## 1. First-Time Setup (New User)

**Goal:** Get repr set up and generate your first stories from existing work.

### Journey

```bash
# Step 1: Install repr (via pipx recommended)
pipx install repr-cli

# Step 2: Initialize - scans for repos and sets up config
repr init ~/code

# Output:
# Found 12 repositories
# ✓ myproject (143 commits) [Python]
# ✓ frontend-app (87 commits) [TypeScript]
# ...
# Track these repositories? [Y/n]

# Step 3: See what you've been working on (preview, no save)
repr week

# Step 4: Generate your first stories locally
repr generate --local

# Output:
# Generating stories (local LLM)...
# myproject
#   • Built OAuth2 integration with Google and GitHub providers
#   • Implemented Redis caching layer for session management
# Generated 2 stories
# Stories saved to: ~/.repr/stories

# Step 5: View your generated stories
repr stories

# Step 6: (Optional) Sign in to enable cloud features
repr login
```

### Key Commands Used

| Command | Purpose |
|---------|---------|
| `repr init [path]` | First-time setup, discover repos |
| `repr week` | Preview recent work |
| `repr generate --local` | Create stories using local LLM |
| `repr stories` | View generated stories |
| `repr login` | Enable cloud sync (optional) |

---

## 2. Daily Developer Workflow

**Goal:** Automatically capture your daily work with minimal friction.

### Journey A: Automatic Hook-Based Capture

```bash
# One-time setup: Install git hooks in your repos
repr hooks install --all

# Now, every git commit is automatically queued
# (The hook runs silently, no network calls)

# At end of day/week, generate stories from queued commits
repr generate --local

# Review what was generated
repr stories --needs-review

# Interactive review workflow
repr review
# [a] Approve  [e] Edit  [r] Regenerate  [d] Delete  [s] Skip  [q] Quit
```

### Journey B: Manual Daily Standup

```bash
# Morning: Quick standup summary (last 3 days)
repr standup

# Output:
# 📊 Work since last 3 days
# myproject (8 commits):
#   • Add user authentication flow
#   • Fix session timeout bug
#   • Implement rate limiting
# Total: 8 commits

# This summary wasn't saved. Run with --save to create a story.
```

### Journey C: End-of-Day Capture

```bash
# Check what you did today
repr since "this morning"

# Save it as a story
repr since "this morning" --save

# Or generate from specific commits
repr commits --limit 5
# Shows recent commits with SHAs

repr generate --commits abc1234,def5678,ghi9012
```

### Key Commands Used

| Command | Purpose |
|---------|---------|
| `repr hooks install --all` | Set up auto-capture |
| `repr generate` | Create stories from queued commits |
| `repr standup` | Quick 3-day summary |
| `repr since <date>` | Work since specific time |
| `repr review` | Interactive story review |

---

## 3. Weekly Reflection

**Goal:** Review your week's work and create a polished summary.

### Journey

```bash
# Step 1: See the week's overview
repr week

# Step 2: Generate stories from the week
repr generate --local --batch-size 10

# Step 3: Review and edit stories
repr stories
repr story view 01ARYZ6S41TSV4RRFFQ69G5FAV
repr story edit 01ARYZ6S41TSV4RRFFQ69G5FAV  # Opens in $EDITOR

# Step 4: Mark best stories as featured
repr story feature 01ARYZ6S41TSV4RRFFQ69G5FAV

# Step 5: Export a weekly summary
repr profile export --format md --since 2026-01-01 > weekly-summary.md
```

### Different Template Options

```bash
# For resume/portfolio-style summaries (default)
repr generate --template resume

# For technical changelog format
repr generate --template changelog

# For blog/case study narrative
repr generate --template narrative

# For interview preparation
repr generate --template interview
```

### Template Comparison

| Template | Best For | Output Style |
|----------|----------|--------------|
| `resume` | Portfolios, resumes | Action verbs, quantified impact |
| `changelog` | Release notes | Added/Changed/Fixed categories |
| `narrative` | Blog posts | Storytelling, problem-solving journey |
| `interview` | Job interviews | STAR format (Situation/Task/Action/Result) |

---

## 4. Preparing for a Job Interview

**Goal:** Create interview-ready stories from your actual work using the STAR format.

### Journey

```bash
# Step 1: Generate interview-style stories
repr generate --template interview --local

# Step 2: Review the STAR-format stories
repr stories

# Step 3: View a specific story
repr story view 01ARYZ6S41TSV4RRFFQ69G5FAV

# Output will be in STAR format:
# **Situation:** The authentication system was experiencing...
# **Task:** I needed to implement a more robust...
# **Action:** I designed and implemented...
# **Result:** Reduced authentication failures by 60%...

# Step 4: Feature your best stories
repr story feature 01ARYZ6S41TSV4RRFFQ69G5FAV

# Step 5: Export to bring to the interview
repr profile export --format md > interview-prep.md

# Step 6: Generate from specific projects
repr generate --repo ~/code/important-project --template interview
```

### Tips for Interview Prep

```bash
# Generate stories with extra context via custom prompt
repr generate --template interview --prompt "Focus on leadership and technical decision-making"

# Filter stories by technology
repr stories --json | jq '.[] | select(.technologies | contains(["Python"]))'

# Export only featured stories
repr stories --json | jq '[.[] | select(.is_featured == true)]'
```

---

## 5. Publishing Your Profile

**Goal:** Create a public developer profile at repr.dev.

### Journey

```bash
# Step 1: Sign in (required for cloud features)
repr login

# Step 2: Set up your profile
repr profile set-bio "Full-stack engineer specializing in distributed systems"
repr profile set-location "San Francisco, CA"
repr profile set-available true

# Step 3: Review what you'll publish
repr stories
repr story hide 01ARYZ...  # Hide sensitive stories
repr story feature 01BEST...  # Feature best work

# Step 4: Preview before publishing
repr push --dry-run

# Output:
# Publishing 12 story(ies) to repr.dev...
#   • Built OAuth2 integration with Google/GitHub
#   • Implemented Redis caching layer
#   • Fixed race condition in auth flow
# Run without --dry-run to publish

# Step 5: Publish your stories
repr push --all

# Step 6: Get your profile link
repr profile link
# Your profile: https://repr.dev/@yourusername
```

### Managing What's Public

```bash
# Hide a story from your public profile
repr story hide 01SENSITIVE_STORY_ID

# Feature a story (pins to top)
repr story feature 01BEST_STORY_ID

# Check privacy settings
repr privacy explain

# See what data has been sent to cloud
repr privacy audit
```

---

## 6. Privacy-Focused Workflow (Local Only)

**Goal:** Use repr entirely offline with maximum privacy.

### Journey

```bash
# Step 1: Check current privacy mode
repr mode

# Step 2: Lock to local-only mode (reversible)
repr privacy lock-local

# Or permanently disable cloud features
repr privacy lock-local --permanent

# Step 3: Configure local LLM
repr llm configure

# Detects Ollama automatically, or enter custom endpoint
# Available models:
#   1. llama3.2
#   2. codellama
# Select: 1

# Step 4: Test local LLM connection
repr llm test

# Output:
# Local LLM:
#   ✓ Connection successful
#   Provider: Ollama
#   Model: llama3.2
#   Response time: 234ms

# Step 5: Generate stories locally (default when not signed in)
repr generate --local

# Step 6: Review privacy guarantees
repr privacy explain

# Output:
# ARCHITECTURE:
#   ✓ No background daemons or silent uploads
#   ✓ All network calls are foreground, user-initiated
#   ✓ No telemetry by default (opt-in only)
#
# LOCAL MODE NETWORK POLICY:
#   Allowed: 127.0.0.1, localhost, ::1 (loopback only)
#   Blocked: All external network
```

### Using Your Own API Keys (BYOK)

```bash
# Add your own OpenAI key (never stored in config, uses OS keychain)
repr llm add openai
# API Key: ****

# Or Anthropic, Groq, Together AI
repr llm add anthropic
repr llm add groq
repr llm add together

# Set as default
repr llm use byok:openai

# Generate using your own key
repr generate
```

---

## 7. Multi-Device Sync

**Goal:** Keep stories synchronized across multiple computers.

### Journey: Setting Up New Device

```bash
# On new device:

# Step 1: Install repr
pipx install repr-cli

# Step 2: Initialize
repr init ~/code

# Step 3: Login with same account
repr login
# Uses device flow - no password entry in terminal

# Step 4: Pull stories from cloud
repr sync

# Output:
# Syncing with repr.dev...
# ↓ 23 remote stories to pull
# ↑ 0 local stories to push
# All stories synced
```

### Ongoing Sync Workflow

```bash
# Before starting work: pull latest
repr pull

# Do your work, generate stories locally
repr generate --local

# At end of session: push new stories
repr push

# Or do both at once
repr sync
```

### Handling Conflicts

```bash
# Check sync status
repr status

# Output:
# Auth: ✓ Signed in as user@example.com
# Tracked repos: 5
# Stories: 45 (3 unpushed)

# See what would be pushed
repr push --dry-run

# Push specific story
repr push --story 01ARYZ6S41TSV4RRFFQ69G5FAV
```

---

## 8. Team Lead / Manager Review

**Goal:** Review team member contributions for performance reviews or project retrospectives.

### Journey

```bash
# Step 1: Track the relevant project repos
repr repos add ~/code/team-project-1
repr repos add ~/code/team-project-2

# Step 2: Generate summaries from project activity
repr generate --repo ~/code/team-project-1 --template changelog

# Step 3: Filter by date range
repr since "2025-10-01"

# Step 4: Export project summaries
repr profile export --format md --since 2025-10-01 > Q4-review.md

# Step 5: View commits for specific period
repr commits --repo team-project-1 --since 2025-10-01

# Step 6: Generate narrative for retrospective
repr generate --repo ~/code/team-project-1 --template narrative
```

### Creating Project Changelogs

```bash
# Generate changelog-style stories
repr generate --template changelog

# Export as markdown
repr profile export --format md > CHANGELOG.md

# Or JSON for programmatic use
repr profile export --format json > project-data.json
```

---

## 9. Data Backup & Migration

**Goal:** Back up all data or migrate to a new machine.

### Journey: Backup

```bash
# Step 1: Check what you have
repr data

# Output:
# Local Data
# Stories: 45 files (2.1 MB)
# Profiles: 3 files (340 KB)
# Cache: 120 KB
# Config: 8 KB
# Total: 2.6 MB
# Location: /Users/me/.repr/stories

# Step 2: Create full backup
repr data backup --output ~/backups/repr-backup-2026-01-05.json

# Output:
# Backup saved to /Users/me/backups/repr-backup-2026-01-05.json
#   Stories: 45
#   Profiles: 3
```

### Journey: Restore on New Machine

```bash
# Step 1: Install repr on new machine
pipx install repr-cli

# Step 2: Copy backup file to new machine
# (via USB, cloud storage, etc.)

# Step 3: Restore from backup (merge with any existing)
repr data restore ~/backups/repr-backup-2026-01-05.json --merge

# Or replace everything
repr data restore ~/backups/repr-backup-2026-01-05.json --replace
```

### Housekeeping

```bash
# Clear cache (keeps stories and config)
repr data clear-cache

# Check storage usage
repr data
```

---

## 10. Troubleshooting & Diagnostics

**Goal:** Diagnose and fix issues with repr.

### Journey: Health Check

```bash
# Run full diagnostics
repr doctor

# Output:
# Checking repr health...
#
# ✓ Config: valid (v3)
# ✓ Stories: 45 files, no corruption
# ✓ Local LLM: Ollama (llama3.2)
# ✓ Git: 2.40.0
# ⚠ Tracked repos: 1 missing (/old/path/repo)
#
# Recommendations:
#   1. Remove missing repo: repr repos remove /old/path/repo
```

### Common Issues

```bash
# Issue: "Local LLM not found"
# Solution: Install Ollama and pull a model
ollama pull llama3.2
repr llm test

# Issue: "Not authenticated"
repr login
# Or check if token is valid
repr whoami

# Issue: "Repository not tracked"
repr repos list
repr repos add ~/code/my-repo

# Issue: "Hook not working"
repr hooks status
repr hooks install --repo ~/code/my-repo

# Issue: Corrupted config
repr config edit  # Opens in $EDITOR

# Issue: Check what mode you're in
repr mode

# Issue: See full configuration
repr config show
repr config show llm.default
```

### Debugging Commands

```bash
# Check version
repr --version

# Check auth status
repr whoami --json

# Check repo tracking status
repr repos --json

# Check hook queue
repr hooks status --json

# View raw config
repr config show --json

# Check privacy audit
repr privacy audit --days 7 --json
```

---

## Quick Reference: Command Cheatsheet

### Setup & Status

```bash
repr init [path]           # First-time setup
repr status                # Overall health
repr mode                  # Execution mode
repr doctor                # Full diagnostics
repr whoami                # Current user
```

### Story Generation

```bash
repr generate --local      # Generate with local LLM
repr generate --cloud      # Generate with cloud LLM
repr generate --template X # Use template (resume/changelog/narrative/interview)
repr generate --dry-run    # Preview what would be sent
```

### Quick Summaries

```bash
repr week                  # Last 7 days
repr standup               # Last 3 days
repr since "monday"        # Since specific date
repr since "3 days ago" --save  # Save as story
```

### Story Management

```bash
repr stories               # List all stories
repr story view <id>       # View story content
repr story edit <id>       # Edit in $EDITOR
repr story delete <id>     # Delete story
repr story hide <id>       # Hide from profile
repr story feature <id>    # Pin to profile top
repr review                # Interactive review
```

### Repository Management

```bash
repr repos                 # List tracked repos
repr repos add <path>      # Add repo
repr repos remove <path>   # Remove repo
repr repos pause <path>    # Pause tracking
repr repos resume <path>   # Resume tracking
```

### Hooks

```bash
repr hooks install --all   # Install in all repos
repr hooks remove --all    # Remove from all repos
repr hooks status          # Check hook status
```

### Cloud Operations

```bash
repr login                 # Sign in
repr logout                # Sign out
repr push                  # Publish stories
repr push --dry-run        # Preview push
repr sync                  # Bidirectional sync
repr pull                  # Pull from cloud
```

### LLM Configuration

```bash
repr llm configure         # Interactive setup
repr llm test              # Test connection
repr llm add <provider>    # Add BYOK provider
repr llm remove <provider> # Remove BYOK
repr llm use <mode>        # Set default (local/cloud/byok:X)
```

### Privacy

```bash
repr privacy explain       # Privacy summary
repr privacy audit         # What was sent to cloud
repr privacy lock-local    # Disable cloud
repr privacy unlock-local  # Re-enable cloud
```

### Profile & Export

```bash
repr profile               # View profile
repr profile export --format md   # Export as Markdown
repr profile export --format json # Export as JSON
repr profile link          # Get public URL
```

### Data Management

```bash
repr data                  # Storage stats
repr data backup -o FILE   # Create backup
repr data restore FILE     # Restore from backup
repr data clear-cache      # Clear cache
```

### Configuration

```bash
repr config show           # Show all config
repr config show llm.default  # Show specific key
repr config set key value  # Set value
repr config edit           # Open in $EDITOR
```

### Smart Git Workflow

```bash
repr add <pattern>         # Stage files matching pattern (regex)
repr unstage <pattern>     # Unstage files matching pattern (regex)
repr branch                # Create branch (AI generates name)
repr branch feat/name      # Create branch with explicit name
repr commit                # Generate message and commit
repr commit -m "msg"       # Commit with custom message
repr push                  # Push to remote
repr pr                    # Create PR (AI title/body)
repr changes               # Show unstaged/staged/unpushed changes
repr changes --explain     # With AI explanations
repr clear                 # Clear cached branch/commit info
```

---

*Last updated: February 1, 2026 — For repr CLI v0.2.16*








































