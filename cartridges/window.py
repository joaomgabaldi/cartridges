# window.py
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

import shlex
import shutil
import threading
from pathlib import Path
from sys import platform
from time import time
from typing import Any, Optional

from gi.repository import Adw, Gio, GLib, Gtk, Pango

from cartridges import shared
from cartridges.game import Game
from cartridges.game_cover import GameCover
from cartridges.utils.relative_date import relative_date


@Gtk.Template(resource_path=shared.PREFIX + "/gtk/window.ui")
class CartridgesWindow(Adw.ApplicationWindow):
    __gtype_name__ = "CartridgesWindow"

    overlay_split_view: Adw.OverlaySplitView = Gtk.Template.Child()
    navigation_view: Adw.NavigationView = Gtk.Template.Child()
    sidebar_navigation_page: Adw.NavigationPage = Gtk.Template.Child()
    sidebar: Gtk.ListBox = Gtk.Template.Child()
    all_games_row_box: Gtk.Box = Gtk.Template.Child()
    all_games_no_label: Gtk.Label = Gtk.Template.Child()
    added_row_box: Gtk.Box = Gtk.Template.Child()
    added_games_no_label: Gtk.Label = Gtk.Template.Child()
    toast_overlay: Adw.ToastOverlay = Gtk.Template.Child()
    primary_menu_button: Gtk.MenuButton = Gtk.Template.Child()
    show_sidebar_button: Gtk.Button = Gtk.Template.Child()
    details_view: Gtk.Overlay = Gtk.Template.Child()
    library_page: Adw.NavigationPage = Gtk.Template.Child()
    library_view: Adw.ToolbarView = Gtk.Template.Child()
    library: Gtk.GridView = Gtk.Template.Child()
    scrolledwindow: Gtk.ScrolledWindow = Gtk.Template.Child()
    library_overlay: Gtk.Overlay = Gtk.Template.Child()
    notice_empty: Adw.StatusPage = Gtk.Template.Child()
    notice_no_results: Adw.StatusPage = Gtk.Template.Child()
    search_bar: Gtk.SearchBar = Gtk.Template.Child()
    search_entry: Gtk.SearchEntry = Gtk.Template.Child()
    search_button: Gtk.ToggleButton = Gtk.Template.Child()

    details_page: Adw.NavigationPage = Gtk.Template.Child()
    details_view_toolbar_view: Adw.ToolbarView = Gtk.Template.Child()
    details_view_cover: Gtk.Picture = Gtk.Template.Child()
    details_view_spinner: Adw.Spinner = Gtk.Template.Child()
    details_view_title: Gtk.Label = Gtk.Template.Child()
    details_view_blurred_cover: Gtk.Picture = Gtk.Template.Child()
    details_view_play_button: Gtk.Button = Gtk.Template.Child()
    details_view_developer: Gtk.Label = Gtk.Template.Child()
    details_view_added: Gtk.ShortcutLabel = Gtk.Template.Child()
    details_view_last_played: Gtk.Label = Gtk.Template.Child()
    details_view_hide_button: Gtk.Button = Gtk.Template.Child()

    hidden_library_page: Adw.NavigationPage = Gtk.Template.Child()
    hidden_primary_menu_button: Gtk.MenuButton = Gtk.Template.Child()
    hidden_library: Gtk.GridView = Gtk.Template.Child()
    hidden_library_view: Adw.ToolbarView = Gtk.Template.Child()
    hidden_scrolledwindow: Gtk.ScrolledWindow = Gtk.Template.Child()
    hidden_library_overlay: Gtk.Overlay = Gtk.Template.Child()
    hidden_notice_empty: Adw.StatusPage = Gtk.Template.Child()
    hidden_notice_no_results: Adw.StatusPage = Gtk.Template.Child()
    hidden_search_bar: Gtk.SearchBar = Gtk.Template.Child()
    hidden_search_entry: Gtk.SearchEntry = Gtk.Template.Child()
    hidden_search_button: Gtk.ToggleButton = Gtk.Template.Child()

    game_covers: dict = {}
    toasts: dict = {}
    active_game: Game
    details_view_game_cover: Optional[GameCover] = None
    sort_state: str = "last_played"
    filter_state: str = "all"
    source_rows: dict = {}

    def create_source_rows(self) -> None:
        def get_removed(source_id: str) -> Any:
            removed = tuple(
                game.removed or game.hidden or game.blacklisted
                for game in shared.store.source_games[source_id].values()
            )
            return (
                (count,) if (count := sum(removed)) != len(removed) else False
            )

        total_games_no = 0
        restored = False

        selected_id = (
            self.source_rows[selected_row][0]
            if (selected_row := self.sidebar.get_selected_row()) in self.source_rows
            else None
        )

        if selected_row == self.added_row_box.get_parent():
            self.sidebar.select_row(self.added_row_box.get_parent())
            restored = True

        if added_missing := (
            not shared.store.source_games.get("imported")
            or not (removed := get_removed("imported"))
        ):
            self.sidebar.select_row(self.all_games_row_box.get_parent())
        else:
            games_no = len(shared.store.source_games["imported"]) - removed[0]
            self.added_games_no_label.set_label(str(games_no))
            total_games_no += games_no
        self.added_row_box.get_parent().set_visible(not added_missing)

        self.sidebar.get_row_at_index(2).set_visible(False)

        while row := self.sidebar.get_row_at_index(3):
            self.sidebar.remove(row)

        for source_id in shared.store.source_games:
            if source_id == "imported":
                continue
            if not (removed := get_removed(source_id)):
                continue

            row = Gtk.Box(
                margin_top=12,
                margin_bottom=12,
                margin_start=6,
                margin_end=6,
                spacing=12,
            )
            games_no = len(shared.store.source_games[source_id]) - removed[0]
            total_games_no += games_no

            row.append(
                Gtk.Image.new_from_icon_name(
                    "user-desktop-symbolic"
                    if (split_id := source_id.split("_")[0]) == "desktop"
                    else f"{split_id}-source-symbolic"
                )
            )

            row.append(
                Gtk.Label(
                    label=self.get_application().get_source_name(source_id),
                    halign=Gtk.Align.START,
                    wrap=True,
                    wrap_mode=Pango.WrapMode.CHAR,
                )
            )

            row.append(
                games_no_label := Gtk.Label(
                    label=games_no,
                    hexpand=True,
                    halign=Gtk.Align.END,
                )
            )

            games_no_label.add_css_class("dim-label")

            index = 3
            while source_row := self.sidebar.get_row_at_index(index):
                if self.source_rows[source_row][1] < games_no:
                    self.sidebar.insert(row, index)
                    break
                index += 1
            if not row.get_parent():
                self.sidebar.append(row)

            self.source_rows[row.get_parent()] = (
                source_id,
                games_no,
            )

            if source_id == selected_id:
                self.sidebar.select_row(row.get_parent())
                restored = True

            self.sidebar.get_row_at_index(2).set_visible(True)

        self.all_games_no_label.set_label(str(total_games_no))

        if not restored:
            self.sidebar.select_row(self.all_games_row_box.get_parent())

    def row_selected(self, _widget: Any, row: Gtk.ListBoxRow | None) -> None:
        if not row:
            return
        match row.get_child():
            case self.all_games_row_box:
                value = "all"
            case self.added_row_box:
                value = "imported"
            case _:
                value = self.source_rows[row][0]

        self.library_page.set_title(self.get_application().get_source_name(value))

        self.filter_state = value
        self.library_filter.changed(Gtk.FilterChange.DIFFERENT)
        self.hidden_library_filter.changed(Gtk.FilterChange.DIFFERENT)

        if self.overlay_split_view.get_collapsed():
            self.overlay_split_view.set_show_sidebar(False)

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)

        if platform == "darwin":
            self.sidebar_navigation_page.set_title("")

        self.details_view.set_measure_overlay(self.details_view_toolbar_view, True)
        self.details_view.set_clip_overlay(self.details_view_toolbar_view, False)

        # MVC ListModel Setup
        self.game_store = Gio.ListStore.new(Game)

        self.sorter = Gtk.CustomSorter.new(self.sort_func)

        # Main Library Pipeline
        self.library_filter = Gtk.CustomFilter.new(self.filter_func_main)
        self.library_filter_model = Gtk.FilterListModel.new(self.game_store, self.library_filter)
        self.library_sort_model = Gtk.SortListModel.new(self.library_filter_model, self.sorter)
        self.library_selection = Gtk.SingleSelection.new(self.library_sort_model)
        self.library.set_model(self.library_selection)

        factory = Gtk.SignalListItemFactory()
        factory.connect("setup", self.setup_library_item)
        factory.connect("bind", self.bind_library_item)
        self.library.set_factory(factory)

        # Hidden Library Pipeline
        self.hidden_library_filter = Gtk.CustomFilter.new(self.filter_func_hidden)
        self.hidden_filter_model = Gtk.FilterListModel.new(self.game_store, self.hidden_library_filter)
        self.hidden_sort_model = Gtk.SortListModel.new(self.hidden_filter_model, self.sorter)
        self.hidden_selection = Gtk.SingleSelection.new(self.hidden_sort_model)
        self.hidden_library.set_model(self.hidden_selection)

        hidden_factory = Gtk.SignalListItemFactory()
        hidden_factory.connect("setup", self.setup_library_item)
        hidden_factory.connect("bind", self.bind_library_item)
        self.hidden_library.set_factory(hidden_factory)

        self.library.connect("activate", self.on_game_activated)
        self.hidden_library.connect("activate", self.on_game_activated)

        self.notice_empty.set_icon_name(shared.APP_ID + "-symbolic")

        self.overlay_split_view.set_show_sidebar(
            shared.state_schema.get_boolean("show-sidebar")
        )

        self.sidebar.select_row(self.all_games_row_box.get_parent())

        if shared.PROFILE == "development":
            self.add_css_class("devel")

        self.search_bar.connect_entry(self.search_entry)
        self.hidden_search_bar.connect_entry(self.hidden_search_entry)

        self.search_entry.connect("search-changed", self.search_changed, False)
        self.hidden_search_entry.connect("search-changed", self.search_changed, True)

        self.search_entry.connect("activate", self.show_details_page_search)
        self.hidden_search_entry.connect("activate", self.show_details_page_search)

        self.navigation_view.connect("popped", self.set_show_hidden)
        self.navigation_view.connect("pushed", self.set_show_hidden)

        self.sidebar.connect("row-selected", self.row_selected)

        style_manager = Adw.StyleManager.get_default()
        style_manager.connect("notify::dark", self.set_details_view_opacity)
        style_manager.connect("notify::high-contrast", self.set_details_view_opacity)

        if shared.schema.get_uint("library-rows"):
            shared.schema.bind(
                "library-rows",
                self.library,
                "max-columns",
                Gio.SettingsBindFlags.DEFAULT,
            )
            shared.schema.bind(
                "library-rows",
                self.hidden_library,
                "max-columns",
                Gio.SettingsBindFlags.DEFAULT,
            )
        else:
            self.library.set_max_columns(10)
            self.hidden_library.set_max_columns(10)

        # Batch import action
        import_shortcuts_action = Gio.SimpleAction.new("import_shortcuts", None)
        import_shortcuts_action.connect("activate", self.on_import_shortcuts_action)
        self.add_action(import_shortcuts_action)

    def add_game_to_ui(self, game: Game) -> None:
        self.game_store.append(game)
        self.set_library_child()

    def remove_game_from_ui(self, game: Game) -> None:
        for i in range(self.game_store.get_n_items()):
            if self.game_store.get_item(i) == game:
                self.game_store.remove(i)
                break
        self.set_library_child()

    def setup_library_item(self, factory: Gtk.SignalListItemFactory, list_item: Gtk.ListItem) -> None:
        pass 

    def bind_library_item(self, factory: Gtk.SignalListItemFactory, list_item: Gtk.ListItem) -> None:
        game_widget = list_item.get_item()
        if game_widget:
            parent = game_widget.get_parent()
            if parent:
                parent.remove(game_widget)
            list_item.set_child(game_widget)

    def on_game_activated(self, grid_view: Gtk.GridView, position: int) -> None:
        model = grid_view.get_model()
        game = model.get_item(position)
        if game:
            self.show_details_page(game)

    def search_changed(self, _widget: Any, hidden: bool) -> None:
        if hidden:
            self.hidden_library_filter.changed(Gtk.FilterChange.DIFFERENT)
        else:
            self.library_filter.changed(Gtk.FilterChange.DIFFERENT)

    def set_library_child(self) -> None:
        def remove_from_overlay(widget: Gtk.Widget) -> None:
            if isinstance(widget.get_parent(), Gtk.Overlay):
                widget.get_parent().remove_overlay(widget)

        if self.game_store.get_n_items() == 0:
            self.library_overlay.add_overlay(self.notice_empty)
        elif self.library_selection.get_n_items() == 0:
            remove_from_overlay(self.notice_empty)
            self.library_overlay.add_overlay(self.notice_no_results)
        else:
            remove_from_overlay(self.notice_empty)
            remove_from_overlay(self.notice_no_results)

        hidden_count = sum(1 for i in range(self.game_store.get_n_items()) if getattr(self.game_store.get_item(i), 'hidden', False))
        if hidden_count == 0:
            self.hidden_library_overlay.add_overlay(self.hidden_notice_empty)
        elif self.hidden_selection.get_n_items() == 0:
            remove_from_overlay(self.hidden_notice_empty)
            self.hidden_library_overlay.add_overlay(self.hidden_notice_no_results)
        else:
            remove_from_overlay(self.hidden_notice_empty)
            remove_from_overlay(self.hidden_notice_no_results)

    def filter_func_main(self, game: Game) -> bool:
        return self.base_filter(game, False)

    def filter_func_hidden(self, game: Game) -> bool:
        return self.base_filter(game, True)

    def base_filter(self, game: Game, hidden_view: bool) -> bool:
        if getattr(game, 'removed', False) or getattr(game, 'blacklisted', False):
            return False
            
        if hidden_view and not getattr(game, 'hidden', False):
            return False
        if not hidden_view and getattr(game, 'hidden', False):
            return False

        text = (
            self.hidden_search_entry
            if hidden_view
            else self.search_entry
        ).get_text().lower()

        filtered = text != "" and not (
            text in game.name.lower()
            or (text in game.developer.lower() if getattr(game, 'developer', None) else False)
        )

        if not filtered:
            if self.filter_state == "all":
                pass
            elif getattr(game, 'base_source', '') != self.filter_state:
                filtered = True

        game.filtered = filtered
        GLib.idle_add(self.set_library_child)
        return not filtered

    def sort_func(self, game1: Game, game2: Game) -> int:
        var, order = "name", True

        if self.sort_state in ("newest", "oldest"):
            var, order = "added", self.sort_state == "newest"
        elif self.sort_state == "last_played":
            var = "last_played"
        elif self.sort_state == "a-z":
            order = False

        def get_value(g: Game) -> str:
            val = getattr(g, var)
            if val is None:
                val = ""
            return str(val).lower().removeprefix("the ")

        val1, val2 = get_value(game1), get_value(game2)

        if var != "name" and val1 == val2:
            var, order = "name", False
            val1 = get_value(game1)
            val2 = get_value(game2)

        return ((val1 > val2) ^ order) * 2 - 1

    def set_active_game(self, _widget: Any, _pspec: Any, game: Game) -> None:
        self.active_game = game

    def show_details_page(self, game: Game) -> None:
        self.active_game = game

        self.details_view_cover.set_opacity(int(not getattr(game, 'loading', 0)))
        self.details_view_spinner.set_visible(bool(getattr(game, 'loading', 0)))

        self.details_view_developer.set_label(game.developer or "")
        self.details_view_developer.set_visible(bool(game.developer))

        icon, text = "view-conceal-symbolic", _("Hide")
        if game.hidden:
            icon, text = "view-reveal-symbolic", _("Unhide")

        self.details_view_hide_button.set_icon_name(icon)
        self.details_view_hide_button.set_tooltip_text(text)

        if self.details_view_game_cover:
            self.details_view_game_cover.pictures.remove(self.details_view_cover)

        self.details_view_game_cover = game.game_cover
        self.details_view_game_cover.add_picture(self.details_view_cover)

        self.details_view_blurred_cover.set_paintable(
            self.details_view_game_cover.get_blurred()
        )

        self.details_view_title.set_label(game.name)
        self.details_page.set_title(game.name)

        date = relative_date(game.added)
        self.details_view_added.set_label(
            _("Added: {}").format(date)
        )
        last_played_date = (
            relative_date(game.last_played) if getattr(game, 'last_played', 0) else _("Never")
        )
        self.details_view_last_played.set_label(
            _("Last played: {}").format(last_played_date)
        )

        if self.navigation_view.get_visible_page() != self.details_page:
            self.navigation_view.push(self.details_page)
            self.set_focus(self.details_view_play_button)

        self.set_details_view_opacity()

    def set_details_view_opacity(self, *_args: Any) -> None:
        if self.navigation_view.get_visible_page() != self.details_page:
            return

        if (
            style_manager := Adw.StyleManager.get_default()
        ).get_high_contrast() or not style_manager.get_system_supports_color_schemes():
            self.details_view_blurred_cover.set_opacity(0.3)
            return

        self.details_view_blurred_cover.set_opacity(
            1 - self.details_view_game_cover.luminance[0]
            if style_manager.get_dark()
            else self.details_view_game_cover.luminance[1]
        )

    def set_show_hidden(self, navigation_view: Adw.NavigationView, *_args: Any) -> None:
        self.lookup_action("show_hidden").set_enabled(
            navigation_view.get_visible_page() == self.library_page
        )

    def on_show_sidebar_action(self, *_args: Any) -> None:
        shared.state_schema.set_boolean(
            "show-sidebar", (value := not self.overlay_split_view.get_show_sidebar())
        )
        self.overlay_split_view.set_show_sidebar(value)

    def on_go_to_parent_action(self, *_args: Any) -> None:
        if self.navigation_view.get_visible_page() == self.details_page:
            self.navigation_view.pop()

    def on_go_home_action(self, *_args: Any) -> None:
        self.navigation_view.pop_to_page(self.library_page)

    def on_show_hidden_action(self, *_args: Any) -> None:
        if self.navigation_view.get_visible_page() == self.hidden_library_page:
            return

        self.navigation_view.push(self.hidden_library_page)

    def on_sort_action(self, action: Gio.SimpleAction, state: GLib.Variant) -> None:
        action.set_state(state)
        self.sort_state = str(state).strip("'")
        self.sorter.changed(Gtk.SorterChange.DIFFERENT)

        shared.state_schema.set_string("sort-mode", self.sort_state)

    def on_toggle_search_action(self, *_args: Any) -> None:
        if self.navigation_view.get_visible_page() == self.library_page:
            search_bar = self.search_bar
            search_entry = self.search_entry
        elif self.navigation_view.get_visible_page() == self.hidden_library_page:
            search_bar = self.hidden_search_bar
            search_entry = self.hidden_search_entry
        else:
            return

        search_bar.set_search_mode(not (search_mode := search_bar.get_search_mode()))

        if not search_mode:
            self.set_focus(search_entry)

        search_entry.set_text("")

    def show_details_page_search(self, widget: Gtk.Widget) -> None:
        model = self.hidden_selection if widget == self.hidden_search_entry else self.library_selection
        if model.get_n_items() > 0:
            game = model.get_item(0)
            self.show_details_page(game)

    def on_undo_action(
        self, _widget: Any, game: Optional[Game] = None, undo: Optional[str] = None
    ) -> None:
        if not game:
            if shared.importer and (
                shared.importer.imported_game_ids or shared.importer.removed_game_ids
            ):
                shared.importer.undo_import()
                return

            try:
                game = tuple(self.toasts.keys())[-1][0]
                undo = tuple(self.toasts.keys())[-1][1]
            except IndexError:
                return

        if game:
            if undo == "hide":
                game.toggle_hidden(False)
            elif undo == "remove":
                game.removed = False
                game.save()
                game.update()
                if game not in self.game_store:
                    self.add_game_to_ui(game)

            self.toasts[(game, undo)].dismiss()
            self.toasts.pop((game, undo))

    def on_open_menu_action(self, *_args: Any) -> None:
        if self.navigation_view.get_visible_page() == self.library_page:
            self.primary_menu_button.popup()
        elif self.navigation_view.get_visible_page() == self.hidden_library_page:
            self.hidden_primary_menu_button.popup()

    def on_close_action(self, *_args: Any) -> None:
        self.close()

    def on_import_shortcuts_action(self, *_args: Any) -> None:
        exec_filter = Gtk.FileFilter(name=_("Atalhos e Executáveis"))
        exec_filter.add_mime_type("application/x-executable")
        exec_filter.add_suffix("exe")
        exec_filter.add_suffix("bat")
        exec_filter.add_suffix("url")
        exec_filter.add_suffix("lnk")

        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(exec_filter)

        dialog = Gtk.FileDialog()
        dialog.set_title(_("Selecione os Atalhos para Importar"))
        dialog.set_filters(filters)
        dialog.set_default_filter(exec_filter)
        dialog.open_multiple(self, None, self.process_imported_shortcuts)

    def process_imported_shortcuts(self, dialog: Gtk.FileDialog, result: Gio.Task) -> None:
        try:
            files = dialog.open_multiple_finish(result)
        except GLib.Error:
            return

        def import_thread() -> None:
            max_num = 0
            try:
                from cartridges.utils.sqlite import get_conn
                with get_conn() as conn:
                    cursor = conn.execute("SELECT game_id FROM games WHERE source = 'imported'")
                    for row in cursor:
                        gid = row["game_id"]
                        if gid.startswith("imported_"):
                            try:
                                num = int(gid.replace("imported_", ""))
                                if num > max_num:
                                    max_num = num
                            except ValueError:
                                pass
            except Exception:
                pass
                
            current_num = max_num + 1
            games_to_process = []

            for i in range(files.get_n_items()):
                file = files.get_item(i)
                path = file.get_path()
                if not path:
                    continue
                
                path_obj = Path(path)
                name = path_obj.stem
                executable = path
                game_id = f"imported_{current_num}"
                
                if path.lower().endswith(".url"):
                    try:
                        with open(path, "r", encoding="utf-8", errors="ignore") as f:
                            for line in f:
                                if line.strip().upper().startswith("URL="):
                                    url = line.split("=", 1)[1].strip()
                                    executable = f'start "" "{url}"' if platform == "win32" else f'xdg-open "{url}"'
                                    break
                    except Exception:
                        pass
                        
                elif platform == "win32" and path.lower().endswith(".lnk"):
                    lnk_path = path_obj
                    if lnk_path.is_file():
                        links_dir = shared.games_dir.parent / "links"
                        links_dir.mkdir(parents=True, exist_ok=True)
                        internal_lnk = links_dir / f"{game_id}.lnk"
                        
                        shutil.copy2(lnk_path, internal_lnk)
                        executable = f'start "" "{internal_lnk}"'
                else:
                    executable = shlex.quote(path)

                current_num += 1

                game = Game({
                    "game_id": game_id,
                    "hidden": False,
                    "source": "imported",
                    "added": int(time()),
                    "name": name,
                    "executable": executable
                })
                games_to_process.append(game)

            GLib.idle_add(dispatch_pipeline, games_to_process)

        def dispatch_pipeline(games: list) -> bool:
            if hasattr(self.toast_overlay, "add_toast"):
                toast = Adw.Toast.new(_("A processar e importar {} atalhos...").format(len(games)))
                toast.set_timeout(3)
                self.toast_overlay.add_toast(toast)

            for game in games:
                shared.store.add_game(game, {}, run_pipeline=True)
                
            return False

        threading.Thread(target=import_thread, daemon=True).start()
