import sqlite3
import json
import shlex
from glob import escape
from pathlib import Path
from shutil import copyfile

from gi.repository import GLib

from cartridges import shared

def copy_db(original_path: Path) -> Path:
    """
    Copy a sqlite database to a cache dir and return its new path.
    The caller in in charge of deleting the returned path's parent dir.
    """
    tmp = Path(GLib.Dir.make_tmp())
    for file in original_path.parent.glob(f"{escape(original_path.name)}*"):
        copy = tmp / file.name
        copyfile(str(file), str(copy))
    return tmp / original_path.name

def get_conn() -> sqlite3.Connection:
    shared.games_dir.mkdir(parents=True, exist_ok=True)
    db_path = shared.games_dir / "cartridges.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def init_db() -> sqlite3.Connection:
    conn = get_conn()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS games (
            game_id TEXT PRIMARY KEY,
            added INTEGER,
            executable TEXT,
            source TEXT,
            hidden BOOLEAN,
            last_played INTEGER,
            name TEXT,
            developer TEXT,
            publisher TEXT,
            release_year TEXT,
            removed BOOLEAN,
            blacklisted BOOLEAN,
            version INTEGER
        )
    ''')
    
    try:
        conn.execute('ALTER TABLE games ADD COLUMN publisher TEXT')
        conn.execute('ALTER TABLE games ADD COLUMN release_year TEXT')
    except sqlite3.OperationalError:
        pass

    conn.commit()
    return conn

def migrate_legacy_json(conn: sqlite3.Connection) -> None:
    if not shared.games_dir.exists():
        return
        
    for file in shared.games_dir.glob("*.json"):
        try:
            with open(file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            executable = data.get("executable", "")
            if isinstance(executable, list):
                executable = shlex.join(executable)

            conn.execute('''
                INSERT OR REPLACE INTO games 
                (game_id, added, executable, source, hidden, last_played, name, developer, publisher, release_year, removed, blacklisted, version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                data.get("game_id"), data.get("added"), executable, data.get("source"),
                data.get("hidden", False), data.get("last_played", 0), data.get("name"),
                data.get("developer"), data.get("publisher"), data.get("release_year"),
                data.get("removed", False), data.get("blacklisted", False),
                data.get("version", shared.SPEC_VERSION)
            ))
            conn.commit()
            file.unlink()
        except Exception:
            pass
