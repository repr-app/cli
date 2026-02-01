# repr Strategy

## Core Positioning

**"repr is the developer context layer."**

Your work generates rich context. repr captures it. You decide what to do with it.

We don't prescribe what developers should do with their history — we make it *available*. Resumes, changelogs, social posts, AI agent context, proof-of-work credentials — these are all **lenses** into the same underlying data.

---

## The Mental Model

```
Your code commits (raw signal)
        │
        ▼
repr captures & enriches → stories (structured context)
        │
        ▼
Context is exposed everywhere:
├── MCP → AI agents (Claude Code, Cursor, Clawdbot)
├── API → apps and integrations
├── Web → humans (repr.dev profiles)
└── CLI → local workflows
        │
        ▼
Lenses (views into context):
├── Resume/Profile — job hunting
├── Changelog — release notes
├── Build-in-Public — social content
├── Proof — credentialing & verification
└── Ask anything — AI interprets context for any question
```

---

## Product Layers

### Core: Context Capture & Enrichment
- **Capture** — git hooks, CLI, extension, MCP make collection seamless
- **Enrich** — LLM extracts stories from commits (richer than raw diffs)
- **Store** — local-first, privacy-preserving, optional cloud sync

### Distribution: Context Exposure
- **CLI** (`pipx install repr-cli`) — local context access + MCP server
- **MCP Server** — AI agents consume context directly
- **VSCode Extension** — ambient presence, in-editor access
- **API** — programmatic access for integrations
- **Web** — human-readable profiles at repr.dev

### Lenses: Pre-built Views
- **Resume** — structured for job applications
- **Interview** — STAR-format stories for behavioral questions
- **Changelog** — formatted for release notes
- **Content** — social posts from your work
- **Proof** — verified credentialing for skills

### Monetization Paths (Phase 2+)
| Path | Model | Who Pays |
|------|-------|----------|
| Direct placement | Toptal-style, take a cut | Companies hiring |
| Lead gen | Sell qualified leads to Paraform, Braintrust, agencies | Platforms/agencies |
| Recruiter seats | Search/filter access to talent pool | Recruiters |
| Premium profiles | Boost, verified badge | Devs (optional) |

---

## Why Context Layer Wins

### The Insight
Every use case (resumes, content, changelogs, AI context) needs the **same underlying data** — rich, structured information about what you built. By focusing on capture and enrichment first, we enable all use cases instead of optimizing for one.

### Phase 1: Context Capture
- **CLI + MCP + Extension** — multiple touchpoints for seamless capture
- **Single-player value** — works immediately, no network effects needed
- **Data moat** — the longer devs use it, the richer their context becomes
- **AI-native** — MCP makes context available to the tools devs already use

### Phase 2: Lenses & Distribution
- Pre-built lenses for common use cases (resume, content, changelog)
- Web profiles for human consumption
- API for third-party integrations

### Phase 3: Monetization
- Recruiting becomes a lens, not the identity
- By the time you monetize, you have rich context no competitor has
- "Your context generates better applications" — natural extension

---

## Why Not Lead With Any Single Lens

1. **Limits the product** — "resume tool" or "content tool" boxes you in
2. **Narrow windows** — people only use resume tools when job hunting, content tools sporadically
3. **Context is evergreen** — capture happens continuously, lenses are used on-demand
4. **AI shift** — the future is agents querying context, not humans picking templates

---

## Target Segments (Who Needs Context)

| Segment | Context Need |
|---------|--------------|
| **AI-native devs** | "I want my coding agent to actually know my patterns and history" |
| Juniors / bootcamp grads | "How do I prove I can code with no job history?" (proof lens) |
| Contractors / freelancers | "I need a portfolio fast for this pitch" (resume lens) |
| Indie hackers | "I want to build in public but don't have time to write" (content lens) |
| Team leads | "What did my team actually ship this sprint?" (changelog lens) |

The AI-native segment is new and underserved. Every dev using Claude Code, Cursor, or Copilot would benefit from their agent having persistent context about their work.

---

## The Moat

**Context compounds.**

repr captures developers continuously — every commit adds to their context layer. By the time they need *any* lens (resume, content, proof), we have 6-12 months of rich, structured history.

Competitors who build single-purpose tools (resume builders, content generators) start from zero each time. We start with context that already exists.

---

## Landing Page Messaging

**Do say:**
- "Your developer context, always ready"
- "repr captures what you build. You decide what to do with it."
- "Resumes, changelogs, social posts — all from the same context"
- "Works with Claude Code, Cursor, and any MCP-compatible agent"
- "Privacy-first: your code never leaves your machine"

**Lens-specific messaging (for feature pages):**
- Resume: "Your resume, always current — generated from actual work"
- Content: "Ship code, get posts — content from your commits"
- Proof: "Prove you can code — verified by what you've built"
- AI: "Your agent knows you — context that follows you across tools"

---

## Key Terminology

- **"Context"** — the rich, structured data about what you build
- **"Stories"** — atomic units of work extracted from commits (the core unit)
- **"Lenses"** — pre-built views into your context (resume, content, changelog, proof)
- **"Capture"** — collecting context from your work
- **"Expose"** — making context available (MCP, API, web)

---

*Last updated: January 2026*
