#
# Copyright 2022-2023 kramo
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# SPDX-License-Identifier: GPL-3.0-or-later

# pyright: reportAssignmentType=none

from gi.repository import Gio, GLib

from cartridges import shared
from cartridges.game import Game
from cartridges.store.managers.manager import Manager
from cartridges.store.managers.sgdb_manager import SgdbManager


class DisplayManager(Manager):
    """Manager in charge of adding a game to the UI"""

    run_after = (SgdbManager,)

    def main(self, game: Game, _additional_data: dict) -> None:
        if getattr(game, 'removed', False):
            return

        def update_ui() -> None:
            game.menu_button.set_menu_model(
                shared.win.lookup_action("show_hidden").get_enabled()
                and shared.win.hidden_primary_menu_button.get_menu_model()
                or shared.win.primary_menu_button.get_menu_model()
            )

            if game not in shared.win.game_store:
                shared.win.add_game_to_ui(game)

            shared.win.library_filter.changed(2)
            shared.win.hidden_library_filter.changed(2)
            shared.win.sorter.changed(1)

        GLib.idle_add(update_ui)