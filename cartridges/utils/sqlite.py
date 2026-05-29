# sqlite.py
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
    """Retorna uma conexão ativa com o banco de dados principal."""
    shared.games_dir.mkdir(parents=True, exist_ok=True)
    db_path = shared.games_dir / "cartridges.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # Permite acessar colunas como dicionário
    return conn

def init_db() -> sqlite3.Connection:
    """Cria a tabela de jogos caso não exista."""
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
            removed BOOLEAN,
            blacklisted BOOLEAN,
            version INTEGER
        )
    ''')
    conn.commit()
    return conn

def migrate_legacy_json(conn: sqlite3.Connection) -> None:
    """Migra silenciosamente os .json antigos para o SQLite."""
    if not shared.games_dir.exists():
        return
        
    for file in shared.games_dir.glob("*.json"):
        try:
            with open(file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Executáveis podiam ser listas nos JSONs mais velhos
            executable = data.get("executable", "")
            if isinstance(executable, list):
                executable = shlex.join(executable)

            conn.execute('''
                INSERT OR REPLACE INTO games 
                (game_id, added, executable, source, hidden, last_played, name, developer, removed, blacklisted, version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                data.get("game_id"), data.get("added"), executable, data.get("source"),
                data.get("hidden", False), data.get("last_played", 0), data.get("name"),
                data.get("developer"), data.get("removed", False), data.get("blacklisted", False),
                data.get("version", shared.SPEC_VERSION)
            ))
            conn.commit()
            file.unlink() # Deleta o JSON após migrar com sucesso
        except Exception:
            pass
