#!/usr/bin/env python3
"""
Test script for Story synthesis.

Runs story synthesis on the past few weeks of commits,
loading sessions if available, and saves to .repr/store.json.

Usage:
    python test_story_synthesis.py [--project /path/to/repo] [--weeks 4]
"""

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from repr.models import CommitData, SessionContext, ReprStore, ContentIndex
from repr.story_synthesis import synthesize_stories
from repr.storage import save_repr_store, load_repr_store, create_repr_store
from repr.timeline import extract_commits_from_git, detect_project_root


async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Test story synthesis")
    parser.add_argument("--project", "-p", help="Project path (default: current dir)")
    parser.add_argument("--weeks", "-w", type=int, default=4, help="Weeks to look back")
    parser.add_argument("--batch-size", "-b", type=int, default=25, help="Commits per batch")
    parser.add_argument("--model", "-m", default=None, help="LLM model to use (e.g., kimi-k2.5:cloud)")
    parser.add_argument("--dry-run", action="store_true", help="Don't save results")
    args = parser.parse_args()
    
    # Determine project path
    if args.project:
        project_path = Path(args.project).resolve()
    else:
        project_path = detect_project_root(Path.cwd())
    
    if not project_path:
        print("❌ Not in a git repository")
        sys.exit(1)
    
    print(f"📁 Project: {project_path}")
    print(f"📅 Looking back: {args.weeks} weeks")
    print()
    
    # Extract commits
    days = args.weeks * 7
    print(f"🔍 Extracting commits from last {days} days...")
    
    commits = extract_commits_from_git(
        project_path,
        days=days,
        max_commits=500,
    )
    
    print(f"   Found {len(commits)} commits")
    
    if not commits:
        print("❌ No commits found")
        sys.exit(1)
    
    # Load existing sessions if available
    sessions = []
    store = load_repr_store(project_path)
    if store and store.sessions:
        sessions = store.sessions
        print(f"📝 Loaded {len(sessions)} existing sessions")
    
    # Run synthesis
    print()
    print(f"🤖 Running story synthesis (batch size: {args.batch_size})...")
    
    def progress(current, total):
        print(f"   Batch {current}/{total}")
    
    try:
        kwargs = dict(
            commits=commits,
            sessions=sessions if sessions else None,
            batch_size=args.batch_size,
            progress_callback=progress,
        )
        if args.model:
            kwargs["model"] = args.model
            print(f"   Using model: {args.model}")
        
        stories, index = await synthesize_stories(**kwargs)
    except ValueError as e:
        print(f"❌ Error: {e}")
        print("   Configure API key with: repr llm byok openai <key>")
        sys.exit(1)
    
    # Results
    print()
    print("=" * 60)
    print(f"✅ Synthesized {len(stories)} stories")
    print("=" * 60)
    print()
    
    # Show stories
    for i, story in enumerate(stories[:10], 1):
        print(f"{i}. [{story.category}] {story.title}")
        print(f"   Commits: {len(story.commit_shas)} | Sessions: {len(story.session_ids)}")
        if story.problem:
            print(f"   Problem: {story.problem[:80]}...")
        print()
    
    if len(stories) > 10:
        print(f"   ... and {len(stories) - 10} more stories")
        print()
    
    # Index stats
    print("📊 Content Index Stats:")
    print(f"   Files indexed: {len(index.files_to_stories)}")
    print(f"   Keywords indexed: {len(index.keywords_to_stories)}")
    print(f"   Weeks indexed: {len(index.by_week)}")
    print()
    
    # Save
    if not args.dry_run:
        print("💾 Saving to .repr/store.json...")
        
        # Create or update store
        if not store:
            store = create_repr_store(project_path)
        
        store.commits = commits
        store.stories = stories
        store.index = index
        store.last_updated = datetime.now(timezone.utc)
        
        store_path = save_repr_store(store, project_path)
        print(f"   Saved to: {store_path}")
    else:
        print("🔍 Dry run - not saving")
    
    print()
    print("✨ Done!")


if __name__ == "__main__":
    asyncio.run(main())
