import sqlite3
from pathlib import Path
from typing import List, Optional, Dict, Any


class MetadataStore:
    def __init__(self, path: Path):
        self.path = path
        self.db_path = path / "metadata.db"
        self._init_db()
    
    def _init_db(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS chunks (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    start_line INTEGER NOT NULL,
                    end_line INTEGER NOT NULL,
                    chunk_type TEXT,
                    subsys TEXT,
                    code_snippet TEXT
                );

                CREATE TABLE IF NOT EXISTS symbols (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    line INTEGER NOT NULL,
                    symbol_type TEXT,
                    UNIQUE(name, file_path, line)
                );

                CREATE TABLE IF NOT EXISTS git_commits (
                    hash TEXT PRIMARY KEY,
                    title TEXT,
                    author TEXT,
                    date TEXT,
                    message TEXT,
                    diff TEXT,
                    vector_id TEXT,
                    type_tags TEXT,
                    labels TEXT
                );

                CREATE TABLE IF NOT EXISTS callgraph (
                    caller TEXT NOT NULL,
                    callee TEXT NOT NULL,
                    file_path TEXT,
                    line INTEGER,
                    PRIMARY KEY (caller, callee, file_path, line)
                );

                CREATE TABLE IF NOT EXISTS index_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_chunks_subsys ON chunks(subsys);
                CREATE INDEX IF NOT EXISTS idx_chunks_file ON chunks(file_path);
                CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
                CREATE INDEX IF NOT EXISTS idx_commits_author ON git_commits(author);
                CREATE INDEX IF NOT EXISTS idx_callgraph_caller ON callgraph(caller);
                CREATE INDEX IF NOT EXISTS idx_callgraph_callee ON callgraph(callee);
            """)
            self._migrate_git_commits(conn)

    def _migrate_git_commits(self, conn: sqlite3.Connection):
        columns = [row[1] for row in conn.execute("PRAGMA table_info(git_commits)")]
        if "vector_id" not in columns:
            conn.execute("ALTER TABLE git_commits ADD COLUMN vector_id TEXT")
        if "type_tags" not in columns:
            conn.execute("ALTER TABLE git_commits ADD COLUMN type_tags TEXT")
        if "labels" not in columns:
            conn.execute("ALTER TABLE git_commits ADD COLUMN labels TEXT")
    
    def save_chunks(self, chunks: List[Dict[str, Any]]):
        with sqlite3.connect(self.db_path) as conn:
            conn.executemany(
                """INSERT OR REPLACE INTO chunks 
                   (id, name, file_path, start_line, end_line, chunk_type, subsys, code_snippet)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                [(c["id"], c["name"], c["file_path"], c["start_line"], 
                  c["end_line"], c.get("chunk_type"), c.get("subsys"), 
                  c.get("code_snippet", "")) for c in chunks]
            )
    
    def get_chunks(self, ids: List[str]) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            placeholders = ",".join("?" * len(ids))
            rows = conn.execute(
                f"SELECT * FROM chunks WHERE id IN ({placeholders})", ids
            ).fetchall()
            return [dict(row) for row in rows]
    
    def search_chunks_by_subsys(self, subsys: str, limit: int = 100) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if subsys:
                rows = conn.execute(
                    "SELECT * FROM chunks WHERE subsys = ? LIMIT ?",
                    (subsys, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM chunks LIMIT ?",
                    (limit,)
                ).fetchall()
            return [dict(row) for row in rows]
    
    def save_metadata(self, metadata: Dict[str, Any]):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS index_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            for key, value in metadata.items():
                conn.execute(
                    "INSERT OR REPLACE INTO index_metadata (key, value) VALUES (?, ?)",
                    (key, str(value))
                )
    
    def get_metadata(self, key: str) -> Optional[str]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT value FROM index_metadata WHERE key = ?", (key,)
            ).fetchone()
            return row[0] if row else None
    
    def save_symbols(self, symbols: List[Dict[str, Any]]):
        with sqlite3.connect(self.db_path) as conn:
            conn.executemany(
                """INSERT OR REPLACE INTO symbols 
                   (name, file_path, line, symbol_type)
                   VALUES (?, ?, ?, ?)""",
                [(s["name"], s["file_path"], s["line"], s.get("symbol_type"))
                 for s in symbols]
            )
    
    def search_symbols(self, name: str) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM symbols WHERE name = ?",
                (name,)
            ).fetchall()
            return [dict(row) for row in rows]
    
    def search_symbols_by_prefix(self, prefix: str, limit: int = 100) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM symbols WHERE name LIKE ? LIMIT ?",
                (f"{prefix}%", limit)
            ).fetchall()
            return [dict(row) for row in rows]

    def save_git_commits(self, commits: List[Dict[str, Any]]):
        with sqlite3.connect(self.db_path) as conn:
            conn.executemany(
                """INSERT OR REPLACE INTO git_commits
                   (hash, title, author, date, message, diff, vector_id, type_tags, labels)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [(c["hash"], c.get("title", ""), c.get("author", ""),
                  c.get("date", ""), c.get("message", ""), c.get("diff", ""),
                  c.get("vector_id", ""), c.get("type_tags", ""), c.get("labels", ""))
                 for c in commits]
            )

    def search_git_commits(self, query: str = None, author: str = None, limit: int = 100) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if query:
                rows = conn.execute(
                    "SELECT * FROM git_commits WHERE title LIKE ? OR message LIKE ? LIMIT ?",
                    (f"%{query}%", f"%{query}%", limit)
                ).fetchall()
            elif author:
                rows = conn.execute(
                    "SELECT * FROM git_commits WHERE author = ? LIMIT ?",
                    (author, limit)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM git_commits LIMIT ?",
                    (limit,)
                ).fetchall()
            return [dict(row) for row in rows]

    def search_git_commits_by_type(self, type_tag: str, limit: int = 100) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM git_commits WHERE type_tags LIKE ? LIMIT ?",
                (f"%{type_tag}%", limit)
            ).fetchall()
            return [dict(row) for row in rows]

    def get_git_commits_by_hashes(self, hashes: List[str]) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            placeholders = ",".join("?" * len(hashes))
            rows = conn.execute(
                f"SELECT * FROM git_commits WHERE hash IN ({placeholders})", hashes
            ).fetchall()
            return [dict(row) for row in rows]
