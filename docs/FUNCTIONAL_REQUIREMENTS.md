# Repr CLI: Functional Requirements

**Version:** 3.0  
**Date:** January 5, 2026  
**Author:** repr Team  
**Last Updated:** Updated to reflect current implementation (v0.2.0)

**Major Changes in v3.0:**
- **Story-centric architecture** — Stories stored locally as ULID-based files (`.md` + `.json`)
- **Local-first workflow** — No cloud required; `generate` command creates stories locally
- **Post-commit hooks** queue commits for batch generation (not auto-sync to cloud)
- **Privacy controls** — Local-only mode, BYOK providers, audit logs
- **Profile management** — Export, update, link sharing
- **VS Code Extension** deferred to Phase 2

---

## 1. Executive Summary

### Product Vision
Repr is a privacy-first developer profile tool that converts your commit history into a living professional profile. **Works locally first** — sign in later for sync and sharing.

### Core Value Proposition
> "Your work, surfaced. No blog posts. No manual updates. Just ship code."

### Public Profile Vision
Optional public profiles at `repr.dev/@{username}` — a living portfolio that updates when you push stories. Local generation always works offline.

### Key Architectural Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Local-first workflow | **Accepted** | No cloud required for generation. Privacy by default. |
| Stories as atoms | **Accepted** | ULID-based `.md` + `.json` files. Queryable, composable. |
| Tracked repos infrastructure | **Accepted** | Explicit repo tracking with pause/resume support. |
| Hook infrastructure | **Accepted** | Queues commits locally (no auto-push). Batch generation on demand. |
| Generation location | **CLI** | Local LLM support (Ollama). Cloud/BYOK optional. |
| Template system | **Accepted** | `resume`, `changelog`, `narrative`, `interview` templates. |
| Public profiles | **Optional** | Requires explicit sign-in and push. |
| Story privacy | **Per-story flags** | `is_hidden`, `is_featured`, `needs_review` per story. |
| VS Code Extension | **Deferred** | Phase 2. CLI is proven distribution channel. |

---

## 2. System Components

### 2.1 Component Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Repr CLI (v0.2.0)                           │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│  │   init   │  │ generate │  │  stories │  │   repos  │           │
│  │  --json  │  │  --json  │  │  --json  │  │  --json  │           │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘           │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│  │   week   │  │   push   │  │  hooks   │  │   llm    │           │
│  │  since   │  │   sync   │  │  --json  │  │ privacy  │           │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘           │
└─────────────────────────────────────────────────────────────────────┘
          │                │                │
          ▼                ▼                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Local Storage (~/.repr/)                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │
│  │stories/*.md  │  │stories/*.json│  │ config.json  │             │
│  │  (content)   │  │  (metadata)  │  │tracked_repos │             │
│  └──────────────┘  └──────────────┘  └──────────────┘             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │
│  │profiles/*.md │  │.git/repr/    │  │  audit/*.log │             │
│  │  (exports)   │  │queue.json    │  │ (privacy)    │             │
│  └──────────────┘  └──────────────┘  └──────────────┘             │
└─────────────────────────────────────────────────────────────────────┘
          │                │                │
          ▼                ▼                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   Backend API (Optional, Cloud)                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐             │
│  │ POST /cli/   │  │ POST /cli/   │  │  GET /api/   │             │
│  │   stories    │  │   profile    │  │  public/u/   │             │
│  │              │  │              │  │  {username}  │             │
│  └──────────────┘  └──────────────┘  └──────────────┘             │
└─────────────────────────────────────────────────────────────────────┘
```

**Key Differences from v2.0:**
- **No extension dependency** — Pure CLI workflow
- **Local storage is source of truth** — Cloud is optional sync destination
- **Hooks queue, not sync** — Post-commit hooks only add commits to queue
- **Templates for generation** — Multiple story formats

---

## 3. Functional Requirements

### 3.1 CLI Requirements

#### FR-CLI-001: JSON Output Mode
**Priority:** P0 (Blocker)  
**Status:** ✅ Implemented  
**Description:** Commands support `--json` flag for machine-readable output.

| Command | JSON Output Schema | Status |
|---------|-------------------|--------|
| `repr repos list --json` | `[{path, last_sync, hook_installed, paused}]` | ✅ |
| `repr stories --json` | `[{id, summary, repo_name, created_at, ...}]` | ✅ |
| `repr status --json` | `{version, authenticated, repos_tracked, stories_total}` | ✅ |
| `repr whoami --json` | `{email, user_id}` | ✅ |
| `repr hooks status --json` | `[{name, path, installed, queue_count}]` | ✅ |
| `repr commits --json` | `[{sha, message, date, repo_name}]` | ✅ |

**Acceptance Criteria:**
- ✅ `--json` flag outputs valid JSON to stdout
- ✅ No Rich formatting or ANSI codes in JSON mode
- ✅ Errors output as `{"error": "message"}`

---

#### FR-CLI-002: Init Command
**Priority:** P0 (Core UX)  
**Status:** ✅ Implemented  
**Description:** First-run setup command that scans for repos and configures tracking.

```bash
repr init [path]
```

**Behavior:**
- Scans `~/code` (or specified path) for git repositories
- Shows discovered repos with commit counts and primary language
- Prompts to track repositories
- Detects local LLM (Ollama) availability
- Shows next steps (week, generate, login)

**Output:**
```
Found 12 repositories

✓ myproject (143 commits) [Python]
✓ another-repo (87 commits) [TypeScript]
...

Track these repositories? [Y/n]

Next steps:
  repr week               See what you worked on this week
  repr generate --local   Save stories permanently
  repr login              Unlock cloud sync and publishing
```

---

#### FR-CLI-003: Generate Command
**Priority:** P0 (Core)  
**Status:** ✅ Implemented  
**Description:** Generate stories from commits using local or cloud LLM.

```bash
repr generate [OPTIONS]

Options:
  --local             Use local LLM (Ollama)
  --cloud             Use cloud LLM (requires login)
  --repo PATH         Generate for specific repo
  --commits SHA,SHA   Generate from specific commits
  --batch-size N      Commits per story (default: 5)
  --template NAME     Template: resume, changelog, narrative, interview
  --prompt TEXT       Custom prompt to append
  --dry-run           Preview what would be sent
```

**Behavior:**
1. For each tracked repo (or specified `--repo`), get recent commits (50 commits, last 90 days)
2. If `--commits` specified, use those specific commits
3. Split commits into batches based on `--batch-size`
4. For each batch:
   - Build prompt from template + custom prompt
   - Call LLM (local or cloud based on flags/config)
   - Extract story from response
   - Save as `{ULID}.md` + `{ULID}.json` in `~/.repr/stories/`
5. Stories include metadata: repo, commits, dates, technologies, template used

**Default Mode Selection:**
- Not signed in → local
- Signed in + cloud allowed → cloud
- Privacy locked → local

**Templates:**
- `resume` — Professional accomplishment format
- `changelog` — Technical what/why/how format
- `narrative` — Story-driven format
- `interview` — STAR format (Situation/Task/Action/Result)

**Dry Run:**
- Shows commit count, estimated tokens
- Displays batching strategy if > 50 commits
- Shows sample commits

---

#### FR-CLI-004: Tracked Repositories Management
**Priority:** P0 (Core)  
**Status:** ✅ Implemented  
**Description:** Commands to manage tracked repositories.

```bash
repr repos [ACTION] [PATH]

Actions:
  list                List all tracked repos (default)
  add <path>          Add repository to tracking
  remove <path>       Stop tracking repository
  pause <path>        Pause auto-tracking for repository
  resume <path>       Resume auto-tracking for repository
```

**Output (list):**
```
Tracked Repositories (5)

  ✓ myproject
    /Users/me/code/myproject • hook: on
  ○ another-project
    /Users/me/code/another-project • paused
  ✗ missing-repo
    /old/path/repo • missing
```

**JSON Output:**
```json
[
  {
    "path": "/Users/me/code/myproject",
    "last_sync": "2026-01-05T10:30:00Z",
    "hook_installed": true,
    "paused": false
  }
]
```

---

#### FR-CLI-005: Quick Reflection Commands
**Priority:** P1 (UX)  
**Status:** ✅ Implemented  
**Description:** Quick summaries of recent work without generating permanent stories.

```bash
repr week [--save]
repr since <date> [--save]
repr standup [--days N]
```

**Behavior:**
- `week` — Shows commits from last 7 days
- `since` — Shows commits since date (supports "monday", "3 days ago", "2026-01-01")
- `standup` — Quick summary for standup (last 3 days by default)
- Shows top 5 commits per repo with message summaries
- `--save` flag converts to permanent story (via `generate`)

**Example Output:**
```
📊 Work since this week

myproject (12 commits):
  • Added OAuth2 integration with Google/GitHub
  • Implemented Redis caching layer
  • Fixed race condition in auth flow
  ... and 9 more

another-project (5 commits):
  • Updated dependencies
  • Fixed TypeScript errors
  ... and 3 more

Total: 17 commits

This summary wasn't saved. Run with --save to create a story.
```

---

#### FR-CLI-006: Stories Management
**Priority:** P1 (Core)  
**Status:** ✅ Implemented  
**Description:** List and manage generated stories.

```bash
repr stories [OPTIONS]

Options:
  --repo NAME         Filter by repository
  --needs-review      Show only stories needing review
  --json              Output as JSON
```

**Output:**
```
Stories (23 total)

✓ Built OAuth2 integration with Google/GitHub
  myproject • 2 days ago

⚠ Fixed race condition in authentication flow
  myproject • 1 week ago

○ Updated dependencies and fixed TypeScript errors
  another-project • 2 weeks ago
```

**Status Indicators:**
- ✓ — Pushed to repr.dev
- ⚠ — Needs review
- ○ — Local only (not pushed)

---

#### FR-CLI-007: Story Actions
**Priority:** P1  
**Status:** ✅ Implemented  
**Description:** Manage individual stories.

```bash
repr story <action> <story_id>

Actions:
  view        Show story content
  edit        Open story in $EDITOR
  delete      Delete story
  hide        Hide from profile
  feature     Pin to top of profile
```

**Example:**
```bash
repr story view 01ARYZ6S41TSV4RRFFQ69G5FAV
repr story delete 01ARYZ6S41TSV4RRFFQ69G5FAV
```

---

#### FR-CLI-008: Review Workflow
**Priority:** P1  
**Status:** ✅ Implemented  
**Description:** Interactive review for stories flagged as `needs_review`.

```bash
repr review
```

**Behavior:**
- Shows stories with `needs_review: true` one at a time
- Displays story summary, repo, commit count, content preview
- For `interview` template, shows STAR format sections
- Prompts for action: `[a] Approve [e] Edit [r] Regenerate [d] Delete [s] Skip [q] Quit`
- Approved stories have `needs_review` removed

---

#### FR-CLI-009: Cloud Operations
**Priority:** P1  
**Status:** ✅ Implemented  
**Description:** Push/sync stories to repr.dev.

```bash
repr push [OPTIONS]
repr sync
repr pull

Options (push):
  --story <id>        Push specific story
  --all               Push all unpushed stories
  --dry-run           Preview what would be pushed
```

**Behavior:**
- `push` — Upload unpushed stories to repr.dev (requires auth)
- `sync` — Push local stories + pull remote stories (bidirectional)
- `pull` — Download remote stories to local (not yet implemented)
- Privacy checks applied before pushing
- Audit log recorded for all cloud operations

**Note:** Stories are marked `pushed_at` after successful push.

---

#### FR-CLI-010: Git Hooks
**Priority:** P1  
**Status:** ✅ Implemented  
**Description:** Post-commit hooks that queue commits for story generation.

```bash
repr hooks install [--all | --repo PATH]
repr hooks remove [--all | --repo PATH]
repr hooks status [--json]
repr hooks queue <sha> --repo <path>  # Internal command
```

**Hook Behavior:**
- Post-commit hook runs after every commit
- Queues commit SHA + message in `.git/repr/queue.json`
- Does NOT trigger network calls or generation automatically
- User runs `repr generate` to process queued commits

**Hook Script:**
```bash
#!/bin/sh
# repr post-commit hook
COMMIT_SHA=$(git rev-parse HEAD)
REPO_ROOT=$(git rev-parse --show-toplevel)
repr hooks queue "$COMMIT_SHA" --repo "$REPO_ROOT" 2>/dev/null || true
```

**Queue Format (`.git/repr/queue.json`):**
```json
{
  "commits": [
    {
      "sha": "abc123...",
      "message": "Add OAuth2 integration",
      "timestamp": "2026-01-05T10:30:00Z"
    }
  ]
}
```

---

#### FR-CLI-011: LLM Configuration
**Priority:** P1  
**Status:** ✅ Implemented  
**Description:** Configure local, cloud, or BYOK LLM providers.

```bash
repr llm add <provider>           # Add BYOK provider (openai, anthropic, groq, together)
repr llm remove <provider>        # Remove BYOK provider
repr llm use <mode>               # Set default: local, cloud, byok:<provider>
repr llm configure                # Interactive local LLM setup
repr llm test                     # Test LLM connection
```

**Supported Modes:**
- **local** — Ollama or LM Studio (detects automatically)
- **cloud** — repr.dev cloud LLM (requires sign-in)
- **byok:openai** — Bring your own OpenAI key
- **byok:anthropic** — Bring your own Anthropic key
- **byok:groq** — Bring your own Groq key
- **byok:together** — Bring your own Together AI key

**Configuration Storage:**
- Tokens stored securely in OS keychain (macOS Keychain, Windows Credential Manager, Linux Secret Service)
- Config references keychain entries, not plaintext tokens

**LLM Test Output:**
```
Testing LLM connection...

Local LLM:
  ✓ Connection successful
  Provider: Ollama
  Model: llama3.2
  Response time: 234ms

Cloud LLM:
  ✗ Requires sign-in
```

---

#### FR-CLI-012: Privacy Controls
**Priority:** P1  
**Status:** ✅ Implemented  
**Description:** Privacy audit, local-only mode, and data transparency.

```bash
repr privacy explain              # One-screen privacy summary
repr privacy audit [--days N]     # Show data sent to cloud
repr privacy lock-local [--permanent]  # Disable cloud permanently
repr privacy unlock-local         # Re-enable cloud
```

**Privacy Explain Output:**
```
repr Privacy Guarantees
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ARCHITECTURE:
  ✓ No background daemons or silent uploads
  ✓ All network calls are foreground, user-initiated
  ✓ No telemetry by default (opt-in only)

CURRENT SETTINGS:
  Auth: signed in
  Mode: local
  Privacy lock: disabled
  Telemetry: disabled

LOCAL MODE NETWORK POLICY:
  Allowed: 127.0.0.1, localhost, ::1 (loopback only)
  Blocked: All external network

Run `repr privacy audit` to see all data sent
Run `repr privacy lock-local` to disable cloud permanently
```

**Audit Log:**
- Stored in `~/.repr/audit/*.log`
- Records all cloud operations: timestamp, operation, payload summary, bytes sent
- `repr privacy audit` queries these logs

---

#### FR-CLI-013: Configuration Management
**Priority:** P1  
**Status:** ✅ Implemented  
**Description:** View and modify configuration.

```bash
repr config show [key]            # Show config (or specific key)
repr config set <key> <value>     # Set config value
repr config edit                  # Open config in $EDITOR
```

**Dot Notation:**
```bash
repr config show llm.default
repr config set llm.default local
repr config set generation.batch_size 10
```

**Config Structure (`~/.repr/config.json`):**
```json
{
  "version": 3,
  "auth": {
    "token_keychain_ref": "auth_token_abc123",
    "user_id": "...",
    "email": "user@example.com"
  },
  "profile": {
    "username": null,
    "bio": null,
    "available": false
  },
  "llm": {
    "default": "local",
    "local_api_url": "http://localhost:11434/v1",
    "local_model": "llama3.2",
    "cloud_model": "gpt-4o-mini",
    "byok": {}
  },
  "generation": {
    "batch_size": 5,
    "default_template": "resume",
    "token_limit": 100000,
    "max_commits_per_batch": 50
  },
  "privacy": {
    "lock_local_only": false,
    "lock_permanent": false,
    "telemetry_enabled": false
  },
  "tracked_repos": []
}
```

---

#### FR-CLI-014: Data Management
**Priority:** P2  
**Status:** ✅ Implemented  
**Description:** Backup, restore, and manage local data.

```bash
repr data                         # Show storage stats
repr data backup [--output FILE]  # Backup all data to JSON
repr data restore <file> [--merge]  # Restore from backup
repr data clear-cache             # Clear cache (preserve stories)
```

**Storage Stats:**
```
Local Data

Stories: 23 files (1.2 MB)
Profiles: 5 files (340 KB)
Cache: 120 KB
Config: 8 KB

Total: 1.7 MB

Location: /Users/me/.repr/stories
```

**Backup Format:**
```json
{
  "version": "0.2.0",
  "exported_at": "2026-01-05T12:00:00Z",
  "stories": [
    {
      "id": "01ARYZ...",
      "content": "...",
      "metadata": {...}
    }
  ],
  "profiles": [...],
  "config": {...}
}
```

---

#### FR-CLI-015: Profile Management
**Priority:** P2  
**Status:** ✅ Implemented  
**Description:** View, update, and export profiles.

```bash
repr profile                      # View profile summary
repr profile update [--preview]   # Generate/update profile from stories
repr profile set-bio <text>       # Set bio
repr profile set-location <loc>   # Set location
repr profile set-available <bool> # Set availability
repr profile export [--format FORMAT] [--output FILE]  # Export profile
repr profile link                 # Get shareable link
```

**Export Formats:**
- `md` — Markdown (default)
- `json` — JSON with stories + metadata
- `html` — HTML (planned)
- `pdf` — PDF (planned)

**Export Example:**
```bash
repr profile export --format md > profile.md
repr profile export --format json --output profile.json
repr profile export --format md --since 2026-01-01 > recent.md
```

---

#### FR-CLI-016: Authentication
**Priority:** P0  
**Status:** ✅ Implemented  
**Description:** Device flow authentication with repr.dev.

```bash
repr login
repr logout
repr whoami [--json]
```

**Login Flow:**
1. CLI requests device code from repr.dev
2. Shows verification URL + user code
3. User visits URL in browser, enters code
4. CLI polls for authorization
5. On success, stores token in OS keychain
6. Checks for local stories and prompts to sync

**Login Output:**
```
Authenticate with repr

To sign in, visit:

  https://repr.dev/auth/device

And enter this code:

  ┌───────┐
  │ ABCD  │
  └───────┘

Waiting for authorization... 4:58
```

---

#### FR-CLI-017: Commits Command
**Priority:** P2  
**Status:** ✅ Implemented  
**Description:** List recent commits across tracked repos.

```bash
repr commits [OPTIONS]

Options:
  --repo NAME         Filter by repo name
  --limit N           Number of commits (default: 50)
  --since DATE        Since date
  --json              Output as JSON
```

**Output:**
```
Recent Commits (50)

myproject:
  abc1234  Add OAuth2 integration  2 days ago
  def5678  Fix race condition in auth  3 days ago

another-project:
  xyz9012  Update dependencies  1 week ago
```

---

#### FR-CLI-018: Health Check
**Priority:** P2  
**Status:** ✅ Implemented  
**Description:** Diagnostic checks for repr health.

```bash
repr doctor
```

**Checks:**
- ✓ Config file integrity
- ✓ Stories directory structure
- ✓ Local LLM availability
- ✓ Cloud connectivity (if signed in)
- ✓ Git installation
- ✓ Keychain access
- ⚠ Missing tracked repos
- ✗ Corrupted story files

**Output:**
```
Checking repr health...

✓ Config: valid (v3)
✓ Stories: 23 files, no corruption
✓ Local LLM: Ollama (llama3.2)
✓ Git: 2.40.0
⚠ Tracked repos: 1 missing (/old/path/repo)

Recommendations:
  1. Remove missing repo: repr repos remove /old/path/repo
```

---

#### FR-CLI-019: Mode Command
**Priority:** P2  
**Status:** ✅ Implemented  
**Description:** Show current execution mode and capabilities.

```bash
repr mode
```

**Output:**
```
Mode

Data boundary: local only
Default inference: local

Local LLM: Ollama (llama3.2)

Available:
  ✓ Local generation
  ✗ Cloud generation (requires login)
  ✗ Sync (requires login)
  ✗ Publishing (requires login)
```

---

### 3.2 Backend Requirements

**Status:** Partially Implemented

#### FR-BE-001: Authentication Endpoints
**Priority:** P0  
**Status:** ✅ Implemented  
**Description:** Device flow OAuth for CLI authentication.

| Endpoint | Method | Description | Status |
|----------|--------|-------------|--------|
| `/api/cli/auth/device/code` | POST | Request device code | ✅ |
| `/api/cli/auth/device/token` | POST | Poll for token | ✅ |
| `/api/cli/user` | GET | Get current user info | ✅ |

---

#### FR-BE-002: Stories Endpoints
**Priority:** P1  
**Status:** ✅ Implemented  
**Description:** CRUD operations for commit stories.

| Endpoint | Method | Description | Status |
|----------|--------|-------------|--------|
| `POST /api/cli/stories` | POST | Create/upsert story | ✅ |
| `GET /api/cli/stories` | GET | List stories (with filters) | ✅ |
| `GET /api/cli/stories/{id}` | GET | Get single story | ✅ |
| `DELETE /api/cli/stories/{id}` | DELETE | Delete story | ✅ |

**Query Parameters (GET):**
- `repo_name` — Filter by repository
- `since` — Stories after this date (ISO or human-readable)
- `technologies` — Comma-separated tech filter
- `limit` — Max results (default: 50)
- `offset` — Pagination offset

**Story Schema:**
```sql
CREATE TABLE commit_stories (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    
    -- Content
    summary TEXT NOT NULL,
    content TEXT,  -- Full markdown story
    technologies TEXT[] DEFAULT '{}',
    
    -- Source tracking
    repo_name TEXT NOT NULL,
    repo_remote_url TEXT,
    commit_shas TEXT[] DEFAULT '{}',
    first_commit_at TIMESTAMP WITH TIME ZONE,
    last_commit_at TIMESTAMP WITH TIME ZONE,
    
    -- Stats
    files_changed INTEGER DEFAULT 0,
    lines_added INTEGER DEFAULT 0,
    lines_removed INTEGER DEFAULT 0,
    
    -- Privacy
    is_public BOOLEAN DEFAULT true,
    is_featured BOOLEAN DEFAULT false,
    is_hidden BOOLEAN DEFAULT false,
    
    -- Metadata
    content_hash TEXT,
    model_used TEXT,
    template TEXT,  -- resume, changelog, narrative, interview
    generated_locally BOOLEAN DEFAULT false,
    needs_review BOOLEAN DEFAULT false,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    UNIQUE(user_id, content_hash)
);
```

---

#### FR-BE-003: Profile Endpoints
**Priority:** P2  
**Status:** ✅ Implemented  
**Description:** Profile upload and retrieval.

| Endpoint | Method | Description | Status |
|----------|--------|-------------|--------|
| `POST /api/cli/profile` | POST | Upload profile markdown | ✅ |
| `GET /api/cli/profile` | GET | Get current profile | ✅ |
| `DELETE /api/cli/profile` | DELETE | Delete profile | ✅ |

**Note:** Profiles uploaded via CLI are stored but not automatically published. Separate "publish" action required.

---

#### FR-BE-004: Public Profile Endpoints
**Priority:** P2  
**Status:** ⚠️ Partially Implemented  
**Description:** Public profile access.

| Endpoint | Method | Description | Status |
|----------|--------|-------------|--------|
| `GET /u/{username}` | GET | Public profile HTML | ⚠️ Planned |
| `GET /api/public/u/{username}` | GET | Public profile JSON | ⚠️ Planned |
| `GET /api/public/settings` | GET | Profile settings (authed) | ✅ |
| `PUT /api/public/settings` | PUT | Update settings (authed) | ✅ |

**Username System:**
- Usernames must be unique, 3-30 chars, alphanumeric + hyphens
- Reserved usernames: `admin`, `api`, `app`, `www`, etc.
- Field: `profiles.username` (nullable)
- Field: `profiles.is_profile_public` (default: false)

---

#### FR-BE-005: Repo Profiles Endpoint
**Priority:** P2  
**Status:** ✅ Implemented  
**Description:** Per-repository profile uploads (for context).

| Endpoint | Method | Description | Status |
|----------|--------|-------------|--------|
| `POST /api/cli/repo-profile` | POST | Upload repo profile | ✅ |

**Payload:**
```json
{
  "repo_name": "myproject",
  "content": "# myproject\n\n...",
  "content_hash": "sha256...",
  "commit_count": 143,
  "primary_language": "Python",
  "technologies": ["FastAPI", "PostgreSQL"]
}
```

**Use Case:**
- CLI uploads per-repo markdown alongside stories
- Backend uses repo profiles as context for profile generation
- Not shown publicly (internal context only)

---

### 3.3 VS Code Extension Requirements

**Status:** ❌ Deferred to Phase 2

**Rationale:**
- CLI is proven distribution channel (Homebrew, pipx, binary downloads)
- Local-first workflow doesn't require IDE integration
- Extension adds complexity without clear MVP value
- Can be added later once CLI adoption is validated

**Planned Features (Phase 2):**
- Dashboard webview showing stories, repos, sync status
- Status bar indicator for pending commits
- Command palette integration
- Auto-detect workspace repos
- One-click generate/push

---

### 3.4 Public Profile Requirements

**Status:** ⚠️ Partially Specified (Backend Work Required)

---

### 3.4 Public Profile Requirements

**Status:** ⚠️ Partially Specified (Backend Work Required)

#### FR-PUB-001: Username System
**Priority:** P1  
**Status:** ⚠️ Schema Ready, UI Pending  
**Description:** Users claim unique usernames for public profile URLs.

**Schema:**
```sql
ALTER TABLE profiles ADD COLUMN username TEXT UNIQUE;
ALTER TABLE profiles ADD COLUMN is_profile_public BOOLEAN DEFAULT false;
```

**Constraints:**
- Username: 3-30 characters, alphanumeric + hyphens
- No leading/trailing hyphens
- Unique across all users
- Reserved: `admin`, `api`, `app`, `www`, `help`, `support`, etc.

**CLI Integration:**
- `repr profile link` shows profile URL (`repr.dev/@{username}`)
- Username set via web dashboard (not CLI command yet)

---

#### FR-PUB-002: Public Profile Route
**Priority:** P1  
**Status:** ⚠️ Planned  
**Description:** Publicly accessible profile page at `repr.dev/@{username}`.

**Route:** `GET /u/{username}` or `GET /@{username}`

**Behavior:**
- If username exists AND `is_profile_public = true` → render profile
- If username exists AND `is_profile_public = false` → show "Profile is private"
- If username doesn't exist → 404

**Data Sources:**
- Latest profile markdown (from `POST /api/cli/profile`)
- Public stories (`commit_stories WHERE is_public=true AND is_hidden=false`)
- Featured stories (`commit_stories WHERE is_featured=true`)
- Profile settings (bio, location, availability)

---

#### FR-PUB-003: SEO & Sharing
**Priority:** P2  
**Status:** ⚠️ Planned  
**Description:** Search engine optimization and social sharing.

**Required Tags:**
```html
<title>{Name} - Developer Profile | repr</title>
<meta name="description" content="{bio} Built with {technologies}." />
<meta property="og:title" content="{Name} - Developer Profile" />
<meta property="og:description" content="{bio}" />
<meta property="og:image" content="https://repr.dev/og/{username}.png" />
<meta property="og:url" content="https://repr.dev/@{username}" />
<meta name="twitter:card" content="summary_large_image" />
```

**OG Image Generation:**
- Dynamic per-profile: username, technologies, bio snippet
- Cached on CDN

---

## 4. Data Flow Diagrams

### 4.1 Local Generation Flow (No Cloud)

```
User runs: repr generate --local
         │
         ▼
┌─────────────────────────────────────────┐
│  CLI: Get tracked repos                 │
│  CLI: For each repo:                    │
│    - get_commits_with_diffs(count=50)   │
│    - split into batches (5 commits each)│
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│  CLI: For each batch:                   │
│    - Build prompt from template         │
│    - Call local LLM (Ollama)            │
│    - Extract story from response        │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│  CLI: Save locally:                     │
│    - ~/.repr/stories/{ULID}.md          │
│    - ~/.repr/stories/{ULID}.json        │
│                                         │
│  Metadata includes:                     │
│    - repo_name, commit_shas, dates      │
│    - technologies, template             │
│    - generated_locally: true            │
│    - needs_review: false                │
└─────────────────────────────────────────┘
         │
         ▼
      Done (no network)
```

---

### 4.2 Cloud Generation + Push Flow

```
User runs: repr generate --cloud
         │
         ▼
┌─────────────────────────────────────────┐
│  CLI: Privacy check                     │
│    - is_authenticated()                 │
│    - is_cloud_allowed()                 │
│    - log_cloud_operation()              │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│  CLI: Generate stories                  │
│    (same as local flow, but cloud LLM)  │
│    - Save to ~/.repr/stories/           │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│  User runs: repr push                   │
│    (or repr sync for bidirectional)     │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│  CLI: For each unpushed story:          │
│    POST /api/cli/stories                │
│    {summary, content, metadata}         │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│  Backend: Upsert into commit_stories    │
│    - Deduplication by content_hash      │
│    - Store with user_id                 │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│  CLI: Mark stories as pushed            │
│    - Update local metadata: pushed_at   │
└─────────────────────────────────────────┘
```

---

### 4.3 Hook-Triggered Queue Flow

```
Developer makes git commit
         │
         ▼
┌─────────────────────────────────────────┐
│  Git: Run post-commit hook              │
│    repr hooks queue <SHA> --repo <path> │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│  CLI: Append to .git/repr/queue.json    │
│    {sha, message, timestamp}            │
│    (file locking for concurrent commits)│
└─────────────────────────────────────────┘
         │
         ▼
      Done (silent, no generation yet)


Later, user runs: repr generate
         │
         ▼
┌─────────────────────────────────────────┐
│  CLI: Check .git/repr/queue.json        │
│    - Get queued commit SHAs             │
│    - get_commits_by_shas()              │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│  CLI: Generate stories from queued      │
│    (same generation flow as before)     │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│  CLI: Clear queue after successful gen  │
└─────────────────────────────────────────┘
```

---

### 4.4 Public Profile Access Flow (Future)

```
Visitor: repr.dev/@johndoe
         │
         ▼
┌─────────────────────────────────────────┐
│  CDN: Check cache (1 hour TTL)          │
│    - If hit, return cached HTML         │
│    - If miss, pass to origin            │
└─────────────────────────────────────────┘
         │ (cache miss)
         ▼
┌─────────────────────────────────────────┐
│  Backend: Lookup username               │
│    SELECT * FROM profiles               │
│    WHERE username = 'johndoe'           │
└─────────────────────────────────────────┘
         │
         ├── Not found → 404
         │
         ├── is_profile_public = false → "Private"
         │
         ▼ (public)
┌─────────────────────────────────────────┐
│  Backend: Gather data                   │
│    - Latest profile markdown            │
│    - commit_stories (is_public=true)    │
│    - Featured stories (is_featured)     │
│    - Profile settings (bio, location)   │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│  Backend: Render HTML                   │
│    - SEO meta tags                      │
│    - OG image URL                       │
│    - Structured data (JSON-LD)          │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│  CDN: Cache for 1 hour                  │
└─────────────────────────────────────────┘
```

---

## 5. Non-Functional Requirements

### NFR-001: Performance
- ✅ `--json` commands return in < 500ms (no LLM calls)
- ✅ Local generation: ~30-60s per 50 commits (Ollama llama3.2)
- ⚠️ Cloud generation: depends on API latency (typically 10-30s per batch)
- ✅ Config operations: < 100ms (atomic writes)

### NFR-002: Reliability
- ✅ Atomic config writes (temp file + rename)
- ✅ Git hook failures don't block commits (exit 0 always)
- ✅ Graceful offline mode (all features work without network)
- ✅ Corrupt story files don't crash CLI (validation on load)

### NFR-003: Security
- ✅ Tokens stored in OS keychain (not plaintext config)
- ✅ Config file: 0600 permissions (user-only read/write)
- ✅ No secrets in audit logs (redacted by default)
- ✅ All API calls over HTTPS
- ✅ Privacy controls (local-only mode, permanent lock)

### NFR-004: Compatibility
- ✅ Python 3.10+
- ✅ Cross-platform: macOS, Linux, Windows
- ✅ Git 2.0+
- ✅ Optional: Ollama for local LLM

### NFR-005: Privacy by Design
- ✅ No telemetry by default (opt-in only)
- ✅ No background processes or daemons
- ✅ All network calls are foreground, user-initiated
- ✅ Privacy audit log for transparency
- ✅ Local-only mode (permanent lock option)

---

## 6. Implementation Phases

### Phase 1: Foundation (✅ Complete — v0.2.0)
- ✅ Local story generation with templates
- ✅ Tracked repos management
- ✅ Git hooks (queue commits)
- ✅ Privacy controls + audit
- ✅ LLM configuration (local/cloud/BYOK)
- ✅ Authentication (device flow)
- ✅ Story management (list, view, edit, delete)
- ✅ Quick reflection commands (week, since, standup)
- ✅ Profile management (export, settings)

### Phase 2: Cloud Sync (⚠️ In Progress)
- ✅ Push stories to repr.dev
- ✅ Story endpoints (POST/GET/DELETE)
- ⚠️ Profile generation from stories (backend)
- ⚠️ Pull stories from repr.dev
- ⚠️ Sync command (bidirectional)

### Phase 3: Public Profiles (⚠️ Planned)
- ⚠️ Username claim system
- ⚠️ Public profile routes (`/@{username}`)
- ⚠️ SEO optimization
- ⚠️ OG image generation
- ⚠️ Privacy toggle UI
- ⚠️ Share functionality

### Phase 4: VS Code Extension (⚠️ Deferred)
- Dashboard webview
- Status bar integration
- Command palette commands
- Auto-detect workspace repos
- One-click generate/push

### Phase 5: Advanced Features (Backlog)
- Story regeneration with different templates
- Collaborative profiles (team repos)
- Story scoring/ranking
- Custom domains (pro feature)
- LLM chat interface
- Smart commit batching (by branch/time)

---

## 7. Success Metrics

| Metric | Target | Current | Measurement |
|--------|--------|---------|-------------|
| Time to first story | < 5 min | ~3 min | `repr init` → `repr generate` |
| CLI installs | 1,000 | — | Homebrew analytics, PyPI downloads |
| Local generation usage | > 60% | — | Stories with `generated_locally: true` |
| Hook installation rate | > 50% | — | Repos with hooks / total tracked |
| Story push rate | > 30% | — | Stories pushed / total generated |
| Username claim rate | > 20% | — | Users with username / total users |
| Public profile rate | > 40% | — | Public profiles / claimed usernames |

---

## 8. Out of Scope

| Feature | Reason |
|---------|--------|
| Real-time sync | Hooks + manual `generate` suffices. Polling adds complexity. |
| LLM chat interface | Over-engineering. Commands are sufficient. |
| Bundled venv | Cross-platform hell. Use `pipx` or binaries. |
| Backend worker infrastructure | CLI handles generation. Backend stores results. |
| Impact/complexity scoring | Premature optimization. Focus on story quality first. |
| Per-story privacy controls (v1) | Global privacy settings sufficient for MVP. |
| VS Code Extension (v1) | CLI is proven. Extension adds complexity without clear value yet. |

---

## 9. Appendix A: CLI Command Reference (Current State — v0.2.0)

```bash
# Initialization & Setup
repr init [path]                  # First-time setup, scan for repos
repr doctor                       # Health check and diagnostics

# Generation
repr generate [--local|--cloud]   # Generate stories from commits
  --repo PATH                     # Generate for specific repo
  --commits SHA,SHA               # Generate from specific commits
  --batch-size N                  # Commits per story (default: 5)
  --template NAME                 # resume, changelog, narrative, interview
  --prompt TEXT                   # Custom prompt append
  --dry-run                       # Preview without generating

# Quick Reflection
repr week [--save]                # Work since last 7 days
repr since <date> [--save]        # Work since specific date
repr standup [--days N]           # Quick standup summary (last 3 days)

# Story Management
repr stories [--repo NAME] [--needs-review] [--json]
repr story <action> <id>          # view, edit, delete, hide, feature
repr review                       # Interactive review workflow

# Repository Management
repr repos [action] [path]        # list, add, remove, pause, resume
repr commits [--repo NAME] [--limit N] [--json]

# Cloud Operations
repr push [--story ID] [--all] [--dry-run]
repr sync                         # Bidirectional sync (push + pull)
repr pull                         # Pull remote stories (planned)

# Git Hooks
repr hooks install [--all|--repo PATH]
repr hooks remove [--all|--repo PATH]
repr hooks status [--json]
repr hooks queue <sha> --repo <path>  # Internal

# LLM Configuration
repr llm add <provider>           # Add BYOK (openai, anthropic, groq, together)
repr llm remove <provider>        # Remove BYOK
repr llm use <mode>               # Set default: local, cloud, byok:<provider>
repr llm configure                # Interactive local LLM setup
repr llm test                     # Test connection

# Privacy
repr privacy explain              # Privacy summary
repr privacy audit [--days N]     # Show data sent to cloud
repr privacy lock-local [--permanent]
repr privacy unlock-local

# Configuration
repr config show [key]            # Show config (or specific key, dot notation)
repr config set <key> <value>     # Set config value
repr config edit                  # Open in $EDITOR

# Data Management
repr data                         # Show storage stats
repr data backup [--output FILE]  # Backup to JSON
repr data restore <file> [--merge]
repr data clear-cache

# Profile
repr profile                      # View profile summary
repr profile update [--preview]   # Generate from stories
repr profile set-bio <text>
repr profile set-location <loc>
repr profile set-available <bool>
repr profile export [--format FORMAT] [--output FILE]
  --format: md, json, html (planned), pdf (planned)
  --since DATE                    # Export only recent work
repr profile link                 # Get shareable link

# Authentication
repr login                        # Device flow auth
repr logout
repr whoami [--json]

# Status & Info
repr status [--json]              # Health and stats
repr mode                         # Show execution mode and capabilities
```

---

## 10. Appendix B: Configuration File Structure

**Location:** `~/.repr/config.json`  
**Version:** 3 (current)  
**Permissions:** 0600 (user read/write only)

```json
{
  "version": 3,
  "auth": {
    "token_keychain_ref": "auth_token_abc123",
    "user_id": "uuid",
    "email": "user@example.com",
    "authenticated_at": "2026-01-05T10:00:00Z",
    "litellm_keychain_ref": "litellm_key_abc123"
  },
  "profile": {
    "username": null,
    "claimed": false,
    "bio": null,
    "location": null,
    "website": null,
    "twitter": null,
    "linkedin": null,
    "available": false
  },
  "settings": {
    "default_paths": ["~/code"],
    "skip_patterns": ["node_modules", "venv", ".venv", "vendor", "__pycache__", ".git"]
  },
  "sync": {
    "last_pushed": null,
    "last_profile": null
  },
  "llm": {
    "default": "local",
    "local_provider": "ollama",
    "local_api_url": "http://localhost:11434/v1",
    "local_api_key": "ollama",
    "local_model": "llama3.2",
    "extraction_model": null,
    "synthesis_model": null,
    "cloud_model": "gpt-4o-mini",
    "cloud_send_diffs": false,
    "cloud_redact_paths": true,
    "cloud_redact_emails": false,
    "cloud_redact_patterns": [],
    "cloud_allowlist_repos": [],
    "byok": {}
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
  "tracked_repos": [
    {
      "path": "/Users/me/code/myproject",
      "last_sync": "2026-01-05T10:30:00Z",
      "hook_installed": true,
      "paused": false
    }
  ]
}
```

---

## 11. Appendix C: Story File Structure

**Location:** `~/.repr/stories/`  
**Format:** ULID-based pairs (`.md` + `.json`)

**Example: `01ARYZ6S41TSV4RRFFQ69G5FAV.md`**
```markdown
# Built OAuth2 integration with Google/GitHub

Implemented full OAuth2 authentication flow with support for Google and GitHub providers...

## Technologies
- FastAPI
- OAuth2
- Redis
- PostgreSQL

## Implementation Details
...
```

**Example: `01ARYZ6S41TSV4RRFFQ69G5FAV.json`**
```json
{
  "id": "01ARYZ6S41TSV4RRFFQ69G5FAV",
  "summary": "Built OAuth2 integration with Google/GitHub",
  "repo_name": "myproject",
  "repo_path": "/Users/me/code/myproject",
  "commit_shas": ["abc123def456", "xyz789"],
  "first_commit_at": "2026-01-01T10:00:00Z",
  "last_commit_at": "2026-01-02T15:30:00Z",
  "files_changed": 12,
  "lines_added": 450,
  "lines_removed": 120,
  "technologies": ["FastAPI", "OAuth2", "Redis"],
  "template": "resume",
  "generated_locally": true,
  "needs_review": false,
  "is_hidden": false,
  "is_featured": false,
  "is_public": true,
  "pushed_at": null,
  "created_at": "2026-01-05T12:00:00Z",
  "updated_at": "2026-01-05T12:00:00Z"
}
```

---

## 12. Open Questions

1. **Profile generation trigger:** Should `push` auto-generate profile, or require explicit `profile update`?
2. **Story merging:** If user regenerates same commits with different template, merge or replace?
3. **Username changes:** Allow after claim? Rate limit? Redirect old URLs?
4. **BYOK model selection:** Should each provider have per-model pricing display?
5. **Queue persistence:** Store queue in config.json or keep in .git/repr/?
6. **Hook conflicts:** How to handle existing post-commit hooks? Append? User prompt?
7. **Export automation:** Should `profile export` auto-push to repr.dev?
8. **Story deduplication:** content_hash on full content or just summary?

---

*Last updated: January 5, 2026 — v3.0 (Current Implementation)*
    -- Source tracking
    repo_name TEXT NOT NULL,
    repo_remote_url TEXT,
    commit_shas TEXT[] DEFAULT '{}',
    first_commit_at TIMESTAMP WITH TIME ZONE,
    last_commit_at TIMESTAMP WITH TIME ZONE,
    
    -- Stats
    files_changed INTEGER DEFAULT 0,
    lines_added INTEGER DEFAULT 0,
    lines_removed INTEGER DEFAULT 0,
    
    -- Privacy (v2 - per-story controls)
    is_public BOOLEAN DEFAULT true,      -- Visible on public profile
    is_featured BOOLEAN DEFAULT false,   -- Pinned to top of profile
    is_hidden BOOLEAN DEFAULT false,     -- Excluded from profile generation
    
    -- Metadata
    content_hash TEXT,
    model_used TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Deduplication
    UNIQUE(user_id, content_hash)
);
```

**Indexes:**
- `(user_id)` — List user's stories
- `(user_id, repo_name)` — Filter by repo
- `(user_id, last_commit_at DESC)` — Recent stories
- `GIN(technologies)` — Filter by tech

---

#### FR-BE-002: Stories API Endpoints
**Priority:** P1  
**Description:** CRUD endpoints for commit stories.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/cli/stories` | List stories (with filters) |
| `POST` | `/api/cli/stories` | Create/upsert story |
| `GET` | `/api/cli/stories/{id}` | Get single story |
| `DELETE` | `/api/cli/stories/{id}` | Delete story |

**Query Parameters (GET /stories):**
- `repo_name` — Filter by repository
- `since` — Stories after this date
- `technologies` — Comma-separated tech filter
- `limit` — Max results (default 50)
- `offset` — Pagination offset

---

#### FR-BE-003: Profile Generation from Stories
**Priority:** P2  
**Description:** Update profile generation to use stories as primary source.

**Current Flow:**
```
repo_profiles (markdown blobs) → LLM → profile_versions
```

**New Flow:**
```
commit_stories + repo_profiles + other_sources → LLM → profile_versions
```

**Behavior:**
- Stories are the preferred source for technical accomplishments
- Repo profiles provide backup/context
- Other sources (resume, LinkedIn) provide career context

---

### 3.3 VS Code Extension Requirements

#### FR-EXT-001: Installation Detection
**Priority:** P0 (Blocker)  
**Description:** Extension must detect if `repr` CLI is installed.

**Detection Logic:**
1. Run `repr --version` 
2. If exits with code 0, CLI is installed
3. If fails, show installation prompt

**Installation Prompt UI:**
```
┌─────────────────────────────────────────────────┐
│  Repr CLI not found                             │
│                                                 │
│  Install with:                                  │
│  $ pipx install repr-cli                        │
│                                                 │
│  [Copy Command]  [Open Terminal]  [Dismiss]     │
└─────────────────────────────────────────────────┘
```

---

#### FR-EXT-002: Dashboard Webview
**Priority:** P1  
**Description:** Main dashboard showing tracked repos, recent stories, and sync status.

**Sections:**
1. **Status Header**
   - Authentication status (logged in as X)
   - Last sync time across all tracked repos
   - Pending commits count

2. **Tracked Repositories** (from `repr repos list --json`)
   - List of tracked repos with sync status
   - Pending commits indicator
   - Hook installation status
   - Click repo to filter stories

3. **Recent Stories** (from `repr stories --json --limit 20`)
   - Story cards with summary, tech tags, date
   - Click to expand details
   - Filter by repo dropdown

4. **Quick Actions**
   - [Add Repository] — prompts for path, runs `repr repos add`
   - [Sync All] — runs `repr sync`
   - [Install Hooks] — runs `repr hook install --all`
   - [Open repr.dev] — opens public profile or web dashboard

---

#### FR-EXT-003: Status Bar Item
**Priority:** P1  
**Description:** Persistent status indicator in VS Code status bar.

**States:**
| State | Icon | Text | Color |
|-------|------|------|-------|
| Not installed | ⚠️ | "Repr: Not Installed" | Yellow |
| Not authenticated | 🔒 | "Repr: Login Required" | Yellow |
| Synced | ✓ | "Repr: Synced" | Green |
| Pending commits | ↻ | "Repr: 5 pending" | Blue |
| Syncing | ◐ | "Repr: Syncing..." | Blue |
| Error | ✗ | "Repr: Error" | Red |

**Click Action:** Opens Dashboard webview

**Status Detection:**
- Runs `repr status --json` periodically (every 5 minutes)
- Checks `pending_commits` count from tracked repos
- Shows pending count if > 0

---

#### FR-EXT-004: Command Palette Commands
**Priority:** P1  
**Description:** Commands accessible via Cmd+Shift+P.

| Command ID | Title | Action |
|------------|-------|--------|
| `repr.openDashboard` | Repr: Open Dashboard | Open webview |
| `repr.addRepository` | Repr: Add Repository | Prompt for path, run `repr repos add` |
| `repr.sync` | Repr: Sync Repositories | Run `repr sync` on all tracked repos |
| `repr.syncCurrent` | Repr: Sync Current Repository | Run `repr sync --repo <current>` |
| `repr.installHooks` | Repr: Install Hooks | Run `repr hook install --all` |
| `repr.showStories` | Repr: Show Recent Stories | Open stories panel |
| `repr.login` | Repr: Login | Run `repr login` (opens browser) |
| `repr.logout` | Repr: Logout | Run `repr logout` |
| `repr.shareProfile` | Repr: Share Public Profile | Copy public profile URL to clipboard |
| `repr.openPublicProfile` | Repr: Open Public Profile | Open public profile in browser |

---

#### FR-EXT-005: Automatic Update Detection
**Priority:** P2  
**Description:** Periodically detect new commits in tracked repos and update status.

**Behavior:**
1. On workspace open, check if current workspace contains tracked repos
2. Every 30 minutes, run `repr status --json` to check pending commits
3. Update status bar with pending count
4. Optionally show notification: "You have 5 pending commits. Sync now?"

**Settings:**
```json
{
  "repr.autoDetect.enabled": true,
  "repr.autoDetect.intervalMinutes": 30,
  "repr.autoDetect.showNotification": true,
  "repr.autoDetect.autoSync": false
}
```

**Note:** This replaces the need for git file watchers - we rely on periodic status checks and git hooks for real-time updates.

---

#### FR-EXT-006: Output Channel
**Priority:** P1  
**Description:** Dedicated output channel for CLI command logs.

**Behavior:**
- All CLI commands log to "Repr" output channel
- Show command being run
- Show stdout/stderr
- Show exit code and duration

---

### 3.4 Public Profile Requirements

#### FR-PUB-001: Username System
**Priority:** P1  
**Description:** Users must have unique usernames for public profile URLs.

**Schema Addition:**
```sql
ALTER TABLE profiles ADD COLUMN username TEXT UNIQUE;
ALTER TABLE profiles ADD COLUMN is_profile_public BOOLEAN DEFAULT false;
```

**Constraints:**
- Username: 3-30 characters, alphanumeric + hyphens, no leading/trailing hyphens
- Must be unique across all users
- Reserved usernames: `admin`, `api`, `app`, `www`, `help`, `support`, etc.

**Claim Flow:**
1. User visits Settings → Profile
2. Enters desired username
3. Backend validates uniqueness + format
4. If valid, claim username

---

#### FR-PUB-002: Public Profile Route
**Priority:** P1  
**Description:** Publicly accessible profile page at `repr.dev/u/{username}`.

**Route:** `GET /u/{username}`

**Behavior:**
- If username exists AND `is_profile_public = true`, render public profile
- If username exists AND `is_profile_public = false`, show "Profile is private"
- If username doesn't exist, show 404

**Response (HTML):**
```
┌─────────────────────────────────────────────────────────────────┐
│  repr.dev/u/johndoe                               [Share] 📋    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  👤 John Doe                                                    │
│  Full-stack engineer • San Francisco                            │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  Summary                                                 │   │
│  │  Backend engineer specializing in distributed systems... │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  💡 Featured Work                                      (if any) │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ ⭐ Built real-time collaboration engine                  │   │
│  │    React • WebSockets • Redis • Jan 2026                 │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  📊 Technologies                                                │
│  [Python] [TypeScript] [React] [FastAPI] [PostgreSQL]          │
│                                                                 │
│  📁 Recent Work                                 [View all →]    │
│  • Implemented OAuth2 with refresh tokens                      │
│  • Added Redis caching layer                                   │
│  • Built WebSocket streaming                                   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

#### FR-PUB-003: Public Profile API
**Priority:** P1  
**Description:** JSON API for public profile data (for embeds, integrations).

**Route:** `GET /api/public/u/{username}`

**Response (JSON):**
```json
{
  "username": "johndoe",
  "display_name": "John Doe",
  "summary": "Backend engineer specializing in...",
  "technologies": ["Python", "TypeScript", "React", "FastAPI"],
  "featured_stories": [
    {
      "id": "uuid",
      "summary": "Built real-time collaboration engine",
      "technologies": ["React", "WebSockets", "Redis"],
      "date": "2026-01"
    }
  ],
  "recent_stories": [...],
  "stats": {
    "total_stories": 45,
    "total_repos": 12,
    "technologies_count": 18
  },
  "profile_url": "https://repr.dev/u/johndoe"
}
```

**Headers:**
- `Cache-Control: public, max-age=3600` (1 hour CDN cache)

---

#### FR-PUB-004: Privacy Toggle
**Priority:** P1  
**Description:** User can toggle profile public/private.

**UI Location:** Settings → Profile → Privacy

**Options:**
| Setting | Default | Description |
|---------|---------|-------------|
| Profile Public | `false` | Enable `repr.dev/u/{username}` |
| Show Email | `false` | Display email on public profile |
| Show Recent Stories | `true` | Show recent work on profile |
| Indexable | `true` | Allow search engines to index |

---

#### FR-PUB-005: SEO Meta Tags
**Priority:** P2  
**Description:** Public profiles should be search engine optimized.

**Required Tags:**
```html
<title>John Doe - Full-stack Engineer | repr.dev</title>
<meta name="description" content="Backend engineer specializing in distributed systems. Built with Python, TypeScript, React, FastAPI." />
<meta property="og:title" content="John Doe - Full-stack Engineer" />
<meta property="og:description" content="Backend engineer specializing in..." />
<meta property="og:image" content="https://repr.dev/og/johndoe.png" />
<meta property="og:url" content="https://repr.dev/u/johndoe" />
<meta name="twitter:card" content="summary_large_image" />
<link rel="canonical" href="https://repr.dev/u/johndoe" />
```

---

#### FR-PUB-006: Share Functionality
**Priority:** P2  
**Description:** Easy sharing from profile and extension.

**Share Options:**
- Copy URL to clipboard
- Generate shareable card image (OG image)
- One-click share to LinkedIn, Twitter

**Extension Integration:**
- Command: `repr.shareProfile` — Copy public profile URL
- Status bar context menu: "Copy Profile Link"

---

## 4. Data Flow Diagrams

### 4.1 Analysis Flow (Tracked Repos)

```
User runs "repr sync" (or post-commit hook triggers it)
         │
         ▼
┌─────────────────────────────────────────┐
│  CLI: Get tracked repos from config     │
│  CLI: Check each for commits since      │
│       last_sync timestamp                │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│  CLI: For repos with new commits:       │
│  - Extract commits with diffs (--since) │
│  - Batch commits (25 per batch)         │
│  - LLM extraction (parallel)            │
│  - LLM synthesis                        │
└─────────────────────────────────────────┘
         │
         ├──────────────────┐
         ▼                  ▼
┌─────────────────┐  ┌─────────────────┐
│ POST /cli/      │  │ POST /cli/      │
│ repo-profile    │  │ stories         │
│ (markdown)      │  │ (structured)    │
└─────────────────┘  └─────────────────┘
         │                  │
         ▼                  ▼
┌─────────────────┐  ┌─────────────────┐
│ repo_profiles   │  │ commit_stories  │
│ table + S3      │  │ table           │
└─────────────────┘  └─────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│  CLI: Update last_sync timestamp        │
│       in tracked repos config           │
└─────────────────────────────────────────┘
```

### 4.2 Hook-Triggered Sync Flow

```
Developer makes git commit in tracked repo
         │
         ▼
┌─────────────────────────────────────────┐
│  Git post-commit hook triggers:         │
│  repr sync --repo <path> --background   │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│  CLI: Check if new commits exist        │
│       since last_sync                   │
└─────────────────────────────────────────┘
         │
         ├─── No new commits → Exit silently
         │
         ▼ (has new commits)
┌─────────────────────────────────────────┐
│  CLI: Run incremental analysis          │
│       (same as "Analysis Flow" above)   │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│  Stories pushed to backend              │
│  last_sync updated                      │
│  (All silent, non-blocking)             │
└─────────────────────────────────────────┘
```

### 4.3 Profile Generation Flow

```
User requests profile generation (web or extension)
         │
         ▼
┌─────────────────────────────────────────┐
│  Backend: Gather data sources           │
│  - commit_stories (primary)             │
│  - repo_profiles (context)              │
│  - resume (S3)                          │
│  - linkedin (S3)                        │
│  - github contributions                 │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│  Backend: LLM synthesis                 │
│  - Select relevant stories              │
│  - Combine with other sources           │
│  - Generate markdown profile            │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│  profile_versions table + S3            │
└─────────────────────────────────────────┘
```

### 4.4 Public Profile Access Flow

```
Visitor accesses repr.dev/u/johndoe
         │
         ▼
┌─────────────────────────────────────────┐
│  CDN: Check cache                       │
│  - If cached & fresh, return            │
│  - If stale, pass to origin             │
└─────────────────────────────────────────┘
         │ (cache miss)
         ▼
┌─────────────────────────────────────────┐
│  Backend: Lookup username               │
│  - SELECT * FROM profiles               │
│    WHERE username = 'johndoe'           │
└─────────────────────────────────────────┘
         │
         ├── Not found → 404 page
         │
         ├── is_profile_public = false → "Private" page
         │
         ▼ (public)
┌─────────────────────────────────────────┐
│  Backend: Gather public data            │
│  - Latest profile_version               │
│  - commit_stories WHERE is_public=true  │
│  - Featured stories (is_featured=true)  │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│  Render HTML with:                      │
│  - SEO meta tags                        │
│  - OG image URL                         │
│  - Structured data (JSON-LD)            │
└─────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│  CDN: Cache response (1 hour)           │
└─────────────────────────────────────────┘
```

---

## 5. Non-Functional Requirements

### NFR-001: Performance
- CLI `--json` commands must return in < 500ms (no LLM calls)
- Extension status check must complete in < 1s
- Analysis of 100 commits should complete in < 2 minutes

### NFR-002: Reliability
- Config file writes must be atomic (no corruption on crash)
- CLI must gracefully handle network failures
- Extension must work offline (show cached data)

### NFR-003: Security
- CLI tokens stored in `~/.repr/config.json` with 0600 permissions
- No secrets in extension settings
- All API calls over HTTPS

### NFR-004: Compatibility
- CLI: Python 3.10+
- Extension: VS Code 1.74+
- Backend: Existing Supabase + S3 infrastructure

---

## 6. Implementation Phases

### Phase 1: Foundation (Week 1)
**Goal:** CLI commands work with JSON output, extension can communicate with CLI

| Task | Component | Effort |
|------|-----------|--------|
| Add `--json` to `repos`, `status`, `sync`, `hook` | CLI | 2h |
| Add `repr repos` command (list/add/remove/scan) | CLI | 3h |
| Add `repr sync` command | CLI | 3h |
| Add `repr hook` command (install/remove/status) | CLI | 2h |
| Atomic config writes | CLI | 30m |
| Basic extension scaffold | Extension | 2h |
| Installation detection | Extension | 1h |
| Command palette commands | Extension | 2h |
| Status bar item | Extension | 1h |

### Phase 2: Stories (Week 2)
**Goal:** Stories as queryable data

| Task | Component | Effort |
|------|-----------|--------|
| Add `commit_stories` table | Backend | 1h |
| Add `/api/cli/stories` endpoints | Backend | 2h |
| Add `repr stories --json` | CLI | 2h |
| Update `analyze` to push stories | CLI | 3h |
| Dashboard webview (basic) | Extension | 4h |

### Phase 3: Auto-Sync & Hooks (Week 3)
**Goal:** Automatic syncing workflow

| Task | Component | Effort |
|------|-----------|--------|
| Implement hook installation logic | CLI | 3h |
| Test hooks on macOS/Linux/Windows | CLI | 2h |
| Auto-detect tracked repos in workspace | Extension | 2h |
| Periodic status checking | Extension | 2h |
| Dashboard with repos & stories | Extension | 4h |
| Profile gen from stories | Backend | 4h |

### Phase 4: Public Profiles (Week 4)
**Goal:** Shareable profile at `repr.dev/u/{username}`

| Task | Component | Effort |
|------|-----------|--------|
| Username column + validation | Backend | 1h |
| Username claim UI | Web | 2h |
| Public profile route (`/u/{username}`) | Backend | 3h |
| Public profile page (HTML) | Web | 4h |
| Privacy toggle UI | Web | 1h |
| SEO meta tags + OG image | Web | 2h |
| Share button + copy URL | Web | 1h |
| `repr.shareProfile` command | Extension | 30m |

### Phase 5: Future (Backlog)
- Workspace-level config (`.repr.json` in repo root)
- Per-story privacy controls (show/hide individual stories)
- Featured stories curation
- Story scoring/ranking
- Custom domains (pro feature)
- LLM chat interface (if users request)
- Smart commit batching (group related commits by time/branch)

---

## 7. Out of Scope (Explicitly Rejected)

| Feature | Reason |
|---------|--------|
| LLM chat router | Over-engineering for simple command set |
| Bundled venv management | Cross-platform support nightmare |
| Real-time file watchers | Hooks + periodic polling suffices |
| Backend worker infrastructure | CLI handles synthesis for now |
| Impact/complexity scoring | Premature optimization |
| Local profile files as source of truth | Tracked repos config + remote stories are truth |

---

## 8. Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Time to first story | < 5 minutes | User runs `repr analyze` successfully |
| Extension adoption | 50% of CLI users | Extension installs vs CLI downloads |
| Hook installation rate | > 60% of tracked repos | Repos with hooks / total tracked repos |
| Auto-sync accuracy | > 90% | Successful syncs / total commits |
| Profile freshness | < 1 week stale | Time since last story added |
| Username claim rate | > 30% of users | Users with username / total users |
| Public profile rate | > 50% of usernames | Public profiles / claimed usernames |
| Profile shares | 2+ per user | Share clicks per user with public profile |
| Profile page views | 10+ per public profile | Monthly views per public profile |

---

## 10. Configuration File Structure

### Tracked Repos Config (`~/.repr/config.json`)

```json
{
  "auth": {
    "access_token": "...",
    "refresh_token": "...",
    "user_email": "user@example.com"
  },
  "llm": {
    "extraction_model": "gpt-4o-mini",
    "synthesis_model": "gpt-4o",
    "local_api_url": null,
    "local_api_key": null
  },
  "tracked_repos": [
    {
      "path": "/Users/me/code/myproject",
      "name": "myproject",
      "last_sync": "2026-01-04T10:30:00Z",
      "last_sync_sha": "abc123def456",
      "hook_installed": true,
      "added_at": "2026-01-01T12:00:00Z"
    },
    {
      "path": "/Users/me/code/another-project",
      "name": "another-project",
      "last_sync": "2026-01-02T15:00:00Z",
      "last_sync_sha": "xyz789",
      "hook_installed": false,
      "added_at": "2026-01-01T12:00:00Z"
    }
  ],
  "settings": {
    "default_paths": ["~/code"],
    "auto_sync_enabled": false,
    "dev_mode": false
  }
}
```

**Notes:**
- `last_sync_sha` is used for incremental analysis (`--since` flag)
- `hook_installed` tracks whether post-commit hook is active
- Local profile markdown files in `~/.repr/profiles/` are just cache artifacts

---

## 11. Open Questions

1. **Story granularity:** How many commits = 1 story? Current: 25. Is this optimal?
2. **Deduplication:** If user re-analyzes same commits, should we create new stories or update existing?
3. **Story editing:** Should users be able to edit/delete individual stories?
4. **Username changes:** Allow users to change username? Rate limit? History?
5. **OG image generation:** Static template or dynamic per-profile? Cost/complexity?
6. **Profile caching:** How long to cache public profiles? Invalidation strategy?
7. **Abuse prevention:** How to prevent username squatting? Require verification?
8. **Hook conflicts:** How to handle existing post-commit hooks? Append? Replace? User prompt?
9. **Sync failure handling:** If sync fails (network issue), should we retry? Queue for later?
10. **Workspace detection:** Should extension auto-add repos it finds in workspace to tracked list?

---

## 12. Appendix A: CLI Command Reference (Target State)

```
# Repository Management
repr repos list                List tracked repositories
  --json                       Output as JSON

repr repos add <path>          Add repository or directory to tracking
repr repos remove <path>       Stop tracking a repository
repr repos scan                Auto-discover repos in configured paths

# Syncing
repr sync                      Sync all tracked repos (analyze + push)
  --repo <path>                Sync specific repository
  --all                        Force sync all (ignore last_sync)
  --background                 Run silently (for hooks)
  --json                       Output progress as JSON

# Hooks
repr hook install              Install post-commit hooks
  --repo <path>                Install in specific repo
  --all                        Install in all tracked repos

repr hook remove               Remove post-commit hooks
  --repo <path>                Remove from specific repo
  --all                        Remove from all tracked repos

repr hook status               Show hook installation status
  --json                       Output as JSON

# One-off Analysis
repr analyze <paths>           Analyze repos (one-off, auto-pushes)
  --json                       Output progress as JSON
  --since <sha|date>           Only analyze commits after this point
  --verbose                    Show detailed logs
  --offline                    Stats only, no AI (no push)
  --local                      Use local LLM
  --model <name>               Local model to use

# Stories
repr stories                   List commit stories
  --json                       Output as JSON
  --repo <name>                Filter by repository
  --since <date>               Filter by date
  --limit <n>                  Max stories (default: 50)
  --technologies <list>        Filter by tech (comma-separated)

# Status & Info
repr status                    Show CLI status
  --json                       Output as JSON

repr whoami                    Show user info + public profile URL
  --json                       Output as JSON

repr config                    Show configuration
  --json                       Output as JSON

repr config-set                Configure CLI
  --extraction-model <model>   Model for extraction
  --synthesis-model <model>    Model for synthesis
  --local-api-url <url>        Local LLM API endpoint
  --local-api-key <key>        Local LLM API key
  --clear                      Clear all LLM settings

# Authentication
repr login                     Authenticate with repr.dev
repr logout                    Clear authentication

# Deprecated (hidden, for debugging only)
repr profiles                  List local cache files
repr view                      View local profile markdown
repr push                      Manual push (use 'sync' instead)
```

---

## 13. Appendix B: Extension Settings (Target State)

```json
{
  "repr.cli.path": "",
  "repr.autoDetect.enabled": true,
  "repr.autoDetect.intervalMinutes": 30,
  "repr.autoDetect.showNotification": true,
  "repr.autoDetect.autoSync": false,
  "repr.dashboard.showOnStartup": false,
  "repr.statusBar.enabled": true,
  "repr.hooks.autoInstall": false
}
```

---

## 14. Appendix C: Extension Commands (Complete)

| Command ID | Title | Description |
|------------|-------|-------------|
| `repr.openDashboard` | Repr: Open Dashboard | Open main dashboard webview |
| `repr.addRepository` | Repr: Add Repository | Prompt for path, run `repr repos add` |
| `repr.sync` | Repr: Sync Repositories | Run `repr sync` on all tracked repos |
| `repr.syncCurrent` | Repr: Sync Current Repository | Run `repr sync --repo <current>` |
| `repr.installHooks` | Repr: Install Hooks | Run `repr hook install --all` |
| `repr.showStories` | Repr: Show Stories | Open stories panel |
| `repr.login` | Repr: Login | Authenticate with repr.dev |
| `repr.logout` | Repr: Logout | Clear authentication |
| `repr.shareProfile` | Repr: Share Public Profile | Copy public profile URL to clipboard |
| `repr.openPublicProfile` | Repr: Open Public Profile | Open public profile in browser |

---

## 15. Appendix D: Reserved Usernames

The following usernames are reserved and cannot be claimed:

```
admin, administrator, api, app, apps, auth, blog, cdn, 
dashboard, dev, docs, download, downloads, email, 
enterprise, faq, features, feedback, graphql, help, 
home, info, jobs, legal, login, logout, mail, 
marketing, me, news, null, oauth, official, pricing, 
privacy, profile, repr, root, security, settings, 
signin, signout, signup, sitemap, sso, static, 
status, support, system, team, teams, terms, test, 
undefined, user, users, web, webhook, webhooks, www
```

