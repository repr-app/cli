"""
Central SQLite database for repr stories.

Replaces distributed .repr/store.json files with a single ~/.repr/stories.db
for faster queries, FTS5 search, and staleness tracking.
"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .models import Story, FileChange, CodeSnippet
from .storage import generate_ulid


# Schema version for migrations
SCHEMA_VERSION = 7


def get_db_path() -> Path:
    """Get database path (lazy evaluation for testing)."""
    from .storage import REPR_HOME
    return REPR_HOME / "stories.db"


def _serialize_json_list(items: list) -> str:
    """Serialize a list to JSON string for storage."""
    return json.dumps(items) if items else "[]"


def _serialize_json(obj: list | dict | None) -> str:
    """Serialize an object to JSON string for storage, handling Pydantic models."""
    if not obj:
        return "[]" if isinstance(obj, list) or obj is None else "{}"
    # Handle list of Pydantic models
    if isinstance(obj, list) and obj and hasattr(obj[0], 'model_dump'):
        return json.dumps([item.model_dump() for item in obj])
    return json.dumps(obj)


def _deserialize_file_changes(data: str | None) -> list[FileChange]:
    """Deserialize JSON string to list of FileChange objects."""
    if not data:
        return []
    try:
        items = json.loads(data)
        return [FileChange(**item) for item in items]
    except (json.JSONDecodeError, TypeError):
        return []


def _deserialize_key_snippets(data: str | None) -> list[CodeSnippet]:
    """Deserialize JSON string to list of CodeSnippet objects."""
    if not data:
        return []
    try:
        items = json.loads(data)
        return [CodeSnippet(**item) for item in items]
    except (json.JSONDecodeError, TypeError):
        return []


def _deserialize_json_list(data: str | None) -> list:
    """Deserialize a JSON string to list."""
    if not data:
        return []
    try:
        return json.loads(data)
    except json.JSONDecodeError:
        return []


def _datetime_to_iso(dt: datetime | None) -> str | None:
    """Convert datetime to ISO string."""
    if dt is None:
        return None
    return dt.isoformat()


def _iso_to_datetime(iso_str: str | None) -> datetime | None:
    """Convert ISO string to datetime."""
    if not iso_str:
        return None
    try:
        return datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


class ReprDatabase:
    """Central SQLite database for repr stories."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or get_db_path()
        self._ensure_dir()

    def _ensure_dir(self):
        """Ensure the database directory exists."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        # Enable WAL mode for better concurrency
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
        """Initialize database schema with all tables."""
        with self.connect() as conn:
            # Projects table (registry with freshness tracking)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    path TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    last_generated TEXT,
                    last_commit_sha TEXT,
                    last_commit_at TEXT,
                    created_at TEXT NOT NULL
                )
            """)

            # Stories table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS stories (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(id),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    title TEXT NOT NULL,
                    problem TEXT DEFAULT '',
                    approach TEXT DEFAULT '',
                    tradeoffs TEXT DEFAULT '',
                    outcome TEXT DEFAULT '',
                    category TEXT DEFAULT 'feature',
                    scope TEXT DEFAULT 'internal',
                    technologies TEXT DEFAULT '[]',
                    started_at TEXT,
                    ended_at TEXT,
                    implementation_details TEXT,
                    decisions TEXT,
                    lessons TEXT,
                    public_post TEXT DEFAULT '',
                    public_show TEXT,
                    internal_post TEXT DEFAULT '',
                    internal_show TEXT,
                    internal_details TEXT DEFAULT '[]'
                )
            """)

            # Create indexes for common queries
            conn.execute("CREATE INDEX IF NOT EXISTS idx_stories_project ON stories(project_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_stories_category ON stories(category)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_stories_created_at ON stories(created_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_stories_started_at ON stories(started_at)")

            # FTS5 for full-text search
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS stories_fts USING fts5(
                    title, problem, approach,
                    content='stories', content_rowid='rowid'
                )
            """)

            # Triggers to keep FTS in sync
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS stories_ai AFTER INSERT ON stories BEGIN
                    INSERT INTO stories_fts(rowid, title, problem, approach)
                    VALUES (new.rowid, new.title, new.problem, new.approach);
                END
            """)
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS stories_ad AFTER DELETE ON stories BEGIN
                    INSERT INTO stories_fts(stories_fts, rowid, title, problem, approach)
                    VALUES ('delete', old.rowid, old.title, old.problem, old.approach);
                END
            """)
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS stories_au AFTER UPDATE ON stories BEGIN
                    INSERT INTO stories_fts(stories_fts, rowid, title, problem, approach)
                    VALUES ('delete', old.rowid, old.title, old.problem, old.approach);
                    INSERT INTO stories_fts(rowid, title, problem, approach)
                    VALUES (new.rowid, new.title, new.problem, new.approach);
                END
            """)

            # Story-file relationships
            conn.execute("""
                CREATE TABLE IF NOT EXISTS story_files (
                    story_id TEXT REFERENCES stories(id) ON DELETE CASCADE,
                    file_path TEXT,
                    PRIMARY KEY (story_id, file_path)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_story_files_path ON story_files(file_path)")

            # Story-commit relationships
            conn.execute("""
                CREATE TABLE IF NOT EXISTS story_commits (
                    story_id TEXT REFERENCES stories(id) ON DELETE CASCADE,
                    commit_sha TEXT,
                    PRIMARY KEY (story_id, commit_sha)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_story_commits_sha ON story_commits(commit_sha)")

            # Story-session relationships
            conn.execute("""
                CREATE TABLE IF NOT EXISTS story_sessions (
                    story_id TEXT REFERENCES stories(id) ON DELETE CASCADE,
                    session_id TEXT,
                    PRIMARY KEY (story_id, session_id)
                )
            """)

            # Schema version tracking
            conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY
                )
            """)
            # Don't set version here - let migrations handle it

        # Run migrations for existing databases
        self._run_migrations()

    def _ensure_columns_exist(self, conn):
        """Ensure all required columns exist (recovery for botched migrations)."""
        # All columns that should exist, with their defaults
        required_columns = [
            # v2: technologies
            ("technologies", "'[]'"),
            # v3: build log columns
            ("public_post", "''"),
            ("public_show", "NULL"),
            ("internal_post", "''"),
            ("internal_show", "NULL"),
            ("internal_details", "'[]'"),
            # v4: recall/diff columns
            ("file_changes", "'[]'"),
            ("key_snippets", "'[]'"),
            ("total_insertions", "0"),
            ("total_deletions", "0"),
            # v5: Tripartite Codex fields
            ("hook", "''"),
            ("what", "''"),
            ("value", "''"),
            ("insight", "''"),
            ("show", "NULL"),
            # v6: post_body
            ("post_body", "''"),
            # v7: diagram
            ("diagram", "NULL"),
            # v8: author_name
            ("author_name", "'unknown'"),
            # v9: author_email for Gravatar
            ("author_email", "''"),
        ]

        for col, default in required_columns:
            try:
                conn.execute(f"ALTER TABLE stories ADD COLUMN {col} TEXT DEFAULT {default}")
            except sqlite3.OperationalError:
                # Column already exists
                pass

    def _run_migrations(self):
        """Run schema migrations for existing databases."""
        with self.connect() as conn:
            # Get current schema version
            try:
                row = conn.execute("SELECT version FROM schema_version").fetchone()
                current_version = row["version"] if row else 0
            except sqlite3.OperationalError:
                current_version = 0

            # Recovery: Always try to add columns that might be missing
            # This handles databases where version was set before columns were added
            self._ensure_columns_exist(conn)

            # Migration v1 -> v2: Add technologies column
            if current_version < 2:
                try:
                    conn.execute("ALTER TABLE stories ADD COLUMN technologies TEXT DEFAULT '[]'")
                except sqlite3.OperationalError:
                    # Column already exists
                    pass

                conn.execute(
                    "INSERT OR REPLACE INTO schema_version (version) VALUES (?)",
                    (2,)
                )

            # Migration v2 -> v3: Add build log columns
            if current_version < 3:
                for col, default in [
                    ("public_post", "''"),
                    ("public_show", "NULL"),
                    ("internal_post", "''"),
                    ("internal_show", "NULL"),
                    ("internal_details", "'[]'"),
                ]:
                    try:
                        conn.execute(f"ALTER TABLE stories ADD COLUMN {col} TEXT DEFAULT {default}")
                    except sqlite3.OperationalError:
                        # Column already exists
                        pass

                conn.execute(
                    "INSERT OR REPLACE INTO schema_version (version) VALUES (?)",
                    (3,)
                )

            # Migration v3 -> v4: Add recall/diff columns
            if current_version < 4:
                for col, default in [
                    ("file_changes", "'[]'"),
                    ("key_snippets", "'[]'"),
                    ("total_insertions", "0"),
                    ("total_deletions", "0"),
                ]:
                    try:
                        conn.execute(f"ALTER TABLE stories ADD COLUMN {col} TEXT DEFAULT {default}")
                    except sqlite3.OperationalError:
                        # Column already exists
                        pass

                conn.execute(
                    "INSERT OR REPLACE INTO schema_version (version) VALUES (?)",
                    (4,)
                )

            # Migration v4 -> v5: Add Tripartite Codex fields (hook, what, value, insight, show)
            if current_version < 5:
                for col, default in [
                    ("hook", "''"),
                    ("what", "''"),
                    ("value", "''"),
                    ("insight", "''"),
                    ("show", "NULL"),
                ]:
                    try:
                        conn.execute(f"ALTER TABLE stories ADD COLUMN {col} TEXT DEFAULT {default}")
                    except sqlite3.OperationalError:
                        # Column already exists
                        pass

                conn.execute(
                    "INSERT OR REPLACE INTO schema_version (version) VALUES (?)",
                    (5,)
                )

            # Migration v5 -> v6: Add post_body field
            if current_version < 6:
                try:
                    conn.execute("ALTER TABLE stories ADD COLUMN post_body TEXT DEFAULT ''")
                except sqlite3.OperationalError:
                    # Column already exists
                    pass

                conn.execute(
                    "INSERT OR REPLACE INTO schema_version (version) VALUES (?)",
                    (6,)
                )

            # Migration v6 -> v7: Add diagram field
            if current_version < 7:
                try:
                    conn.execute("ALTER TABLE stories ADD COLUMN diagram TEXT DEFAULT NULL")
                except sqlite3.OperationalError:
                    # Column already exists
                    pass

                conn.execute(
                    "INSERT OR REPLACE INTO schema_version (version) VALUES (?)",
                    (7,)
                )

            # Ensure schema version is set for fresh databases
            conn.execute(
                "INSERT OR IGNORE INTO schema_version (version) VALUES (?)",
                (SCHEMA_VERSION,)
            )

    # =========================================================================
    # Project Management
    # =========================================================================

    def register_project(self, path: Path, name: str) -> str:
        """Register a project and return its ID."""
        project_id = generate_ulid()
        now = datetime.now(timezone.utc).isoformat()

        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO projects (id, path, name, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET name=excluded.name
                """,
                (project_id, str(path.resolve()), name, now)
            )

            # Get the actual ID (might be existing)
            row = conn.execute(
                "SELECT id FROM projects WHERE path = ?",
                (str(path.resolve()),)
            ).fetchone()
            return row["id"] if row else project_id

    def get_project_by_path(self, path: Path) -> dict | None:
        """Get project by path."""
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM projects WHERE path = ?",
                (str(path.resolve()),)
            ).fetchone()
            return dict(row) if row else None

    def get_project_by_id(self, project_id: str) -> dict | None:
        """Get project by ID."""
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM projects WHERE id = ?",
                (project_id,)
            ).fetchone()
            return dict(row) if row else None

    def list_projects(self) -> list[dict]:
        """List all registered projects."""
        with self.connect() as conn:
            rows = conn.execute("SELECT * FROM projects ORDER BY name").fetchall()
            return [dict(row) for row in rows]

    def update_freshness(
        self,
        project_id: str,
        commit_sha: str,
        commit_at: datetime
    ):
        """Update project freshness after story generation."""
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE projects
                SET last_generated = ?,
                    last_commit_sha = ?,
                    last_commit_at = ?
                WHERE id = ?
                """,
                (now, commit_sha, _datetime_to_iso(commit_at), project_id)
            )

    def check_freshness(self, path: Path) -> dict:
        """
        Check if a project's stories are up to date.

        Returns:
            {
                "needs_refresh": bool,
                "reason": str | None,
                "last_generated": str | None,
                "last_commit_sha": str | None
            }
        """
        project = self.get_project_by_path(path)
        if not project:
            return {
                "needs_refresh": True,
                "reason": "Project not registered",
                "last_generated": None,
                "last_commit_sha": None,
            }

        if not project.get("last_generated"):
            return {
                "needs_refresh": True,
                "reason": "No stories generated yet",
                "last_generated": None,
                "last_commit_sha": project.get("last_commit_sha"),
            }

        # Get latest commit from git
        try:
            import subprocess
            result = subprocess.run(
                ["git", "-C", str(path), "log", "-1", "--format=%H"],
                capture_output=True,
                text=True,
            )
            latest_sha = result.stdout.strip() if result.returncode == 0 else None
        except Exception:
            latest_sha = None

        if latest_sha and latest_sha != project.get("last_commit_sha"):
            return {
                "needs_refresh": True,
                "reason": f"New commits since last generation",
                "last_generated": project.get("last_generated"),
                "last_commit_sha": project.get("last_commit_sha"),
                "current_commit_sha": latest_sha,
            }

        return {
            "needs_refresh": False,
            "reason": None,
            "last_generated": project.get("last_generated"),
            "last_commit_sha": project.get("last_commit_sha"),
        }

    # =========================================================================
    # Story CRUD
    # =========================================================================

    def save_story(self, story: Story, project_id: str) -> str:
        """Save a story to the database."""
        now = datetime.now(timezone.utc).isoformat()

        with self.connect() as conn:
            # Insert or update story
            conn.execute(
                """
                INSERT INTO stories (
                    id, project_id, created_at, updated_at,
                    title, problem, approach, tradeoffs, outcome,
                    category, scope, technologies, started_at, ended_at,
                    implementation_details, decisions, lessons,
                    hook, what, value, insight, show, diagram, post_body,
                    public_post, public_show, internal_post, internal_show, internal_details,
                    file_changes, key_snippets, total_insertions, total_deletions,
                    author_name, author_email
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    updated_at=excluded.updated_at,
                    title=excluded.title,
                    problem=excluded.problem,
                    approach=excluded.approach,
                    tradeoffs=excluded.tradeoffs,
                    outcome=excluded.outcome,
                    category=excluded.category,
                    scope=excluded.scope,
                    technologies=excluded.technologies,
                    started_at=excluded.started_at,
                    ended_at=excluded.ended_at,
                    implementation_details=excluded.implementation_details,
                    decisions=excluded.decisions,
                    lessons=excluded.lessons,
                    hook=excluded.hook,
                    what=excluded.what,
                    value=excluded.value,
                    insight=excluded.insight,
                    show=excluded.show,
                    diagram=excluded.diagram,
                    post_body=excluded.post_body,
                    public_post=excluded.public_post,
                    public_show=excluded.public_show,
                    internal_post=excluded.internal_post,
                    internal_show=excluded.internal_show,
                    internal_details=excluded.internal_details,
                    file_changes=excluded.file_changes,
                    key_snippets=excluded.key_snippets,
                    total_insertions=excluded.total_insertions,
                    total_deletions=excluded.total_deletions,
                    author_name=excluded.author_name,
                    author_email=excluded.author_email
                """,
                (
                    story.id,
                    project_id,
                    _datetime_to_iso(story.created_at),
                    now,
                    story.title,
                    story.problem,
                    story.approach,
                    story.tradeoffs,
                    story.outcome,
                    story.category,
                    story.scope,
                    _serialize_json_list(story.technologies),
                    _datetime_to_iso(story.started_at),
                    _datetime_to_iso(story.ended_at),
                    _serialize_json_list(story.implementation_details),
                    _serialize_json_list(story.decisions),
                    _serialize_json_list(story.lessons),
                    story.hook,
                    story.what,
                    story.value,
                    story.insight,
                    story.show,
                    story.diagram,
                    story.post_body,
                    story.public_post,
                    story.public_show,
                    story.internal_post,
                    story.internal_show,
                    _serialize_json_list(story.internal_details),
                    _serialize_json(story.file_changes),
                    _serialize_json(story.key_snippets),
                    story.total_insertions,
                    story.total_deletions,
                    story.author_name,
                    story.author_email,
                )
            )

            # Update file relationships
            conn.execute("DELETE FROM story_files WHERE story_id = ?", (story.id,))
            if story.files:
                conn.executemany(
                    "INSERT INTO story_files (story_id, file_path) VALUES (?, ?)",
                    [(story.id, f) for f in story.files]
                )

            # Update commit relationships
            conn.execute("DELETE FROM story_commits WHERE story_id = ?", (story.id,))
            if story.commit_shas:
                conn.executemany(
                    "INSERT INTO story_commits (story_id, commit_sha) VALUES (?, ?)",
                    [(story.id, sha) for sha in story.commit_shas]
                )

            # Update session relationships
            conn.execute("DELETE FROM story_sessions WHERE story_id = ?", (story.id,))
            if story.session_ids:
                conn.executemany(
                    "INSERT INTO story_sessions (story_id, session_id) VALUES (?, ?)",
                    [(story.id, sid) for sid in story.session_ids]
                )

        return story.id

    def _row_to_story(self, row: sqlite3.Row, conn: sqlite3.Connection) -> Story:
        """Convert a database row to a Story object."""
        story_id = row["id"]

        # Get related files
        files = [
            r["file_path"] for r in
            conn.execute("SELECT file_path FROM story_files WHERE story_id = ?", (story_id,))
        ]

        # Get related commits
        commit_shas = [
            r["commit_sha"] for r in
            conn.execute("SELECT commit_sha FROM story_commits WHERE story_id = ?", (story_id,))
        ]

        # Get related sessions
        session_ids = [
            r["session_id"] for r in
            conn.execute("SELECT session_id FROM story_sessions WHERE story_id = ?", (story_id,))
        ]

        # Helper to safely get column
        def _get(col: str, default=""):
            return row[col] if col in row.keys() else default

        return Story(
            id=story_id,
            project_id=row["project_id"],
            created_at=_iso_to_datetime(row["created_at"]) or datetime.now(timezone.utc),
            updated_at=_iso_to_datetime(row["updated_at"]) or datetime.now(timezone.utc),
            title=row["title"],
            problem=row["problem"] or "",
            approach=row["approach"] or "",
            tradeoffs=row["tradeoffs"] or "",
            outcome=row["outcome"] or "",
            category=row["category"] or "feature",
            scope=row["scope"] or "internal",
            technologies=_deserialize_json_list(row["technologies"]) if "technologies" in row.keys() else [],
            started_at=_iso_to_datetime(row["started_at"]),
            ended_at=_iso_to_datetime(row["ended_at"]),
            implementation_details=_deserialize_json_list(row["implementation_details"]),
            decisions=_deserialize_json_list(row["decisions"]),
            lessons=_deserialize_json_list(row["lessons"]),
            files=files,
            commit_shas=commit_shas,
            session_ids=session_ids,
            # Tripartite Codex fields
            hook=_get("hook", ""),
            what=_get("what", ""),
            value=_get("value", ""),
            insight=_get("insight", ""),
            show=_get("show", None),
            diagram=_get("diagram", None),
            post_body=_get("post_body", ""),
            # Legacy fields
            public_post=_get("public_post", ""),
            public_show=_get("public_show", None),
            internal_post=_get("internal_post", ""),
            internal_show=_get("internal_show", None),
            internal_details=_deserialize_json_list(_get("internal_details", "[]")),
            # Recall data
            file_changes=_deserialize_file_changes(_get("file_changes", "[]")),
            key_snippets=_deserialize_key_snippets(_get("key_snippets", "[]")),
            total_insertions=int(_get("total_insertions", 0) or 0),
            total_deletions=int(_get("total_deletions", 0) or 0),
            author_name=_get("author_name", "unknown"),
            author_email=_get("author_email", ""),
        )

    def get_story(self, story_id: str) -> Story | None:
        """Get a story by ID."""
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM stories WHERE id = ?",
                (story_id,)
            ).fetchone()

            if not row:
                return None

            return self._row_to_story(row, conn)

    def delete_story(self, story_id: str) -> bool:
        """Delete a story by ID."""
        with self.connect() as conn:
            cursor = conn.execute("DELETE FROM stories WHERE id = ?", (story_id,))
            return cursor.rowcount > 0

    def list_stories(
        self,
        project_id: str | None = None,
        category: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[Story]:
        """List stories with optional filters."""
        conditions = []
        params = []

        if project_id:
            conditions.append("project_id = ?")
            params.append(project_id)

        if category:
            conditions.append("category = ?")
            params.append(category)

        if since:
            conditions.append("(started_at >= ? OR created_at >= ?)")
            iso_since = _datetime_to_iso(since)
            params.extend([iso_since, iso_since])

        where_clause = " AND ".join(conditions) if conditions else "1=1"

        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM stories
                WHERE {where_clause}
                ORDER BY COALESCE(started_at, created_at) DESC
                LIMIT ?
                """,
                params + [limit]
            ).fetchall()

            return [self._row_to_story(row, conn) for row in rows]

    def search_stories(
        self,
        query: str,
        files: list[str] | None = None,
        limit: int = 20,
    ) -> list[Story]:
        """
        Search stories using FTS5.

        Args:
            query: Search query (keywords)
            files: Optional file paths to filter by
            limit: Maximum results

        Returns:
            List of matching stories, scored by relevance
        """
        with self.connect() as conn:
            # FTS search
            if files:
                # Search with file filter using JOIN
                rows = conn.execute(
                    """
                    SELECT DISTINCT s.*, bm25(stories_fts) as score
                    FROM stories s
                    JOIN stories_fts fts ON s.rowid = fts.rowid
                    JOIN story_files sf ON s.id = sf.story_id
                    WHERE stories_fts MATCH ?
                      AND sf.file_path IN ({})
                    ORDER BY score
                    LIMIT ?
                    """.format(",".join("?" * len(files))),
                    [query] + files + [limit]
                ).fetchall()
            else:
                # Pure FTS search
                rows = conn.execute(
                    """
                    SELECT s.*, bm25(stories_fts) as score
                    FROM stories s
                    JOIN stories_fts fts ON s.rowid = fts.rowid
                    WHERE stories_fts MATCH ?
                    ORDER BY score
                    LIMIT ?
                    """,
                    (query, limit)
                ).fetchall()

            return [self._row_to_story(row, conn) for row in rows]

    def get_stories_by_file(self, file_path: str, limit: int = 20) -> list[Story]:
        """Get stories that touch a specific file."""
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT s.* FROM stories s
                JOIN story_files sf ON s.id = sf.story_id
                WHERE sf.file_path = ?
                ORDER BY s.created_at DESC
                LIMIT ?
                """,
                (file_path, limit)
            ).fetchall()

            return [self._row_to_story(row, conn) for row in rows]

    def get_stories_by_commit(self, commit_sha: str) -> list[Story]:
        """Get stories that include a specific commit."""
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT s.* FROM stories s
                JOIN story_commits sc ON s.id = sc.story_id
                WHERE sc.commit_sha = ? OR sc.commit_sha LIKE ?
                ORDER BY s.created_at DESC
                """,
                (commit_sha, commit_sha + "%")
            ).fetchall()

            return [self._row_to_story(row, conn) for row in rows]

    def get_processed_commits(self, project_id: str) -> set[str]:
        """Get all commit SHAs that are already part of stories for a project."""
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT sc.commit_sha
                FROM story_commits sc
                JOIN stories s ON sc.story_id = s.id
                WHERE s.project_id = ?
                """,
                (project_id,)
            ).fetchall()
            return {row["commit_sha"] for row in rows}

    # =========================================================================
    # Migration
    # =========================================================================

    def import_from_store(self, store: "ReprStore", project_path: Path) -> int:
        """
        Import stories from a ReprStore (JSON) into SQLite.

        Args:
            store: ReprStore loaded from .repr/store.json
            project_path: Path to the project

        Returns:
            Number of stories imported
        """
        # Register project
        project_id = self.register_project(project_path, project_path.name)

        imported = 0
        for story in store.stories:
            self.save_story(story, project_id)
            imported += 1

        return imported

    def get_stats(self) -> dict:
        """Get database statistics."""
        with self.connect() as conn:
            story_count = conn.execute("SELECT COUNT(*) FROM stories").fetchone()[0]
            project_count = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
            file_count = conn.execute("SELECT COUNT(DISTINCT file_path) FROM story_files").fetchone()[0]
            commit_count = conn.execute("SELECT COUNT(DISTINCT commit_sha) FROM story_commits").fetchone()[0]

            # Category breakdown
            categories = {}
            for row in conn.execute("SELECT category, COUNT(*) as cnt FROM stories GROUP BY category"):
                categories[row["category"]] = row["cnt"]

            return {
                "story_count": story_count,
                "project_count": project_count,
                "unique_files": file_count,
                "unique_commits": commit_count,
                "categories": categories,
                "db_path": str(self.db_path),
                "db_size_bytes": self.db_path.stat().st_size if self.db_path.exists() else 0,
            }


# Singleton instance
_db_instance: ReprDatabase | None = None


def get_db() -> ReprDatabase:
    """Get the singleton database instance."""
    global _db_instance
    if _db_instance is None:
        _db_instance = ReprDatabase()
        _db_instance.init_schema()
    return _db_instance


def reset_db_instance():
    """Reset the singleton (for testing)."""
    global _db_instance
    _db_instance = None
