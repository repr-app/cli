# Story Engine & Context Refactor

**Version:** 0.2.16  
**Date:** January 2026

The `repr` Story Engine is a major architectural shift from tracking raw commits to synthesizing **Stories** — coherent narratives of work that capture context, reasoning, and implementation details.

## Core Concepts

### 1. Stories vs Commits
Previously, `repr` treated a single commit or session as the atomic unit of work. The new Story Engine groups related commits (e.g., 10 commits for "Implement OAuth") into a single **Story**.

**Story Model:**
- **Problem**: What was broken or missing (WHY)
- **Approach**: Technical strategy and trade-offs (HOW)
- **Implementation Details**: Specific files, patterns, and APIs used (WHAT)
- **Decisions**: Key choices made during development
- **Outcome**: The end result

### 2. Story Synthesis Pipeline
The new `repr timeline synthesize` command uses LLMs (local or cloud) to:
1.  **Group** commits intelligently based on time, file overlap, and semantic similarity.
2.  **Extract** context from diffs and commit messages.
3.  **Synthesize** a coherent narrative.

```bash
# Synthesize stories from the last 4 weeks of work
repr timeline synthesize --weeks 4 --model kimi-k2.5:cloud
```

## New Data Model (.repr)

All data is stored locally in `.repr/`:
- `store.json`: The new story store containing all synthesized stories.
- `index.json`: An inverted index (keyword → story) for fast LLM retrieval.

**Note:** The old `timeline.json` is deprecated for story generation but kept for backward compatibility.

## Interactive Dashboard

A completely redesigned premium dashboard allows you to explore your work history.

```bash
repr timeline serve
```

**Features:**
- **Dark Mode UI**: Professional glassmorphism design.
- **Rich Context**: Expand stories to see implementation details and decisions.
- **Filtering**: Sort by Features, Bugfixes, Infra, etc.
- **Search**: Full-text search across all your stories.
- **Chronological Sort**: Newest stories first.

## MCP Server Integration

The `repr` Model Context Protocol (MCP) server exposes your stories to AI agents (Claude Code, Cursor, Windsurf).

**Available Tools:**
- `search_stories(query)`: Find stories by concept or keyword.
- `List_recent_stories(days)`: Get a digest of recent work.
- `get_story(id)`: Retrieve full context for a specific story.

**Agent Capability:**
Agents can now answer questions like:
> "How did we implement auth middleware last month?"
> "What changed in the billing service recently?"
> "Draft a changelog based on my recent feature work."

## Migration

If you have an existing `repr` setup:
1.  **Update**: `pip install -U repr-cli`
2.  **Synthesize**: Run `repr timeline synthesize --weeks 8` to backfill stories.
3.  **Serve**: Run `repr timeline serve` to view the new dashboard.
