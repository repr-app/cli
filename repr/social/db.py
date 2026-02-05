"""
Database operations for social posts feature.

Extends the main repr database with social-specific tables.
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
from contextlib import contextmanager

from .models import (
    SocialPlatform,
    SocialDraft,
    SocialConnection,
    DraftStatus,
    ConnectionStatus,
)


def get_social_db_path() -> Path:
    """Get social database path."""
    from ..storage import REPR_HOME
    return REPR_HOME / "social.db"


class SocialDatabase:
    """Database for social posts and OAuth connections."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or get_social_db_path()
        self._ensure_dir()
        self.init_schema()

    def _ensure_dir(self):
        """Ensure the database directory exists."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_schema(self):
        """Initialize database schema."""
        with self.connect() as conn:
            # Social drafts table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS social_drafts (
                    id TEXT PRIMARY KEY,
                    platform TEXT NOT NULL,
                    story_id TEXT,
                    title TEXT,
                    content TEXT NOT NULL,
                    thread_parts TEXT,
                    url TEXT,
                    subreddit TEXT,
                    status TEXT DEFAULT 'draft',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    posted_at TEXT,
                    scheduled_for TEXT,
                    post_id TEXT,
                    post_url TEXT,
                    error_message TEXT,
                    generation_prompt TEXT,
                    auto_generated INTEGER DEFAULT 1
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_drafts_platform ON social_drafts(platform)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_drafts_status ON social_drafts(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_drafts_story ON social_drafts(story_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_drafts_created ON social_drafts(created_at)")

            # OAuth connections table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS social_connections (
                    id TEXT PRIMARY KEY,
                    platform TEXT UNIQUE NOT NULL,
                    status TEXT DEFAULT 'disconnected',
                    access_token TEXT,
                    refresh_token TEXT,
                    token_expires_at TEXT,
                    platform_user_id TEXT,
                    platform_username TEXT,
                    platform_display_name TEXT,
                    profile_url TEXT,
                    connected_at TEXT,
                    last_used_at TEXT,
                    error_message TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_connections_platform ON social_connections(platform)")

            # Post history table (for analytics)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS post_history (
                    id TEXT PRIMARY KEY,
                    draft_id TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    posted_at TEXT NOT NULL,
                    post_id TEXT,
                    post_url TEXT,
                    success INTEGER DEFAULT 1,
                    error_message TEXT,
                    engagement_likes INTEGER DEFAULT 0,
                    engagement_shares INTEGER DEFAULT 0,
                    engagement_comments INTEGER DEFAULT 0,
                    last_fetched_at TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_history_platform ON post_history(platform)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_history_posted ON post_history(posted_at)")

    # ==========================================================================
    # Draft operations
    # ==========================================================================

    def save_draft(self, draft: SocialDraft) -> str:
        """Save or update a draft."""
        with self.connect() as conn:
            thread_parts_json = json.dumps(draft.thread_parts) if draft.thread_parts else None
            
            conn.execute("""
                INSERT OR REPLACE INTO social_drafts (
                    id, platform, story_id, title, content, thread_parts, url,
                    subreddit, status, created_at, updated_at, posted_at,
                    scheduled_for, post_id, post_url, error_message,
                    generation_prompt, auto_generated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                draft.id,
                draft.platform.value if isinstance(draft.platform, SocialPlatform) else draft.platform,
                draft.story_id,
                draft.title,
                draft.content,
                thread_parts_json,
                draft.url,
                draft.subreddit,
                draft.status.value if isinstance(draft.status, DraftStatus) else draft.status,
                draft.created_at.isoformat(),
                datetime.utcnow().isoformat(),
                draft.posted_at.isoformat() if draft.posted_at else None,
                draft.scheduled_for.isoformat() if draft.scheduled_for else None,
                draft.post_id,
                draft.post_url,
                draft.error_message,
                draft.generation_prompt,
                1 if draft.auto_generated else 0,
            ))
            return draft.id

    def get_draft(self, draft_id: str) -> Optional[SocialDraft]:
        """Get a draft by ID."""
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM social_drafts WHERE id = ?",
                (draft_id,)
            ).fetchone()
            if not row:
                return None
            return self._row_to_draft(row)

    def list_drafts(
        self,
        platform: Optional[SocialPlatform] = None,
        status: Optional[DraftStatus] = None,
        story_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[SocialDraft]:
        """List drafts with optional filters."""
        with self.connect() as conn:
            conditions = []
            params = []
            
            if platform:
                conditions.append("platform = ?")
                params.append(platform.value if isinstance(platform, SocialPlatform) else platform)
            
            if status:
                conditions.append("status = ?")
                params.append(status.value if isinstance(status, DraftStatus) else status)
            
            if story_id:
                conditions.append("story_id = ?")
                params.append(story_id)
            
            where_clause = " AND ".join(conditions) if conditions else "1=1"
            query = f"""
                SELECT * FROM social_drafts
                WHERE {where_clause}
                ORDER BY created_at DESC
                LIMIT ?
            """
            params.append(limit)
            
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_draft(row) for row in rows]

    def update_draft_status(
        self,
        draft_id: str,
        status: DraftStatus,
        post_id: Optional[str] = None,
        post_url: Optional[str] = None,
        error_message: Optional[str] = None,
    ):
        """Update draft status after posting attempt."""
        with self.connect() as conn:
            posted_at = datetime.utcnow().isoformat() if status == DraftStatus.POSTED else None
            conn.execute("""
                UPDATE social_drafts
                SET status = ?, post_id = ?, post_url = ?, error_message = ?,
                    posted_at = ?, updated_at = ?
                WHERE id = ?
            """, (
                status.value if isinstance(status, DraftStatus) else status,
                post_id,
                post_url,
                error_message,
                posted_at,
                datetime.utcnow().isoformat(),
                draft_id,
            ))

    def update_draft_content(
        self,
        draft_id: str,
        title: Optional[str] = None,
        content: Optional[str] = None,
        thread_parts: Optional[List[str]] = None,
    ):
        """Update draft content (for editing)."""
        with self.connect() as conn:
            updates = []
            params = []
            
            if title is not None:
                updates.append("title = ?")
                params.append(title)
            
            if content is not None:
                updates.append("content = ?")
                params.append(content)
            
            if thread_parts is not None:
                updates.append("thread_parts = ?")
                params.append(json.dumps(thread_parts))
            
            if not updates:
                return
            
            updates.append("updated_at = ?")
            params.append(datetime.utcnow().isoformat())
            updates.append("auto_generated = 0")  # Mark as edited
            
            params.append(draft_id)
            
            query = f"UPDATE social_drafts SET {', '.join(updates)} WHERE id = ?"
            conn.execute(query, params)

    def delete_draft(self, draft_id: str):
        """Delete a draft."""
        with self.connect() as conn:
            conn.execute("DELETE FROM social_drafts WHERE id = ?", (draft_id,))

    def _row_to_draft(self, row: sqlite3.Row) -> SocialDraft:
        """Convert database row to SocialDraft."""
        thread_parts = None
        if row["thread_parts"]:
            try:
                thread_parts = json.loads(row["thread_parts"])
            except json.JSONDecodeError:
                pass
        
        return SocialDraft(
            id=row["id"],
            platform=SocialPlatform(row["platform"]),
            story_id=row["story_id"],
            title=row["title"],
            content=row["content"],
            thread_parts=thread_parts,
            url=row["url"],
            subreddit=row["subreddit"],
            status=DraftStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            posted_at=datetime.fromisoformat(row["posted_at"]) if row["posted_at"] else None,
            scheduled_for=datetime.fromisoformat(row["scheduled_for"]) if row["scheduled_for"] else None,
            post_id=row["post_id"],
            post_url=row["post_url"],
            error_message=row["error_message"],
            generation_prompt=row["generation_prompt"],
            auto_generated=bool(row["auto_generated"]),
        )

    # ==========================================================================
    # Connection operations
    # ==========================================================================

    def save_connection(self, connection: SocialConnection) -> str:
        """Save or update an OAuth connection."""
        with self.connect() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO social_connections (
                    id, platform, status, access_token, refresh_token,
                    token_expires_at, platform_user_id, platform_username,
                    platform_display_name, profile_url, connected_at,
                    last_used_at, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                connection.id,
                connection.platform.value if isinstance(connection.platform, SocialPlatform) else connection.platform,
                connection.status.value if isinstance(connection.status, ConnectionStatus) else connection.status,
                connection.access_token,
                connection.refresh_token,
                connection.token_expires_at.isoformat() if connection.token_expires_at else None,
                connection.platform_user_id,
                connection.platform_username,
                connection.platform_display_name,
                connection.profile_url,
                connection.connected_at.isoformat() if connection.connected_at else None,
                connection.last_used_at.isoformat() if connection.last_used_at else None,
                connection.error_message,
            ))
            return connection.id

    def get_connection(self, platform: SocialPlatform) -> Optional[SocialConnection]:
        """Get connection for a platform."""
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM social_connections WHERE platform = ?",
                (platform.value if isinstance(platform, SocialPlatform) else platform,)
            ).fetchone()
            if not row:
                return None
            return self._row_to_connection(row)

    def list_connections(self) -> List[SocialConnection]:
        """List all connections."""
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM social_connections").fetchall()
            return [self._row_to_connection(row) for row in rows]

    def delete_connection(self, platform: SocialPlatform):
        """Delete a connection (disconnect)."""
        with self.connect() as conn:
            conn.execute(
                "DELETE FROM social_connections WHERE platform = ?",
                (platform.value if isinstance(platform, SocialPlatform) else platform,)
            )

    def update_connection_status(
        self,
        platform: SocialPlatform,
        status: ConnectionStatus,
        error_message: Optional[str] = None,
    ):
        """Update connection status."""
        with self.connect() as conn:
            conn.execute("""
                UPDATE social_connections
                SET status = ?, error_message = ?, last_used_at = ?
                WHERE platform = ?
            """, (
                status.value if isinstance(status, ConnectionStatus) else status,
                error_message,
                datetime.utcnow().isoformat(),
                platform.value if isinstance(platform, SocialPlatform) else platform,
            ))

    def _row_to_connection(self, row: sqlite3.Row) -> SocialConnection:
        """Convert database row to SocialConnection."""
        return SocialConnection(
            id=row["id"],
            platform=SocialPlatform(row["platform"]),
            status=ConnectionStatus(row["status"]),
            access_token=row["access_token"],
            refresh_token=row["refresh_token"],
            token_expires_at=datetime.fromisoformat(row["token_expires_at"]) if row["token_expires_at"] else None,
            platform_user_id=row["platform_user_id"],
            platform_username=row["platform_username"],
            platform_display_name=row["platform_display_name"],
            profile_url=row["profile_url"],
            connected_at=datetime.fromisoformat(row["connected_at"]) if row["connected_at"] else None,
            last_used_at=datetime.fromisoformat(row["last_used_at"]) if row["last_used_at"] else None,
            error_message=row["error_message"],
        )

    # ==========================================================================
    # Stats and analytics
    # ==========================================================================

    def get_stats(self) -> Dict[str, Any]:
        """Get social posting statistics."""
        with self.connect() as conn:
            # Draft counts by status
            draft_stats = {}
            for row in conn.execute("""
                SELECT status, COUNT(*) as count
                FROM social_drafts
                GROUP BY status
            """).fetchall():
                draft_stats[row["status"]] = row["count"]
            
            # Drafts by platform
            platform_stats = {}
            for row in conn.execute("""
                SELECT platform, COUNT(*) as count
                FROM social_drafts
                GROUP BY platform
            """).fetchall():
                platform_stats[row["platform"]] = row["count"]
            
            # Connection status
            connections = {}
            for row in conn.execute("""
                SELECT platform, status
                FROM social_connections
            """).fetchall():
                connections[row["platform"]] = row["status"]
            
            return {
                "drafts_by_status": draft_stats,
                "drafts_by_platform": platform_stats,
                "connections": connections,
                "total_drafts": sum(draft_stats.values()),
                "total_posted": draft_stats.get("posted", 0),
            }


# Singleton instance
_social_db: Optional[SocialDatabase] = None


def get_social_db() -> SocialDatabase:
    """Get the social database singleton."""
    global _social_db
    if _social_db is None:
        _social_db = SocialDatabase()
    return _social_db
