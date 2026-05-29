# steamgriddb.py
#
# Copyright 2022-2023 kramo
# Copyright 2023 Geoffrey Coulaud
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# SPDX-License-Identifier: GPL-3.0-or-later

import logging
import re
from pathlib import Path
from typing import Any

import requests
from gi.repository import Gio
from requests.exceptions import HTTPError

from cartridges import shared
from cartridges.game import Game
from cartridges.utils.save_cover import convert_cover, save_cover


class SgdbError(Exception):
    pass


class SgdbAuthError(SgdbError):
    pass


class SgdbGameNotFound(SgdbError):
    pass


class SgdbBadRequest(SgdbError):
    pass


class SgdbNoImageFound(SgdbError):
    pass


class SgdbHelper:
    """Helper class to make queries to SteamGridDB"""

    base_url = "https://www.steamgriddb.com/api/v2/"

    @property
    def auth_headers(self) -> dict[str, str]:
        key = shared.schema.get_string("sgdb-key")
        headers = {"Authorization": f"Bearer {key}"}
        return headers

    def sanitize_name(self, name: str) -> str:
        clean = re.sub(r'[™®©]', '', name)
        clean = re.sub(r'\(.*?\)|\[.*?\]', '', clean)
        clean = re.sub(r'(?i)\b(?:definitive|goty|enhanced|special|director\'s cut)\s+edition\b', '', clean)
        return clean.strip()

    def get_game_ids(self, game: Game) -> list[int]:
        clean_name = self.sanitize_name(game.name)
        uri = f"{self.base_url}search/autocomplete/{clean_name}"
        res = requests.get(uri, headers=self.auth_headers, timeout=5)
        match res.status_code:
            case 200:
                data = res.json()["data"]
                if len(data) == 0:
                    raise SgdbGameNotFound(res.status_code)
                return [item["id"] for item in data[:3]]
            case 401:
                raise SgdbAuthError(res.json()["errors"][0])
            case 404:
                raise SgdbGameNotFound(res.status_code)
            case _:
                res.raise_for_status()

    def get_image_uri(self, game_id: int, animated: bool = False) -> str:
        dimensions = "600x900,342x482,660x930"
        uri = f"{self.base_url}grids/game/{game_id}?dimensions={dimensions}"
        if animated:
            uri += "&types=animated"
        res = requests.get(uri, headers=self.auth_headers, timeout=5)
        match res.status_code:
            case 200:
                data = res.json()["data"]
                if len(data) == 0:
                    raise SgdbNoImageFound()
                return data[0]["url"]
            case 401:
                raise SgdbAuthError(res.json()["errors"][0])
            case 404:
                raise SgdbGameNotFound(res.status_code)
            case _:
                res.raise_for_status()

    def conditionaly_update_cover(self, game: Game) -> None:
        use_sgdb = shared.schema.get_boolean("sgdb")
        if not use_sgdb or game.blacklisted:
            return

        image_trunk = shared.covers_dir / game.game_id
        still = image_trunk.with_suffix(".tiff")
        animated = image_trunk.with_suffix(".gif")
        prefer_sgdb = shared.schema.get_boolean("sgdb-prefer")

        if not prefer_sgdb and (still.is_file() or animated.is_file()):
            return

        try:
            sgdb_ids = self.get_game_ids(game)
        except (HTTPError, SgdbGameNotFound) as error:
            logging.warning(
                "%s while getting SGDB ID for %s. Skipping cover download.", type(error).__name__, game.name
            )
            # Retorna silenciosamente em vez de estoirar o pipeline
            return
        except SgdbError as error:
            logging.warning(
                "%s while getting SGDB ID for %s", type(error).__name__, game.name
            )
            raise error

        image_uri_kwargs_sets = [{"animated": False}]
        if shared.schema.get_boolean("sgdb-animated"):
            image_uri_kwargs_sets.insert(0, {"animated": True})

        for sgdb_id in sgdb_ids:
            for uri_kwargs in image_uri_kwargs_sets:
                try:
                    uri = self.get_image_uri(sgdb_id, **uri_kwargs)
                    response = requests.get(uri, timeout=5)
                    tmp_file = Gio.File.new_tmp()[0]
                    tmp_file_path = tmp_file.get_path()
                    Path(tmp_file_path).write_bytes(response.content)
                    
                    save_cover(game.game_id, convert_cover(tmp_file_path))
                    return
                except SgdbAuthError as error:
                    raise error
                except Exception as error: 
                    logging.warning(
                        "%s while processing image for %s kwargs=%s id=%s. Skipping to next...",
                        type(error).__name__,
                        game.name,
                        str(uri_kwargs),
                        sgdb_id
                    )
                    continue

        logging.warning('No matching/valid image found for game "%s"', game.name)
        # Em vez de levantar exceção por não achar imagem, retorna limpo.
        return
