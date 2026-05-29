#
# Copyright 2023 kramo
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# SPDX-License-Identifier: GPL-3.0-or-later

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
        if additional_data.get("skip_save"):
            return

        with get_conn() as conn:
            conn.execute('''
                INSERT OR REPLACE INTO games 
                (game_id, added, executable, source, hidden, last_played, name, developer, publisher, release_year, removed, blacklisted, version)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                game.game_id, game.added, game.executable, game.source,
                game.hidden, game.last_played, game.name, getattr(game, 'developer', None),
                getattr(game, 'publisher', None), getattr(game, 'release_year', None),
                game.removed, game.blacklisted, getattr(game, 'version', shared.SPEC_VERSION)
            ))
            conn.commit()
