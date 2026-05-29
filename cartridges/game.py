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

from pathlib import Path
from sys import platform
from typing import Any, Optional

from gi.repository import Gio, GLib, GObject

from cartridges import shared
from cartridges.game_cover import GameCover
from cartridges.utils.run_executable import run_executable


class Game(GObject.Object):
    """Game object"""

    __gsignals__ = {
        "save-ready": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "fetch-ready": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "display-ready": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "update-ready": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, data: dict):
        super().__init__()
        self.game_id = data.get("game_id", "")
        self.name = data.get("name", "")
        self.developer = data.get("developer")
        self.publisher = data.get("publisher")
        self.release_year = data.get("release_year")
        self.executable = data.get("executable", "")
        self.added = data.get("added", 0)
        self.source = data.get("source", "")
        self.hidden = data.get("hidden", False)
        self.last_played = data.get("last_played", 0)
        self.version = data.get("version", shared.SPEC_VERSION)

        # Only present in legacy state
        self.steam_id = data.get("steam_id")

        self.removed = False
        self.blacklisted = False
        self.filtered = False
        self.loading = 0

        self.game_cover: Optional[GameCover] = None
        self.base_source = self.source.split("_")[0]

    def get_cover_path(self) -> Path:
        base_path = shared.covers_dir / self.game_id

        if base_path.with_suffix(".gif").is_file():
            return base_path.with_suffix(".gif")

        return base_path.with_suffix(".tiff")

    def toggle_hidden(self, save: bool = True) -> None:
        self.hidden = not self.hidden
        self.update()

        if not save:
            return

        shared.win.library_filter.changed(2)
        shared.win.hidden_library_filter.changed(2)

        shared.win.create_source_rows()

        self.save()

        # Translators: {} is the game's title
        string = _("{} hidden") if self.hidden else _("{} unhidden")

        shared.win.get_application().send_notification(
            "hide", Gio.Notification.new(string.format(self.name))
        )

        try:
            shared.win.toasts[(self, "hide")].dismiss()
            shared.win.toasts.pop((self, "hide"))
        except KeyError:
            pass

        # Translators: {} is the game's title
        toast = shared.win.toast_overlay.add_toast(
            string.format(self.name),
            "win.undo",
            _("Undo"),
        )
        shared.win.toasts[(self, "hide")] = toast

        # Sleep for 6 seconds before withdrawing the notification
        GLib.Thread.new(
            None,
            lambda: (
                GLib.usleep(6000000),
                shared.win.get_application().withdraw_notification("hide"),
            ),
        )

    def remove_game(self) -> None:
        if shared.win.navigation_view.get_visible_page() == shared.win.details_page:
            shared.win.navigation_view.pop()

        self.removed = True
        self.update()

        shared.win.create_source_rows()

        # Delete files
        shared.store.cleanup_game(self)

        # Remove from runtime cache
        shared.win.remove_game_from_ui(self)

        shared.win.get_application().send_notification(
            "remove",
            # Translators: {} is the game's title
            Gio.Notification.new(_("{} removed").format(self.name)),
        )

        try:
            shared.win.toasts[(self, "remove")].dismiss()
            shared.win.toasts.pop((self, "remove"))
        except KeyError:
            pass

        # Display an undo toast if the game is manually added
        if self.source == "imported":
            # Translators: {} is the game's title
            toast = shared.win.toast_overlay.add_toast(
                _("{} removed").format(self.name),
                "win.undo",
                _("Undo"),
            )
            shared.win.toasts[(self, "remove")] = toast

        # Sleep for 6 seconds before withdrawing the notification
        GLib.Thread.new(
            None,
            lambda: (
                GLib.usleep(6000000),
                shared.win.get_application().withdraw_notification("remove"),
            ),
        )

    def launch(self) -> None:
        shared.win.get_application().send_notification(
            "launch",
            # Translators: {} is the game's title
            Gio.Notification.new(_("{} launched").format(self.name)),
        )

        GLib.Thread.new(None, lambda: run_executable(self.executable))

        # Sleep for 6 seconds before withdrawing the notification
        GLib.Thread.new(
            None,
            lambda: (
                GLib.usleep(6000000),
                shared.win.get_application().withdraw_notification("launch"),
            ),
        )

    def toggle_play(self, _widget: Any, _pspec: Any, action: Any) -> None:
        pass

    def save(self) -> None:
        shared.store.save_game(self)

    def update(self) -> None:
        self.emit("update-ready")

    def set_loading(self, increment: int) -> None:
        self.loading += increment