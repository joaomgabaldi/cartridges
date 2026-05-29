#
# Copyright 2023 Geoffrey Coulaud
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# SPDX-License-Identifier: GPL-3.0-or-later

import re
import requests
from requests.exceptions import ConnectionError as RequestConnectionError
from requests.exceptions import HTTPError, SSLError

from cartridges import shared
from cartridges.game import Game
from cartridges.store.managers.async_manager import AsyncManager


class SteamAPIManager(AsyncManager):
    """Manager in charge of getting game information from Steam"""

    run_after = ()
    retryable_on = (HTTPError, SSLError, RequestConnectionError)

    def main(self, game: Game, _additional_data: dict) -> None:
        if game.blacklisted:
            return

        app_id = None
        if game.source == "steam":
            app_id = game.game_id.split("_")[1]
        elif hasattr(game, "steam_id") and game.steam_id:
            app_id = game.steam_id

        if app_id:
            uri = f"https://store.steampowered.com/api/appdetails?appids={app_id}&l=en"
            res = requests.get(uri, timeout=5)
            res.raise_for_status()

            json_data = res.json()
            if not json_data or not json_data.get(str(app_id)) or not json_data[str(app_id)].get("success"):
                return
            
            data = json_data[str(app_id)]["data"]

            if not getattr(game, "developer", None) and data.get("developers"):
                game.developer = data["developers"][0]
                
            if not getattr(game, "publisher", None) and data.get("publishers"):
                game.publisher = data["publishers"][0]
                
            if not getattr(game, "release_year", None):
                date_str = data.get("release_date", {}).get("date", "")
                if date_str:
                    match = re.search(r'\d{4}', date_str)
                    if match:
                        game.release_year = match.group()

            game.save()
            game.update()