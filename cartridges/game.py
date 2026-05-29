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

from gi.repository import Gio, GLib, GObject, Gtk

from cartridges import shared
from cartridges.game_cover import GameCover
from cartridges.utils.run_executable import run_executable

@Gtk.Template(resource_path=shared.PREFIX + "/gtk/game.ui")
class Game(Gtk.Box):
    """Game object"""

    __gtype_name__ = "Game"

    __gsignals__ = {
        "save-ready": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "fetch-ready": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "display-ready": (GObject.SignalFlags.RUN_FIRST, None, ()),
        "update-ready": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    # Mapeamento exato dos filhos declarados no game.blp
    menu_button: Gtk.MenuButton = Gtk.Template.Child()
    menu_revealer: Gtk.Revealer = Gtk.Template.Child()
    play_revealer: Gtk.Revealer = Gtk.Template.Child()
    cover: Gtk.Picture = Gtk.Template.Child()
    spinner: Gtk.Spinner = Gtk.Template.Child()
    title: Gtk.Label = Gtk.Template.Child()
    play_button: Gtk.Button = Gtk.Template.Child()
    cover_button: Gtk.Button = Gtk.Template.Child()

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

        # Only present in legacy state
        self.steam_id = data.get("steam_id")

        self.version = data.get("version", shared.SPEC_VERSION)

        self.removed = False
        self.blacklisted = False
        self.filtered = False
        self.loading = 0

        self.game_cover: Optional[GameCover] = None

        self.base_source = self.source.split("_")[0]
        self.title.set_label(self.name)

        # Ligar os botões às respetivas ações
        self.play_button.connect("clicked", self.launch)
        self.cover_button.connect("clicked", lambda *_: shared.win.show_details_page(self))
        
        # Ligar os menús
        if self.menu_button.get_popover():
            self.menu_button.get_popover().connect("notify::visible", self.toggle_play)

        # Restaurar o controlador de eventos (para quando o utilizador passar o cursor)
        motion_controller = Gtk.EventControllerMotion.new()
        motion_controller.connect("enter", self.toggle_play)
        motion_controller.connect("leave", self.toggle_play)
        self.cover_button.add_controller(motion_controller)

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

    def launch(self, *_args: Any) -> None:
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

    def toggle_play(self, widget: Any, _pspec: Any = None) -> None:
        show = False
        
        if isinstance(widget, Gtk.EventControllerMotion):
            show = widget.contains_pointer()
        
        popover = self.menu_button.get_popover()
        if popover and popover.get_visible():
            show = True

        self.play_revealer.set_reveal_child(show)
        self.menu_revealer.set_reveal_child(show)

    def save(self) -> None:
        shared.store.save_game(self)

    def update(self) -> None:
        self.emit("update-ready")
        
        if self.game_id in shared.win.game_covers:
            if not self.game_cover:
                self.game_cover = shared.win.game_covers[self.game_id]
                self.game_cover.add_picture(self.cover)

            self.cover.set_opacity(int(not self.loading))

            if self.loading:
                self.spinner.start()
            else:
                self.spinner.stop()

        self.title.set_label(self.name)

        if hasattr(shared, 'win') and shared.win and getattr(shared.win, 'active_game', None) == self:
            shared.win.show_details_page(self)

    def set_loading(self, increment: int) -> None:
        self.loading += increment