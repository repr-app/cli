# repr CLI - Complete Specification

**Last updated:** January 2026

---

## Core Principle

**repr helps you understand what you've actually worked on.**

Most developers don't work off detailed task lists. You push a few things forward, go by feel, and ship. That works great for getting things done — but it makes it surprisingly hard to answer basic questions afterward:

- What actually changed this week?
- What's worth mentioning vs. noise?
- What did I really accomplish?

repr bridges that gap by giving you grounded summaries of your work — not just for resumes or portfolios, but for standups, interviews, weekly reflection, and casual "what have you been up to?" conversations.

**Personal observability first. Sharing is optional.**

**repr has two execution modes (Data Boundary):**

| Mode | Auth required | Data leaves machine | Use cases |
|------|---------------|---------------------|-----------|
| **Local** | ❌ No | ❌ No | Personal reflection, private work, offline |
| **Cloud** | ✅ Yes | ✅ Yes | Sync across devices, publish, share |

**Inference Options:**
repr can generate stories using a local LLM (offline), repr-managed cloud inference (requires login), or BYOK using your own API keys (sends data directly to the provider).

**Mode availability:**
- Without login, only Local mode is available.
- With login, Cloud mode becomes available (unless Local-only lock is enabled).

**Architectural guarantee:**
> Without `repr login`, repr never contacts repr.dev or uploads anything.
> BYOK is optional and, when used, sends data directly to the provider.
> We enforce this in code, not policy.

This means you can use repr for introspection without committing to publishing. The privacy architecture enables personal reflection as the primary use case, with sharing as an optional add-on.

This guarantee is repeated everywhere: CLI help, error messages, docs, web copy.

---

## Vocabulary

**Key Terms:**

- **Summary**: Ephemeral output from `repr week`, `repr since`, or `repr standup` (not saved unless you use `--save`)
- **Story**: Persistent artifact saved as Markdown + metadata (`.md` + `.json` in `~/.repr/stories/`), reviewable, editable, publishable
- **Profile**: Derived artifact generated from your stories, publishable to repr.dev
- **Local mode**: No authentication, all data stays on your machine, network calls limited to loopback (127.0.0.1)
- **Cloud mode**: Authenticated, enables sync/publish/cloud inference, requires explicit `repr login`
- **BYOK** (Bring Your Own Key): Use your own API keys (OpenAI, Anthropic, etc.) for inference; data goes directly to the provider, not repr.dev

**Canonical Workflows:**

- **Publish flow**: `repr generate` → `repr stories review/edit` → `repr push`
- **Multi-device sync flow**: `repr login` → `repr sync` (bidirectional: uploads local stories, downloads remote stories, with prompts)
- **Daily passive use**: `repr hooks install` → commits auto-queue locally → optional auto-generation on hook (if enabled)

---

## Installation & First Run

```bash
# Install
pipx install repr-cli

# First run
repr init
```

**Output:**
```
🚀 repr - understand what you've actually worked on

repr helps you answer: "What did I work on this week?"

Works locally first — sign in later for sync and sharing.

Scanning ~/code for repositories...
Found 3 repositories

✓ everdraft (347 commits)
✓ my-side-project (89 commits)
✓ dotfiles (45 commits)

Default username: jdoe-mbp (local only)
Local LLM: detected Ollama at http://localhost:11434

Next steps:
  repr week               See what you worked on this week
  repr since monday       Quick summary since Monday
  repr generate --local   Save stories permanently
  repr login             Unlock cloud sync and publishing
```

**What happens:**
- Scans for git repos in common paths (`~/code`, `~/projects`, current directory)
- Generates hostname-based username (`$USER-$(hostname -s)`)
- Detects local LLM (Ollama, LM Studio, etc.)
- **Prompts user to confirm which repos to track** (default: track all found repos, but user can deselect)
- Creates `~/.repr/config.json` with local-only defaults
- **Network policy: See below**

**Network Call Policy in Local Mode:**

Allowed:
- `127.0.0.1`, `localhost`, `::1` (loopback only)
- Unix domain sockets (local IPC)

Strictly disallowed:
- Any non-loopback IP address
- Any DNS lookups to public networks
- Any HTTP(S) to public internet
- repr.dev connectivity checks
- Update checks
- Template fetching from remote

In local mode, repr is completely air-gapped except for localhost LLM detection.

**Enforcement:**
- repr uses a custom network sandbox (socket dialer allowlist) that rejects all outbound connections except loopback
- DNS resolution is intercepted: queries for non-loopback addresses are blocked
- If a plugin or dependency attempts an external network call, it fails with:
  ```
  ❌ External network blocked in Local mode
     Attempted connection to: example.com:443
     Local mode only allows loopback (127.0.0.1, localhost, ::1)

     To enable cloud features: repr login
  ```
- Enforcement is code-level (not policy): network layer is wrapped with allow/deny logic

---

## Complete Command Reference

### Authentication

#### `repr login`

Authenticate with repr.dev to unlock cloud features.

**Flow:**
1. Opens browser → Supabase Auth
2. User signs in / creates account
3. Returns to CLI with device code
4. Device linked to account
5. Token saved locally

**Data sent:** Email + random device key (generated locally)

**After login:**
```
✓ Signed in as alice@example.com

Cloud features enabled:
  • Cloud LLM generation
  • Sync across devices
  • Publish to repr.dev

Default to cloud inference when available? [y/N]
```

If user says **No**, sets `llm.default = "local"` in config.

**If user has local stories:**
```
You have 10 local stories that haven't been uploaded yet.
Run `repr sync` to review and upload them.
```

Does NOT auto-upload. Consent happens at `repr sync`.

---

#### `repr logout`

Clear authentication, return to local-only mode.

```bash
repr logout

✓ Signed out
  Cloud features disabled
  Local stories preserved

  Run `repr login` to re-enable cloud features
```

**What happens:**
- Removes auth token
- Sets mode back to local-only
- Keeps all local data (stories, config, queue)

---

#### `repr whoami`

Show current user and mode (lightweight alias of `repr status --identity`).

**Not signed in:**
```
Username: jdoe-mbp (local only)
Data boundary: local only
Auth: not signed in

Cloud features require sign-in.
Run `repr login` to enable cloud features.
```

**Signed in:**
```
Username: alice (claimed ✓)
Email: alice@example.com
Data boundary: cloud-enabled
Default inference: local
Auth: signed in

Profile: https://repr.dev/@alice
```

---

### Story Generation

#### `repr generate`

Generate stories from commits.

**Flags:**
- `--local` - Use local LLM (default if not signed in)
- `--cloud` - Use cloud LLM (requires login)
- `--repo <path>` - Generate for specific repo
- `--commits <hashes>` - Generate from specific commits (comma-separated)
- `--template <type>` - Use template: `resume`, `changelog`, `narrative`, `interview`
- `--batch-size <n>` - Number of commits per story (default: 5)
- `--dry-run` - Preview what would be sent (cloud only)
- `--prompt <text>` - Custom prompt to append

**Important:** Generation saves stories locally. Use `repr push` to publish to repr.dev.

**Examples:**

```bash
# Local generation (default)
repr generate --local

# Cloud generation (requires login)
repr generate --cloud

# Dry run (preview payload before sending)
repr generate --cloud --dry-run

# Specific commits with template
repr generate --commits abc123,def456,ghi789 --template resume

# Custom prompt
repr generate --cloud --prompt "Focus on performance improvements"
```

**Local generation:**
```
Generating stories (local LLM)...

✓ everdraft: 2 stories generated
  • Built user authentication with JWT
  • Implemented payment integration

✓ my-side-project: 1 story generated
  • Added real-time collaboration

Stories saved locally: ~/.repr/stories/
Run `repr stories` to view
```

**Cloud generation (not signed in):**
```
❌ Cloud generation requires sign-in
   Run `repr login` to enable cloud features

   Local generation is available:
   repr generate --local
```

**Cloud generation (signed in):**
```
Generating stories (cloud LLM: gpt-4o-mini)...

Sending to cloud:
  • 3 repos
  • 15 commits
  • Commit messages, repo-relative file paths, metadata

  ℹ Diffs not included (set llm.cloud_send_diffs = true to enable)
  ℹ Machine-specific paths redacted (set llm.cloud_redact_paths = false to disable)

Payload: {
  repos: [
    {
      id: "sha256_hash_of_git_root",
      name: "everdraft",
      commits: [
        {
          hash: "abc123...",
          message: "Add JWT authentication",
          timestamp: "2026-01-02T10:00:00Z",
          files_changed: ["src/auth/jwt.ts", "src/middleware/auth.ts"],
          stats: { additions: 120, deletions: 15 }
        }
      ]
    }
  ]
}

✓ everdraft: 2 stories generated
  • Built user authentication with JWT (high confidence)
  • Implemented payment integration (high confidence)

✓ my-side-project: 1 story generated
  • Added real-time collaboration (needs review ⚠)

Stories saved locally: ~/.repr/stories/
Run `repr push` to publish to repr.dev
```

**Dry run preview:**
```bash
repr generate --cloud --dry-run

Preview: Cloud generation payload

Repos: 3
  • everdraft
  • my-side-project
  • dotfiles

Commits: 15 total
  • everdraft: 8 commits
  • my-side-project: 5 commits
  • dotfiles: 2 commits

Payload includes:
  ✓ Commit messages
  ✓ File paths (absolute paths redacted)
  ✓ Summary metadata (files changed, lines added/removed)
  ✗ Code diffs (disabled, set llm.cloud_send_diffs = true to enable)

Privacy settings:
  ✓ Absolute path redaction: enabled (llm.cloud_redact_paths = true)
  ✗ Code diffs: disabled (llm.cloud_send_diffs = false)

Estimated tokens: ~4,200

Continue with generation? [y/N]
```

---

### Personal Reflection (Lightweight Commands)

These commands provide on-the-fly summaries without saving stories. No setup required, no hooks needed — just quick answers to "what did I work on?"

#### `repr week`

Show what you worked on this week.

**Flags:**
- `--format <fmt>` - Output format: `text` (default), `md`, `bullets`
- `--save` - Save as a permanent story (otherwise ephemeral)

```bash
repr week

📊 This Week's Work (Jan 1-5)

everdraft (23 commits):
  • Built user authentication with JWT
  • Fixed memory leak in WebSocket handler
  • Added rate limiting to API endpoints

my-side-project (8 commits):
  • Implemented dark mode toggle
  • Refactored state management

Total: 31 commits across 2 projects

This summary wasn't saved. Run with --save to create a story.
```

**What this is for:**
- Friday standup prep
- Weekend reflection ("did I actually ship anything?")
- Quick check-in without committing to archival

---

#### `repr since <date>`

Show work since a specific date or time reference.

**Flags:**
- `--format <fmt>` - Output format: `text` (default), `md`, `bullets`
- `--save` - Save as a permanent story

**Time references:**
- Absolute dates: `2026-01-01`, `Jan 1`
- Relative: `monday`, `last week`, `3 days ago`
- Special: `standup` (last 3 days), `yesterday`

**Time Parsing Details:**
- **Timezone**: Local machine timezone (uses system time)
- **"monday"**: Most recent Monday at 00:00 local time (if today is Monday, uses last Monday)
- **"last week"**: Previous calendar week (Monday 00:00 to Sunday 23:59)
- **"3 days ago"**: Exactly 72 hours before current time
- **Parsing library**: Uses `dateparser` (Python) with locale-aware natural language processing

```bash
repr since monday

📊 Work Since Monday (Jan 1-5)

everdraft (18 commits):
  • Built user authentication system
  • Added rate limiting

my-side-project (5 commits):
  • Dark mode implementation

Total: 23 commits across 2 projects
```

```bash
repr since "3 days ago"

📊 Work Since Jan 2

everdraft (12 commits):
  • Fixed memory leak in WebSocket handler
  • Added rate limiting to API

Total: 12 commits in everdraft
```

---

#### `repr standup`

Quick summary for daily standup (last 3 days).

**Flags:**
- `--days <n>` - Number of days to look back (default: 3)
- `--format <fmt>` - Output format: `text` (default), `bullets`, `slack`

```bash
repr standup

📊 Standup Summary (Last 3 Days)

everdraft:
  • Fixed memory leak in WebSocket handler
  • Added rate limiting to API endpoints
  • Updated dependencies

my-side-project:
  • Implemented dark mode toggle

Commits: 15 across 2 projects
```

**With Slack format:**
```bash
repr standup --format slack

*Last 3 days:*
• everdraft: Fixed memory leak, added rate limiting, updated dependencies (12 commits)
• my-side-project: Implemented dark mode (3 commits)
```

**Key difference from `repr generate`:**
- `repr week/since/standup`: Ad-hoc, ephemeral, instant
- `repr generate`: Permanent stories saved to `~/.repr/stories/`

Use these lightweight commands for quick reflection. Use `repr generate` when you want to archive and potentially share.

---

### Publishing & Syncing

#### `repr push`

Publish local stories to repr.dev. Stories reach the cloud only via explicit user-confirmed upload (via `repr push` or the upload step of `repr sync`).

**Requires:** Login

**Important:** Cloud generation (`repr generate --cloud`) does NOT automatically publish. You must explicitly run `repr push`.

**Flags:**
- `--all` - Push all local stories (default)
- `--story <id>` - Push specific story only
- `--since <date>` - Push stories created since date
- `--dry-run` - Preview what would be published

```bash
repr push

↑ Publishing 10 local stories to repr.dev...

Preview:
  • Built user authentication with JWT (created 2 days ago)
  • Implemented payment integration (created 1 week ago)
  • Added real-time collaboration (created 3 weeks ago)
  ...

These stories will be:
  ✓ Uploaded to repr.dev
  ✓ Synced across your devices
  ✓ Visible on your profile (based on privacy settings)

Continue? [y/N]
```

**Not signed in:**
```
❌ Publishing requires sign-in
   Run `repr login` to publish your profile

   Stories are saved locally: ~/.repr/stories/
```

---

#### `repr sync`

Sync stories across devices. `repr sync` is a composite operation that can upload local stories, download remote stories, and resolve conflicts — always with explicit user confirmation.

**Requires:** Login

**First sync after login (with local stories):**
```bash
repr sync

You have 10 local stories that haven't been uploaded.

Preview:
  • Built authentication system
  • Implemented payment flow
  • Added CI/CD pipeline
  ...

Upload these stories? [y/N]
```

**Subsequent syncs:**
```bash
repr sync

Syncing with repr.dev...

↑ 2 local stories to push
↓ 1 remote story to pull

Changes:
  ↑ "Built dashboard UI" (new on this device)
  ↑ "Fixed memory leak" (new on this device)
  ↓ "Optimized database queries" (from laptop)

Continue? [y/N]
```

**Conflicts:**
```
⚠ Conflicts detected:

Story "Built auth system" exists locally and remotely (different content)

Local version (this device):
  Created: 2 days ago
  Commits: 3
  Summary: Built user authentication with JWT

Remote version (laptop):
  Created: 1 day ago
  Commits: 5
  Summary: Implemented complete auth flow with OAuth

Keep: [local] [remote] [both] [skip]
```

---

#### `repr pull`

Pull remote stories to local device.

**Requires:** Login

```bash
repr pull

Pulling from repr.dev...

↓ 3 new stories from other devices
  • Built payment integration
  • Added admin dashboard
  • Fixed security vulnerability

Stories saved locally: ~/.repr/stories/
```

---

### Story Management

#### `repr stories`

List all stories.

**Flags:**
- `--repo <name>` - Filter by repository
- `--since <date>` - Filter by date
- `--needs-review` - Show only stories needing review
- `--with-links` - Show share links (requires login)

```bash
repr stories

Recent Stories (12 total)

✓ Built user authentication with JWT         (high confidence)
  everdraft • 3 commits • 12 files • React, FastAPI
  Created: 2 days ago

⚠ Refactored database layer                   (needs review)
  everdraft • 8 commits • 34 files • SQL, Python
  Created: 1 week ago

✓ Added real-time collaboration               (high confidence)
  my-side-project • 5 commits • 18 files • WebSockets, Redis
  Created: 3 weeks ago

Commands:
  repr story edit <id>        Edit story
  repr story delete <id>      Delete story
  repr story hide <id>        Hide from profile
  repr story feature <id>     Pin to top of profile
```

**With links (requires login):**
```bash
repr stories --with-links

✓ Built user authentication with JWT
  https://repr.dev/@alice/stories/abc123

⚠ Refactored database layer
  https://repr.dev/@alice/stories/def456
```

---

#### `repr story <action> <id>`

Manage individual stories.

**Note:** `repr stories <action> <id>` also works as an alias.

**Actions:**
- `edit <id>` - Edit story in $EDITOR
- `delete <id>` - Delete story
- `hide <id>` - Hide from profile (keep locally)
- `unhide <id>` - Show on profile
- `feature <id>` - Pin to top of profile
- `link <id>` - Get shareable link (requires login)
- `regenerate <id>` - Regenerate with different prompt/template

**Story ID Format:** ULID (sortable, collision-safe, e.g., `01ARYZ6S41TSV4RRFFQ69G5FAV`)

**Examples:**

```bash
# Edit story
repr story edit abc123
# Opens in $EDITOR (vim, vscode, etc.)

# Delete story
repr story delete abc123
⚠ This will delete the story locally and remotely.
Continue? [y/N]

# Get share link
repr story link abc123
https://repr.dev/@alice/stories/abc123

Embed code:
<script src="https://repr.dev/embed/abc123.js"></script>

# Regenerate
repr story regenerate abc123 --template technical
Regenerating story with template: technical
✓ Story updated
```

---

#### `repr stories review`

Interactive review workflow for stories needing review.

```bash
repr stories review

Story 1 of 3 needs review:

⚠ "Refactored database layer"
  8 commits • 34 files • SQL, Python

What was built:
  Completely restructured the database access layer to use
  repository pattern. Migrated from direct ORM calls to
  centralized repositories with proper transaction handling.

Technologies:
  Python, SQLAlchemy, PostgreSQL

Confidence: Medium (complex refactor, multiple patterns)

[a] Approve  [e] Edit  [r] Regenerate  [d] Delete  [s] Skip  [q] Quit
```

---

### Profile Management

#### `repr profile`

View profile in terminal.

**Flags:**
- `--stories` - Show only stories section
- `--tech` - Show only tech stack
- `--timeline` - Show only timeline

```bash
repr profile

Alice (@alice)
Full-stack developer • San Francisco, CA

Tech Stack:
  React, TypeScript, Python, FastAPI, PostgreSQL, Redis

Recent Stories (5):
  • Built user authentication with JWT
  • Implemented payment integration
  • Added real-time collaboration
  ...

Timeline:
  2026 Q1: 12 stories across 3 projects
  2025 Q4: 8 stories across 2 projects

Profile: https://repr.dev/@alice
Last updated: 2 days ago
```

---

#### `repr profile update`

Generate/update profile from stories.

**Flags:**
- `--preview` - Show diff before publishing
- `--local` - Update locally only (don't publish)

```bash
repr profile update --preview

Profile Changes Since Last Publish:

Added Stories (2):
  + Built payment integration
  + Implemented real-time sync

Updated Sections:
  ~ Tech Stack: +Stripe, +WebSockets
  ~ Timeline: 2 new entries in 2026 Q1

Metadata Changes:
  ~ Last updated: 2 weeks ago → today

Continue? [y/N]
```

---

#### `repr profile set-<field> <value>`

Set profile metadata.

```bash
# Bio
repr profile set-bio "Full-stack developer specializing in AI/ML"

# Location
repr profile set-location "San Francisco, CA"

# Availability
repr profile set-available true

# Social links
repr profile set-website "https://alice.dev"
repr profile set-twitter "@alicedev"
repr profile set-linkedin "alice"
```

---

#### `repr profile export`

Export profile to different formats.

**Flags:**
- `--format <fmt>` - Format: `md`, `pdf`, `html`, `json`
- `--since <date>` - Export only recent work
- `--output <path>` - Output file path

```bash
# Export to Markdown
repr profile export --format md > profile.md

# Export to PDF (uses bundled HTML-to-PDF renderer, no external dependencies)
repr profile export --format pdf --output resume.pdf

# Export recent work only
repr profile export --since 2025-01-01 --format md
```

**PDF Rendering:** PDF export is rendered from Markdown → HTML → PDF using a bundled renderer (no external service required).

---

#### `repr profile link`

Get shareable profile link.

**Requires:** Login

```bash
repr profile link

Your profile: https://repr.dev/@alice

Share specific sections:
  Stories: https://repr.dev/@alice/stories
  Timeline: https://repr.dev/@alice/timeline

QR code: Run `repr profile qr` to display
```

---

#### `repr profile privacy <level>`

Set profile visibility.

**Requires:** Login

**Levels:**
- `public` - Searchable, visible to all
- `unlisted` - Has link but not searchable
- `private` - Only you can see

```bash
repr profile privacy unlisted

✓ Profile visibility: unlisted
  Your profile has a link but won't appear in search

  Anyone with the link can view: https://repr.dev/@alice
```

---

### Repository Management

#### `repr repos`

List tracked repositories.

```bash
repr repos

Tracked Repositories (3)

✓ everdraft (~/code/everdraft)
  347 commits • auto-track: on • hook: installed
  Last sync: 2 hours ago

✓ my-side-project (~/code/my-side-project)
  89 commits • auto-track: on • hook: installed
  Last sync: 1 day ago

○ dotfiles (~/code/dotfiles)
  45 commits • auto-track: paused • hook: not installed
  Last sync: never

Commands:
  repr repos add <path>       Add repository
  repr repos remove <path>    Stop tracking
  repr repos pause <path>     Pause auto-tracking
  repr repos resume <path>    Resume auto-tracking
```

---

#### `repr repos add <path>`

Add repository to tracking.

```bash
repr repos add ~/code/new-project

Analyzing repository...
✓ new-project (234 commits)

Install auto-tracking hook? [Y/n]
```

---

#### `repr repos remove <path>`

Stop tracking repository.

```bash
repr repos remove ~/code/old-project

This will:
  • Remove tracking for old-project
  • Uninstall hook (if installed)
  • Keep existing stories (12 stories)

Continue? [y/N]
```

---

#### `repr repos pause <path>`

Temporarily pause auto-tracking.

```bash
repr repos pause ~/code/work-project

✓ Auto-tracking paused for work-project
  Hook disabled (commits won't be queued)
  Existing stories preserved

  Resume: repr repos resume ~/code/work-project
```

---

### Hooks Management

#### `repr hooks install`

Install git post-commit hooks for auto-tracking.

**Flags:**
- `--all` - Install in all tracked repos
- `--repo <path>` - Install in specific repo

```bash
repr hooks install --all

Installing hooks in 3 repositories...

✓ everdraft: hook installed
✓ my-side-project: hook installed
○ dotfiles: hook already installed

Hooks installed: 2
Already installed: 1

What hooks do:
  • Run locally during post-commit phase
  • Queue commits for story generation (always local, stored in .git/repr/queue.json)
  • Auto-generation triggers when batch size reached (default: 5) IF generation.auto_generate_on_hook = true AND LLM is healthy
  • Auto-generation during hooks always uses the local LLM, regardless of default inference settings
  • Hooks never trigger BYOK inference.
  • Auto-generation in hooks is always local-only.
  • By default, commits are ONLY queued; manual generation required
  • Auto-generation runs DURING commit (foreground, adds latency)
  • If generation fails, commit succeeds anyway; generation is skipped
  • Stories published only via explicit `repr push`

  Hook location: .git/hooks/post-commit
  Queue location: .git/repr/queue.json (simple file lock for concurrency)
  Performance: Auto-generation adds 1-5s to commit time if enabled
  Uninstall: repr hooks remove --all
```

**Privacy note in help:**
```bash
repr hooks --help

Manage git post-commit hooks

PRIVACY:
  • Hooks run locally on your machine
  • Commits are queued locally only (stored in .git/repr/queue.json)
  • No external network calls during commit (loopback only). Hooks never trigger cloud generation.
  • No data sent until story generation
  • Auto-generation only if generation.auto_generate_on_hook = true (disabled by default)
  • Stories pushed only if signed in + cloud enabled
  • Hook config: .git/hooks/post-commit

BEHAVIOR:
  • By default, hooks only enqueue commits
  • Set generation.auto_generate_on_hook = true to enable auto-generation
  • Auto-generation only runs if LLM health check passes

  To uninstall: repr hooks remove --all
```

---

#### `repr hooks remove`

Remove git post-commit hooks.

**Flags:**
- `--all` - Remove from all tracked repos
- `--repo <path>` - Remove from specific repo

```bash
repr hooks remove --all

✓ everdraft: hook removed
✓ my-side-project: hook removed
○ dotfiles: no hook installed

Hooks removed: 2
```

---

#### `repr hooks status`

Show hook status for all tracked repos.

```bash
repr hooks status

Hook Status:

✓ everdraft
  Hook installed and active
  Queue: 3 commits (batch size: 5)

✓ my-side-project
  Hook installed and active
  Queue: 0 commits

○ dotfiles
  No hook installed
```

---

#### Hooks Behavior Under Git Edge Cases

**Rebases / Amended Commits:**
- If a commit hash disappears (e.g., after `git rebase`), the queue entry is dropped on next hook run with a warning
- The hook detects orphaned queue entries by checking if commit hash exists in repo history
- Warning message: `⚠ Dropped 2 orphaned commits from queue (removed by rebase or amend)`

**Force Push / Rewritten History:**
- Local queue is unaffected (stored in `.git/repr/queue.json`)
- If you force-push and lose commits, queue will contain references to non-existent commits
- Next hook run will clean up orphaned entries automatically

**Repo Deletion:**
- Queue is stored in `.git/repr/queue.json` within the repo
- If repo is deleted, queue is lost (stories are not affected)
- Already-generated stories remain in `~/.repr/stories/`

**Bare Repos / Read-Only `.git`:**
- Hook install fails with actionable error: `❌ Cannot install hook: .git directory is read-only`
- Suggestion: `Use repr repos add --no-hooks to track without hooks`

**Concurrent Commits (Multiple Terminals):**
- Queue uses simple file lock (`.git/repr/queue.json.lock`)
- If lock is held, hook waits up to 2 seconds, then skips queuing with warning
- Warning: `⚠ Could not acquire queue lock, commit not queued (retry: repr generate)`

---

### LLM Configuration

#### `repr llm add <provider>`

Configure a BYOK provider.

```bash
repr llm add openai
# Prompts for API key (hidden input)
# Stores key in OS keychain

repr llm add anthropic
```

---

#### `repr llm remove <provider>`

Remove a BYOK provider key.

```bash
repr llm remove openai
```

---

#### `repr llm use <mode>`

Set default LLM mode.

**Modes:** `local`, `cloud`, `byok:<provider>`

```bash
repr llm use local

✓ Default LLM: local
```

```bash
repr llm use byok:openai

✓ Default LLM: byok:openai
  (api.openai.com)
```

```bash
repr llm use cloud

⚠ Cloud LLM requires sign-in

Signed in: Use cloud by default
Not signed in: Fall back to local

Current: not signed in → local will be used
```

---

#### `repr llm configure`

Configure local LLM endpoint.

```bash
repr llm configure

Detected local LLMs:
  1. Ollama (http://localhost:11434)
  2. LM Studio (http://localhost:1234)
  3. Custom endpoint

Select: 1

✓ Using Ollama

Available models:
  1. llama3.2 (recommended)
  2. mistral
  3. codellama

Select model: 1

✓ LLM configured
  Provider: Ollama
  Endpoint: http://localhost:11434
  Model: llama3.2

Test: repr llm test
```

---

#### `repr llm test`

Test LLM connection and generation.

```bash
repr llm test

Testing local LLM...

Endpoint: http://localhost:11434
Model: llama3.2

✓ Connection successful
✓ Model loaded
✓ Test generation successful (1.2s response time)

LLM ready for story generation.
```

---

### Privacy & Data Management

#### `repr mode`

Quick check of current execution mode and settings.

```bash
repr mode

Data boundary: local
Auth: not signed in
LLM: Ollama (llama3.2) at http://localhost:11434
Privacy lock: disabled

Available:
  ✓ Local generation
  ✗ Cloud generation (requires login)
  ✗ Sync (requires login)
  ✗ Publishing (requires login)

Run `repr login` to enable cloud features
```

**Signed in:**
```bash
repr mode

Data boundary: cloud-enabled
Default inference: local
Auth: signed in as alice@example.com
LLM: local=Ollama (llama3.2), cloud=gpt-4o-mini
Privacy lock: disabled

Available:
  ✓ Local generation
  ✓ Cloud generation
  ✓ Sync
  ✓ Publishing

Use `repr llm use <local|cloud>` to change default
```

**BYOK:**
```bash
repr mode

Data boundary: local (no repr.dev account)
Inference: BYOK (OpenAI)
Network: outbound to api.openai.com (user-provided key)
Privacy: Data sent directly to provider, not repr.dev

⚠ BYOK inference sends data to third-party providers
  See `repr privacy audit` for full history
```

---

#### `repr config`

View and modify configuration.

**Subcommands:**
- `show` - Display current config
- `show <key>` - Display specific config value
- `set <key> <value>` - Set config value
- `edit` - Open config file in $EDITOR

```bash
# Show all config
repr config show

# Show specific value
repr config show llm.default
local

# Set value
repr config set generation.batch_size 10
✓ Set generation.batch_size = 10

# Edit config file
repr config edit
# Opens ~/.repr/config.json in $EDITOR
```

**Common config keys:**
- `llm.default` - Default LLM mode (`local` or `cloud`)
- `llm.local_model` - Local LLM model name
- `generation.batch_size` - Commits per story
- `generation.auto_generate_on_hook` - Auto-generate on hooks
- `publish.on_generate` - Publish after generation (`never`, `prompt`, `always`)
- `privacy.lock_local_only` - Local-only mode lock
- `llm.cloud_redact_paths` - Path redaction

---

#### `repr privacy explain`

One-screen summary of privacy guarantees and current settings.

```bash
repr privacy explain

repr Privacy Guarantees
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ARCHITECTURE:
  ✓ Without login, nothing leaves your machine (enforced in code)
  ✓ No background daemons or silent uploads
  ✓ All network calls are foreground, user-initiated
  ✓ No telemetry by default (opt-in only)

CURRENT SETTINGS:
  Auth: not signed in
  Mode: local only
  Privacy lock: disabled
  Telemetry: disabled

LOCAL MODE NETWORK POLICY:
  Allowed: 127.0.0.1, localhost, ::1 (loopback only)
  Blocked: All external network, DNS, HTTP(S) to internet

CLOUD MODE (when signed in):
  ✓ Path redaction enabled (cloud_redact_paths = true)
  ✓ Diffs disabled (cloud_send_diffs = false)
  ✓ Email redaction disabled (cloud_redact_emails = false)
  ✓ Auto-publish disabled (publish.on_generate = never)

DATA RETENTION:
  Story deletion: Immediate removal from repr.dev
  Account deletion: All data deleted within 30 days
  Backups: Encrypted snapshots retained 90 days
  Local data: Never touched by cloud operations

OWNERSHIP:
  Your content belongs to you
  repr claims no ownership over generated stories

Run `repr privacy audit` to see all data sent
Run `repr privacy lock-local` to disable cloud permanently
```

---

#### `repr privacy audit`

Show what data was sent to repr.dev.

```bash
repr privacy audit

Privacy Audit

Last 30 days:

Cloud generation (3 times):
  • Jan 2: 15 commits → 3 stories
    Payload: commit messages, file paths, metadata
    Diffs included: No

  • Dec 28: 8 commits → 2 stories
    Payload: commit messages, file paths, metadata
    Diffs included: No

  • Dec 20: 12 commits → 3 stories
    Payload: commit messages, file paths, metadata
    Diffs included: No

BYOK generation (OpenAI) – 3 times
  • Jan 2: 15 commits → 3 stories
    Destination: api.openai.com
    Payload: commit messages, file paths, metadata
    Diffs included: No

Profile updates (2 times):
  • Jan 2: Profile updated with 3 new stories
  • Dec 20: Profile updated with 3 new stories

Total data sent: ~12 KB
Local data: ~/.repr/ (2.3 MB)

Settings:
  Cloud send diffs: No
  Auto-publish: No (publish.on_generate = never)
  Default LLM: local
```

**Not signed in:**
```
Privacy Audit

Last 30 days:
  None (not signed in)

Local data: ~/.repr/ (1.1 MB)

No data has been sent to repr.dev.
Run `repr login` to enable cloud features.
```

---

#### `repr privacy lock-local`

Disable cloud features (even after login).

**Flags:**
- `--permanent` - Make lock irreversible (requires confirmation)

```bash
# Reversible lock (default)
repr privacy lock-local

✓ Local-only mode enabled
  Cloud features disabled even after sign-in
  All generation will use local LLM

  To unlock: repr privacy unlock-local

# Permanent lock (irreversible)
repr privacy lock-local --permanent

⚠ This will PERMANENTLY disable cloud features.
  You will not be able to unlock cloud mode.
  Local-only mode will be enforced forever.

Continue? [y/N]

✓ Local-only mode PERMANENTLY enabled
  Cloud features cannot be re-enabled
  All generation will use local LLM only
```

**Why reversible by default:**
- Most users want flexibility to try cloud features later
- Permanent lock is available for strict privacy requirements
- Reversible lock is sufficient for most use cases

**Lock + Login Interaction:**

If you lock local-only WHILE already logged in:
- Auth state remains "signed in"
- Cloud mode becomes unavailable
- Commands requiring cloud will say "blocked by local-only lock" (not "requires login")
- `repr whoami` shows: `Auth: signed in (cloud locked by privacy setting)`

If you lock local-only BEFORE logging in:
- `repr login` will succeed (for future use)
- Cloud mode remains unavailable until unlocked
- You can unlock later to enable cloud features

**After locking, attempting cloud:**
```bash
repr generate --cloud

❌ Cloud features locked
   Local-only mode is enabled (privacy setting)

   Auth: signed in
   Mode: local only (cloud blocked)

   To unlock: repr privacy unlock-local
   (or permanently locked if --permanent was used)
```

---

#### `repr data`

Show local data storage.

```bash
repr data

Local Data (~/.repr/)

Stories: 24 files (234 KB)
Profile cache: 3 versions (45 KB)
Commit queue: 18 pending commits (12 KB)
Config: 1 file (2 KB)
Cache: 12 MB

Total: 12.3 MB

Locations:
  Stories: ~/.repr/stories/ (format: <ulid>.md + <ulid>.json metadata)
  Config: ~/.repr/config.json
  Cache: ~/.repr/cache/
  Queue: per-repo at <repo>/.git/repr/queue.json

Story File Format:
  • Each story stored as two files:
    - <ULID>.md: Story content in Markdown (e.g., 01ARYZ6S41TSV4RRFFQ69G5FAV.md)
    - <ULID>.json: Metadata (commits, timestamps, repo, etc.)
```

---

#### `repr data backup`

Backup all local data to JSON.

```bash
repr data backup > backup.json

✓ Backed up:
  • 24 stories
  • 3 profile versions
  • 18 queued commits
  • Config and settings

Saved to: backup.json (1.2 MB)
```

---

#### `repr data restore`

Restore from backup.

```bash
repr data restore < backup.json

This will restore:
  • 24 stories
  • 3 profile versions
  • Config and settings

Existing data will be merged (duplicates skipped).

Continue? [y/N]

✓ Restored 24 stories
✓ Restored config
```

---

#### `repr data clear-cache`

Clear local cache.

```bash
repr data clear-cache

✓ Cache cleared (12 MB freed)
  Stories preserved
  Config preserved
```

---

### Status & Health

#### `repr status`

Show repr status and health.

```bash
repr status

Username: alice (claimed ✓)
Email: alice@example.com
Data boundary: cloud-enabled
Default inference: local
Auth: signed in

Tracked repos: 3 (2 active, 1 paused)
Stories: 24 (2 unpublished, 1 needs review)
Profile: updated 2 days ago (4 new stories available)

Pending:
  ⚠ 1 story needs review
  💡 4 stories ready for profile update
  📝 everdraft: 3 commits queued (batch size: 5)

Profile: https://repr.dev/@alice
Last sync: 2 hours ago

Next steps:
  repr stories review         Review flagged stories
  repr profile update         Update profile with new stories
```

**Not signed in:**
```
Username: jdoe-mbp (local only)
Auth: not signed in
Data boundary: local

Tracked repos: 3
Stories: 12 (all local)
Profile: not published

Pending:
  📝 everdraft: 3 commits queued
  📝 my-side-project: 2 commits queued

Cloud features require sign-in.
Run `repr login` to enable sync and publishing.
```

---

#### `repr doctor`

Health check and diagnostics.

```bash
repr doctor

Checking repr health...

✓ Auth: signed in as alice@example.com
✓ Tracked repos: 3 repositories
✓ Hooks: installed in 3/3 repos
✓ LLM: local (Ollama) + cloud (gpt-4o-mini)
⚠ Story queue: 12 commits pending (batch size: 5)
⚠ Profile: 47 days since last update

Recommendations:
  • Generate stories from pending commits: repr generate
  • Update profile: repr profile update

All systems healthy.
```

**With issues:**
```
Checking repr health...

✓ Auth: signed in
✗ LLM: local endpoint unreachable (http://localhost:11434)
⚠ Hooks: installed in 2/3 repos (missing: dotfiles)
⚠ Sync: 3 stories not pushed

Issues found:
  1. Local LLM not running
     Fix: Start Ollama (ollama serve)
     Test: repr llm test

  2. Hook missing in dotfiles
     Fix: repr hooks install --repo ~/code/dotfiles

  3. Stories not synced
     Fix: repr sync
```

---

### Smart Git Workflow

AI-powered git commands for staging, branching, committing, and creating PRs.

#### `repr add <pattern>`

Stage files matching pattern (grep-style regex).

**Arguments:**
- `pattern` - Regex pattern to match in file paths

**Flags:**
- `-f, --force` - Force add ignored files

```bash
repr add cli              # Stage files matching "cli"
repr add "\.py$"          # Stage files ending in .py
repr add .                # Stage all changed files
repr add cli -f           # Force add ignored files
```

**Next step hints:**
- On main/master: suggests `repr branch` to create a new feature branch
- On feature branch: suggests `repr commit` or `repr branch` to create a new feature branch

---

#### `repr unstage <pattern>`

Unstage files matching pattern (grep-style regex).

**Arguments:**
- `pattern` - Regex pattern to match in staged file paths

```bash
repr unstage cli          # Unstage files matching "cli"
repr unstage "\.py$"      # Unstage files ending in .py
repr unstage .            # Unstage all staged files
```

---

#### `repr branch [name]`

Create and switch to a new branch.

**Arguments:**
- `name` (optional) - Branch name (AI generates if omitted)

**Flags:**
- `-r, --regenerate` - Regenerate branch name

```bash
repr branch               # AI generates name from staged/unpushed
repr branch feat/my-feat  # Use explicit name
repr branch -r            # Regenerate cached name
```

**Next step hint:** If there are staged changes, suggests `repr commit` to commit them.

---

#### `repr commit`

Generate commit message and commit staged changes.

**Flags:**
- `-m, --message <msg>` - Custom message (skip AI)
- `-r, --regenerate` - Regenerate message
- `-y, --yes` - Skip confirmation on main/master

```bash
repr commit               # AI generates message
repr commit -m "fix: x"   # Custom message
repr commit -r            # Regenerate message
```

---

#### `repr push`

Push commits to remote.

```bash
repr push                 # Push to remote (sets upstream if needed)
```

---

#### `repr pr`

Create a pull request with AI-generated title and description.

**Flags:**
- `-t, --title <title>` - Custom PR title
- `-d, --draft` - Create as draft PR
- `-r, --regenerate` - Regenerate title/body

```bash
repr pr                   # AI generates title/body
repr pr -t "feat: add X"  # Custom title
repr pr --draft           # Create draft PR
```

---

#### `repr changes`

Show file changes across git states.

**Flags:**
- `-e, --explain` - Add AI explanations per group
- `-c, --compact` - Compact output (no diff previews)
- `--json` - Output as JSON

```bash
repr changes              # Show unstaged/staged/unpushed
repr changes --explain    # With AI explanations
repr changes --compact    # Just file names
```

---

#### `repr clear`

Clear cached branch name and commit message.

```bash
repr clear                # Show and clear cache
```

---

### Utilities

#### `repr commits`

List recent commits across all tracked repos.

**Flags:**
- `--repo <name>` - Filter by repo
- `--limit <n>` - Number of commits (default: 50)
- `--since <date>` - Filter by date

```bash
repr commits --limit 10

Recent Commits (10)

everdraft:
  abc123  Fix memory leak in WebSocket handler        2 hours ago
  def456  Add rate limiting to API endpoints          1 day ago
  ghi789  Update dependencies                          3 days ago

my-side-project:
  jkl012  Implement dark mode                          1 week ago
  mno345  Add user preferences                         1 week ago

Commands:
  repr generate --commits abc123,def456    Generate story from commits
```

---

#### `repr summary`

Weekly activity summary.

```bash
repr summary --week

📊 This Week in repr

Commits: 47 across 3 repos
  • everdraft: 23 commits
  • my-side-project: 18 commits
  • dotfiles: 6 commits

Stories: 4 generated (1 needs review)
  ✓ Built user authentication
  ✓ Implemented payment flow
  ✓ Added CI/CD pipeline
  ⚠ Refactored database layer (needs review)

Profile: updated 2 days ago

Activity:
  • 12 profile views
  • 8 story views
  • Top story: "Built user authentication" (5 views)

Next steps:
  repr stories review         Review flagged story
  repr generate              Generate from 12 pending commits
```

---

### Help & Learning

#### `repr --help`

Main help text.

```
repr - turn your commits into a developer profile

MODES:
  Local:  No sign-in, no data leaves your machine
  Cloud:  Sign in to sync, publish, and use cloud inference

GETTING STARTED:
  repr init              Create local profile
  repr generate --local  Generate stories (offline)
  repr login             Unlock cloud features

CORE COMMANDS:
  generate    Generate stories from commits
  push        Publish stories to repr.dev (requires login)
  sync        Sync across devices (requires login)
  pull        Pull remote stories (requires login)
  status      Show profile and auth status

STORY MANAGEMENT:
  stories     List all stories
  story       Manage individual story (edit, delete, hide, etc.)

PROFILE:
  profile     View and manage profile
  whoami      Show current user

REPOSITORIES:
  repos       Manage tracked repositories
  hooks       Install/remove git hooks

LLM:
  llm         Configure LLM (local/cloud)

PRIVACY:
  mode        Show current mode and settings
  config      View and edit configuration
  privacy     Privacy audit, explain, local-only mode

DATA:
  data        Backup, restore, clear cache

SMART GIT:
  add         Stage files matching pattern (grep-style regex)
  unstage     Unstage files matching pattern (grep-style regex)
  branch      Create and switch to new branch (AI names)
  commit      Generate commit message and commit
  push        Push to remote
  pr          Create pull request (AI title/body)
  changes     Show file changes across git states
  clear       Clear cached branch/commit info

UTILITIES:
  commits     List recent commits
  summary     Weekly activity summary
  doctor      Health check

Run 'repr <command> --help' for more information.

Cloud features require sign-in.
Local generation always works offline.
```

---

## Configuration File

**Location:** `~/.repr/config.json`

**Note on Token Storage:**
- Tokens are NEVER stored in plaintext in config.json
- Uses OS keychain where available:
  - macOS: Keychain
  - Windows: Credential Manager
  - Linux: Secret Service (libsecret)
- Fallback: Encrypted file with locally generated key (limitations documented)
- Config file only stores a reference to the keychain entry

```json
{
  "profile": {
    "username": "alice",
    "claimed": true,
    "email": "alice@example.com"
  },
  "auth": {
    "signed_in": true,
    "token_keychain_ref": "repr_auth_token_alice"
  },
  "llm": {
    "default": "local",
    "local_provider": "ollama",
    "local_endpoint": "http://localhost:11434",
    "local_model": "llama3.2",
    "cloud_model": "gpt-4o-mini",
    "cloud_send_diffs": false,
    "cloud_redact_paths": true,
    "cloud_redact_emails": false,
    "cloud_redact_patterns": [],
    "cloud_allowlist_repos": [],
    "byok": {
      "openai": {
        "model": "gpt-4o-mini",
        "keychain_ref": "repr_byok_openai_default",
        "send_diffs": false,
        "redact_paths": true,
        "redact_emails": false,
        "redact_patterns": []
      },
      "anthropic": {
        "model": "claude-sonnet",
        "keychain_ref": "repr_byok_anthropic_default",
        "send_diffs": false,
        "redact_paths": true
      }
    }
  },
  "generation": {
    "batch_size": 5,
    "auto_generate_on_hook": false,
    "default_template": "resume",
    "token_limit": 100000,
    "max_commits_per_batch": 50
  },
  "publish": {
    "on_generate": "never",
    "on_sync": "prompt"
  },
  "privacy": {
    "lock_local_only": false,
    "lock_permanent": false,
    "profile_visibility": "public",
    "telemetry_enabled": false
  },
  "repos": {
    "tracked": [
      "~/code/everdraft",
      "~/code/my-side-project",
      "~/code/dotfiles"
    ],
    "settings": {
      "~/code/everdraft": {
        "batch_size": 5,
        "auto_track": true,
        "hook_installed": true,
        "paused": false
      },
      "~/code/dotfiles": {
        "batch_size": 10,
        "auto_track": false,
        "hook_installed": false,
        "paused": false
      }
    }
  }
}
```

---

## Security Model

**Trust Boundaries:**

repr operates with the following trust model:

1. **Trusted Input:**
   - Local LLM responses (assumes localhost LLM is user-controlled)
   - User-provided configuration (`~/.repr/config.json`)
   - Cloud API responses (after TLS verification and signed-in state)

2. **Untrusted Input:**
   - Git commit messages (may contain injection attempts, malformed UTF-8)
   - File paths (may contain traversal attempts, special characters)
   - Filenames (may contain control characters, encoding exploits)
   - User-provided templates or prompts (sanitized before LLM submission)

**Redaction Enforcement:**

- Redaction is applied **before payload serialization**, not after
- Path redaction: Filesystem paths are stripped at the data collection layer (before JSON encoding)
- Pattern-based redaction (emails, custom patterns): Applied via regex during commit parsing
- Cloud payloads are constructed from pre-redacted data structures (no post-hoc scrubbing)

**Network Access Control:**

- **Local mode**: Socket dialer allowlist (127.0.0.1, ::1, Unix sockets only)
- **Cloud mode**: Explicit authentication check before any repr.dev API call
- **BYOK mode**: Direct provider access (bypasses repr.dev); user explicitly opts in via `repr llm add`
- DNS resolution is intercepted in local mode (blocks public DNS queries)

**Verification:**

Users can verify privacy and security properties:

- `repr privacy audit` - Shows all network activity and data sent
- `repr generate --dry-run` - Preview cloud payload before sending
- `repr doctor` - Health check (detects unexpected network access)
- `repr mode` - Shows current data boundary and network destinations

**Secrets Management:**

- Tokens stored in OS keychain (macOS Keychain, Windows Credential Manager, Linux Secret Service)
- Fallback: Encrypted file with locally generated key (documented limitations)
- No tokens in `config.json` (only keychain references)
- API keys for BYOK stored separately per provider in keychain

**Command Gating:**

Commands that require authentication fail fast with actionable errors:

```
❌ Cloud generation requires sign-in
   Run `repr login` to enable cloud features
```

Commands that violate privacy lock fail immediately:

```
❌ Cloud features locked
   Local-only mode is enabled (privacy setting)
```

This ensures users cannot accidentally violate their own privacy settings.

---

## Privacy Guarantees

### What Data Is Collected

| Action | Data Sent | When | Can Be Disabled |
|--------|-----------|------|-----------------|
| `repr init` | Nothing | Never | N/A (local only) |
| `repr generate --local` | Nothing | Never | N/A (local only) |
| `repr login` | Email + random device key (generated locally) | Only during auth | No (required for cloud) |
| `repr generate --cloud` | Commit messages, file paths (absolute paths redacted by default), summary metadata (files changed, lines added/removed) | Only when signed in | Yes (`--local` instead) |
| `repr generate --cloud` (with diffs) | Above + code diffs | Only when `cloud_send_diffs = true` | Yes (disabled by default) |
| `repr push` | Generated story content, repo metadata | Only when signed in | Yes (keep local) |
| `repr sync` | Story content, timestamps, metadata | Only when signed in | Yes (manual push only) |

**Path Redaction:**
- Enabled by default (`llm.cloud_redact_paths = true`)
- Absolute paths are stripped (e.g., `/Users/alice/code/myproject/src/auth.ts` → `src/auth.ts`)
- Optionally strip filenames, keeping extensions only (e.g., `*.ts`)
- Prevents machine-specific paths and usernames from leaking (home directories, absolute paths)
- Note: Repo-relative paths (e.g., `src/auth.ts`) are still sent for meaningful story generation

### Key Principles

1. **Without login, nothing leaves your machine**
   - Architecturally enforced, not a policy promise
   - All generation happens locally
   - Without repr login, repr never contacts repr.dev or uploads anything.
   - BYOK is optional and, when used, sends data directly to the provider whose API key you configured.
   - All such activity is visible in repr privacy audit.

2. **Cloud requires explicit sign-in**
   - No silent upgrades from local → cloud
   - Clear error messages explaining the boundary

3. **Diffs are optional**
   - Disabled by default
   - Must explicitly enable `cloud_send_diffs = true`
   - Can preview with `--dry-run`

4. **Path redaction by default**
   - Absolute paths stripped automatically (`cloud_redact_paths = true`)
   - Prevents leaking repo structure to cloud

5. **Local-only lockdown available**
   - `repr privacy lock-local` disables cloud features (reversible by default; `--permanent` makes it irreversible)
   - Even after login, cloud remains disabled

6. **Full audit trail**
   - `repr privacy audit` shows all data sent
   - Timestamps, payload details, data size

7. **No telemetry**
   - CLI collects no telemetry by default
   - Anonymous usage analytics are opt-in only
   - Set `privacy.telemetry_enabled = true` to opt in

   **If telemetry is enabled (opt-in):**

   | Event | Data Collected | Retention | Purpose |
   |-------|----------------|-----------|---------|
   | Command execution | Command name (e.g., `generate`, `push`), timestamp | 90 days | Understand feature usage |
   | Error occurrence | Error type, sanitized message (no paths/PII) | 90 days | Improve error handling |
   | LLM generation | Success/failure, duration, model type | 90 days | Monitor performance |
   | Network operation | Endpoint (e.g., `/api/stories`), status code | 30 days | Debug connectivity issues |

   **Never collected (even with telemetry enabled):**
   - Commit messages, code diffs, or file contents
   - Filesystem paths, usernames, or email addresses
   - Story content or profile data
   - API keys or authentication tokens

   **Opt-out anytime**: `repr config set privacy.telemetry_enabled false`

8. **No background daemons**
   - repr runs no background processes or daemons
   - Auto-generation is triggered opportunistically during CLI invocations (hooks, `repr status`, `repr generate`)
   - No "overnight sync" or background operations
   - All network calls happen in foreground, user-initiated commands

### Cloud LLM Scope

**What cloud LLM sees:**
- Only commits/repos you explicitly select for generation
- Commit messages, file paths (redacted), metadata, optional diffs
- Nothing else

**What cloud LLM never sees:**
- Full repository contents
- Local stories not selected for cloud generation
- Profile drafts unless explicitly publishing
- Untracked repositories
- Commits not queued for generation

This is architecturally enforced: only selected data is sent in the generation API call.

### Hooks Privacy

**Git hooks:**
- Run locally on your machine
- Queue commits locally only (stored in `.git/repr/queue.json`)
- No external network calls during commit (loopback only). Hooks never trigger cloud generation.
- Auto-generation only if `generation.auto_generate_on_hook = true` (disabled by default)
- Auto-generation only runs if LLM health check passes
- Stories generated locally or in cloud (based on mode; hooks always use local LLM)
- Stories pushed only if signed in + cloud enabled
- Hook location: `.git/hooks/post-commit`
- Queue location: `.git/repr/queue.json` (simple file lock for concurrency)
- Uninstall anytime: `repr hooks remove --all`

### Token Security

**Authentication tokens:**
- NEVER stored in plaintext
- Stored in OS keychain where available:
  - macOS: Keychain
  - Windows: Credential Manager
  - Linux: Secret Service (libsecret)
- Fallback: Encrypted file with locally generated key
- Config file only stores keychain reference, not the token itself

### Cloud Data Retention & Deletion

**What happens to cloud data:**
- **Story deletion** (`repr story delete`): Deleted immediately from repr.dev and all synced devices
- **Profile privacy** (`repr profile privacy private`): Profile hidden from public view; stories retained but not accessible via web
- **Account deletion**: All cloud data (stories, profile, metadata) deleted within 30 days
- **Local data**: Never touched by cloud operations; account deletion does not affect local files

**Data lifecycle:**
- Cloud stories are retained indefinitely while account is active
- No automatic expiration or archival
- You control retention via `repr story delete` or account deletion

### Content Ownership & Licensing

**Your content belongs to you:**
- repr claims no ownership over generated stories, profiles, or any content you create
- All content is yours to use, modify, share, or delete as you see fit
- repr.dev is a hosting and sync platform; you retain full rights to your work

---

## Error Messages

All error messages follow this pattern:
1. What went wrong
2. Why (explain the boundary)
3. How to fix (offer alternative)

### Cloud Without Auth

```
❌ Cloud generation requires sign-in
   repr enforces: cloud features require authentication

   Run `repr login` to enable cloud features

   Local generation is available:
   repr generate --local
```

### Push Without Auth

```
❌ Publishing requires sign-in
   Stories can only be published after authentication

   Run `repr login` to publish your profile

   Stories are saved locally: ~/.repr/stories/
```

### Cloud While Locked

```
❌ Cloud features locked
   Local-only mode is enabled (privacy setting)

   To unlock: repr privacy unlock-local

   Current mode: local only
```

### Local LLM Unreachable

```
❌ Local LLM unreachable
   Could not connect to http://localhost:11434

   Is Ollama running?
   Start: ollama serve
   Test: repr llm test

   Alternatively:
   repr generate --cloud  (requires login)
```

### Sync Conflict

```
⚠ Sync conflict detected

Story "Built auth system" exists locally and remotely with different content.

Local version (this device):
  Created: 2 days ago
  Commits: 3
  Summary: Built user authentication with JWT

Remote version (laptop):
  Created: 1 day ago
  Commits: 5
  Summary: Implemented complete auth flow with OAuth

Options:
  [l] Keep local
  [r] Keep remote
  [b] Keep both (rename local to "Built auth system (2)")
  [s] Skip (decide later)

Choose:
```

---

## User Journeys

### Journey 1: Try repr (Local-Only)

**Time:** 5 minutes

```bash
# Install
pipx install repr-cli

# Initialize
repr init
# Output: Scans repos, creates local profile, no login

# Generate first stories
repr generate --local
# Output: 3 stories generated using local LLM

# View stories
repr stories
# Output: List of 3 stories with confidence ratings

# Check status
repr status
# Output: Shows local-only mode, suggests login for cloud

# User decides: "I like this, let me try cloud features"
repr login
```

**What happened:**
- User tried repr without commitment
- Saw immediate value (3 stories generated)
- No data sent to cloud
- Login becomes a voluntary upgrade

---

### Journey 2: Daily Passive Use (Hooks)

**Time:** Ongoing, invisible

```bash
# One-time setup
repr login
repr repos add ~/code/myproject
repr hooks install --all

# Developer works normally
cd ~/code/myproject
git commit -m "Fix memory leak"
# Hook runs silently, queues commit

git commit -m "Add rate limiting"
# Queue: 2 commits

git commit -m "Update tests"
git commit -m "Refactor handler"
git commit -m "Add logging"
# Queue reaches batch size (5 commits)
# If auto_generate_on_hook=true and LLM is healthy:
# Story generated automatically during this commit (foreground, adds 1-5s latency)

# Later, developer checks in
repr status
# Output: "1 new story generated: 'Improved API reliability'"
```

**What happened:**
- Developer committed 5 times normally
- Hook queued commits locally in `.git/repr/queue.json`
- On 5th commit, if `generation.auto_generate_on_hook = true` and LLM is healthy, story generated **during the commit hook execution** (foreground operation, adds latency to git commit)
- By default (`auto_generate_on_hook = false`), commits are only queued; user runs `repr generate` manually when ready
- Developer gets passive value (profile builds itself)

**Important:** Auto-generation runs in the foreground during `git commit` if enabled. This may add 1-5 seconds to commit time depending on LLM speed. If generation fails, commit succeeds but generation is skipped.

---

### Journey 3: Manual Story Creation

**Time:** 2 minutes

```bash
# Developer finished a feature, wants to document it

# View recent commits
repr commits --limit 10
# Output: List of recent commits with hashes

# Select related commits
repr generate --commits abc123,def456,ghi789 --template resume

# Story generated
# Output: "Built user authentication system with JWT"

# Review and edit
repr story edit <story-id>
# Opens in $EDITOR, user tweaks wording

# Publish
repr push
# Story now on repr.dev/@username
```

**What happened:**
- Developer had explicit intent to create story
- Selected specific commits (not batch)
- Customized with template
- Edited before publishing
- Full control over output

---

### Journey 4: Weekly Maintenance

**Time:** 5 minutes/week

```bash
# Check weekly summary
repr summary --week
# Output: 47 commits → 4 stories, 1 needs review

# Review flagged story
repr stories review
# Interactive review: Approve/Edit/Regenerate

# Update profile
repr profile update --preview
# Shows diff: 4 new stories, tech stack updated

# Publish
repr profile update
# Profile published to repr.dev/@username

# Check analytics
repr status
# Output: 23 profile views, top story has 8 views
```

**What happened:**
- Developer maintains profile weekly
- Reviews auto-generated content
- Publishes with confidence
- Gets feedback (views)

---

### Journey 5: Sharing Profile

**Time:** 1 minute

```bash
# Get profile link
repr profile link
# Output: https://repr.dev/@alice

# Export as PDF for application
repr profile export --format pdf --output resume.pdf
# PDF saved

# Share specific story
repr story link abc123
# Output: https://repr.dev/@alice/stories/abc123

# Get embed code for personal site
repr story link abc123
# Shows embed code
```

**What happened:**
- Developer shared profile multiple ways
- PDF for traditional applications
- Link for modern sharing
- Embed for personal website

---

## Edge Cases & Implementation Details

### Repo Identity & Path Changes

**Problem:** Repos are tracked by filesystem path, but paths can change (move, rename, different paths across devices).

**Solution:**
- Internally identify repos by stable ID: random UUID generated at first track and stored in `.git/repr/repo_id`
- This ID is repo-intrinsic (stored within the repo) and portable across devices
- **Privacy-safe**: Does not encode or hash filesystem paths; no risk of path recovery from ID
- Store display path separately in config
- On path change detection:
  ```bash
  ⚠ Repository path changed
    Old: ~/code/old-name
    New: ~/code/new-name
    Repo ID: 8f3e4c2a-1b5d-4a7e-9c8f-2d6b3e5a7f1c

  Update path in config? [y/N]
  ```

**Cross-device sync:**
- Repos matched by stable ID (UUID stored in `.git/repr/repo_id`), not path
- Paths can differ across machines (e.g., `/Users/alice/code/project` on Mac, `~/code/project` on Linux)
- Stories are repo-ID-linked, so sync works regardless of path
- **Security**: Repo IDs are locally generated UUIDs; no path information is encoded or hashed

---

### Multi-User Machines & CI Environments

**Problem:** Shared workstations or CI runners could leak stories across users or unexpectedly attempt cloud operations.

**Solution:**

**Environment variable overrides:**
- `REPR_HOME` - Override data directory (default: `~/.repr`)
- `REPR_MODE` - Force mode: `local` or `cloud`
- `REPR_CI` - CI-safe defaults (disable hooks, force local, no prompts)

**CI usage example:**
```bash
# In CI environment
export REPR_CI=true
export REPR_MODE=local
repr generate --local  # Safe, never attempts cloud even if login present
```

**Multi-user safety:**
- `~/.repr` is per-user (standard Unix permissions)
- No global config or shared state
- Each user has isolated data directory

---

### Token Limits & Large Repos

**Problem:** Huge repos or many commits can exceed cloud LLM token limits.

**Solution:**

**Token budget enforcement:**
- Cloud generation caps payload at **50 commits or 100k tokens** per request
- CLI automatically splits into batches if needed:
  ```bash
  repr generate --cloud

  ⚠ 150 commits queued (exceeds 50-commit limit)

  Will split into 3 batches:
    Batch 1: commits 1-50 (est. 80k tokens)
    Batch 2: commits 51-100 (est. 75k tokens)
    Batch 3: commits 101-150 (est. 60k tokens)

  Continue? [y/N]
  ```

**User control:**
- `--batch-size <n>` limits commits per story
- `--commits <hashes>` manually selects specific commits
- Dry run shows token estimate before sending

---

### Redaction Beyond Paths

**Additional PII/security concerns:**
- Commit messages can contain secrets, customer names, tickets
- Author names/emails may be sensitive
- Filenames can leak customer data

**Extended redaction options (config):**
```json
"llm": {
  "cloud_redact_paths": true,
  "cloud_redact_emails": true,
  "cloud_redact_patterns": ["TICKET-\\d+", "customer-\\w+"],
  "cloud_allowlist_repos": ["public-repo", "oss-project"]
}
```

**Behavior:**
- `cloud_redact_emails`: Strip author emails from commit metadata
- `cloud_redact_patterns`: Regex-based scrubbing of commit messages (replace with `[REDACTED]`)
- `cloud_allowlist_repos`: Only these repos can use cloud generation (others forced to local)

**Example:**
```bash
repr generate --cloud --dry-run

Commit message: "Fix TICKET-1234 for customer-acme auth issue"
After redaction: "Fix [REDACTED] for [REDACTED] auth issue"
```

---

### Cloud Data Retention - Backups & Logs

**User question:** "You said account deletion removes data in 30 days. What about backups?"

**Explicit policy:**
- **Active systems:** Stories deleted immediately on `repr story delete` or account deletion
- **Encrypted backups:** Operational backups may retain encrypted snapshots for up to **90 days** after deletion
- **Access logs:** Request logs (IP, timestamp, endpoint) retained for **30 days** for security/debugging
- **Analytics:** If telemetry enabled, anonymized aggregate stats retained indefinitely (no PII)

**Compliance:**
- GDPR "right to be forgotten": Honored for active data; backup retention disclosed
- User can request full data export before deletion: `repr data backup`

---

## Edge Cases & Decisions

### 1. User generates stories locally, then logs in

**Decision:** Don't auto-upload local stories at login.

**Flow:**
```bash
repr login
✓ Signed in

You have 10 local stories.
Run `repr sync` to review and upload them.

repr sync
# Shows preview of 10 stories
# User confirms upload
```

**Why:** Login is just authentication. Upload is a separate consent moment.

---

### 2. User on multiple devices with different local stories

**Decision:** Sync shows conflicts, user resolves.

**Flow:**
```bash
# On laptop
repr generate --local  # Story A

# On desktop
repr generate --local  # Story B (same commits, different)

# On laptop, user logs in
repr sync
# Uploads Story A

# On desktop, user logs in
repr sync
# Conflict: Story A (remote) vs Story B (local)
# User chooses: keep remote, keep local, or keep both
```

---

### 3. User wants to prevent specific repo from auto-publishing

**Decision:** Per-repo settings in config.

**Flow:**
```bash
repr repos pause ~/code/work-project
# Auto-tracking paused
# Commits still tracked locally
# Stories not auto-generated

# Manual generation still works
repr generate --repo ~/code/work-project --local
# Story generated locally, not pushed
```

---

### 4. User accidentally publishes sensitive story

**Decision:** Delete from web + CLI.

**Flow:**
```bash
repr story delete abc123
⚠ This will delete locally and from repr.dev
Continue? [y/N]

# After delete
repr sync
# Story removed from all devices
```

---

### 5. Local LLM fails during generation

**Decision:** Error with clear fallback.

**Flow:**
```bash
repr generate --local

❌ Local LLM generation failed
   Error: Connection refused (http://localhost:11434)

   Is Ollama running?
   Start: ollama serve
   Test: repr llm test

   Alternatively:
   repr generate --cloud  (requires login)
```

**No silent fallback to cloud.** User explicitly chooses.

---

## One-Line Summary (Repeat Everywhere)

> **Cloud features require sign-in. Local generation always works offline.**

This appears in:
- `repr --help`
- `repr init` output
- Error messages
- Web docs
- README
- CLI splash screen

---

**End of Specification**
