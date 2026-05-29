# file_manager.py
from cartridges import shared
from cartridges.game import Game
from cartridges.store.managers.async_manager import AsyncManager
from cartridges.store.managers.steam_api_manager import SteamAPIManager
from cartridges.utils.sqlite import get_conn

class FileManager(AsyncManager):
    """Manager in charge of saving a game to the database"""

    run_after = (SteamAPIManager,)
    signals = {"save-ready"}

    def main(self, game: Game, additional_data: dict) -> None:
        if additional_data.get("skip_save"):  # Skip saving when loading games from disk
            return

        with get_conn() as conn:
            conn.execute('''
                INSERT OR REPLACE INTO games 
                (game_id, added, executable, source, hidden, last_played, name, developer, removed, blacklisted, version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                game.game_id, game.added, game.executable, game.source,
                game.hidden, game.last_played, game.name, game.developer,
                game.removed, game.blacklisted, getattr(game, 'version', shared.SPEC_VERSION)
            ))
