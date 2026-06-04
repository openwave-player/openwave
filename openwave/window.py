from __future__ import annotations

import json
import os
import random
from collections import defaultdict
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Gst", "1.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gst, Gtk, Pango

from .constants import APP_VERSION, AUDIO_EXTENSIONS
from .dialogs import PlaylistDialog, show_about_dialog
from .mpris import MPRISProvider
from .player import Player
from .updater import check_for_updates, download_and_restart
from .utils import ensure_dir, read_audio_metadata
from .ui_builder import (
    APP_CSS,
    apply_css,
    build_header,
    sidebar_section,
    add_sidebar_row,
)


class OpenWave(Gtk.Window):
    def __init__(self):
        super().__init__(title="OpenWave")
        self.set_default_size(1180, 760)
        self.set_resizable(True)

        # Diretórios e config
        self.base_dir = Path(GLib.get_user_config_dir()) / "openwave"
        ensure_dir(self.base_dir)
        self.config_file = self.base_dir / "state.json"

        # Estado da biblioteca
        self.library_folder: str | None = None
        self.library_tracks: list[dict] = []
        self.track_by_path: dict[str, dict] = {}
        self.artist_index: dict[str, list[dict]] = {}
        self.album_index: dict[tuple[str, str], list[dict]] = {}

        # Favoritos e playlists
        self.favorites: set[str] = set()
        self.playlists: dict[str, list[str]] = {}

        # Estado da view
        self.current_view = "library"
        self.current_playlist_name: str | None = None
        self.current_artist_name: str | None = None
        self.current_album_key: tuple[str, str] | None = None
        self._syncing_sidebar_selection = False

        # Estado da fila
        self.current_queue: list[dict] = []
        self.user_queue: list[dict] = []
        self.play_history: list[str] = []

        # Estado da faixa e MPRIS
        self.selected_track_path: str | None = None
        self.current_track_path: str | None = None
        self.is_shuffle = False
        self.current_cover_url = ""

        self.current_title = "Nenhuma faixa"
        self.current_artist = "OpenWave"
        self.current_album = ""

        # Inicialização
        self._load_state()
        self.mpris = MPRISProvider(self)
        apply_css(APP_CSS)
        self._setup_header()
        self._player = Player()
        self._player.on_tag_found_cb = self.on_tag_found
        self._player.on_eos_cb = self.on_eos
        self._player.on_error_cb = self.on_error
        self._player.on_progress_cb = self._on_player_progress
        self._build_ui()

        if self.library_folder:
            self._scan_library(self.library_folder, quiet=True)
            self._set_view("library")
        else:
            self._set_default_cover()
            self._update_header_subtitle()
            self._apply_track_view()

        self.connect("destroy", self._on_destroy)
        self.show_all()

        has_tracks = bool(self.library_tracks or self.current_view in {"queue", "playlist", "favorites"})
        self.empty_label.set_visible(not has_tracks)

        check_for_updates(self._on_update_available)

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    def _on_destroy(self, *args) -> None:
        self._player.null()
        self._save_state()

    # ------------------------------------------------------------------
    # UI principal
    # ------------------------------------------------------------------

    def _setup_header(self) -> None:
        self.header, self.btn_choose_folder, self.btn_refresh, self.btn_about = build_header(
            on_choose_folder=self.on_choose_folder_clicked,
            on_refresh=self.on_refresh_clicked,
            on_about=self.on_about_clicked,
        )
        self.set_titlebar(self.header)

    def _build_ui(self) -> None:
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(root)

        body = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        body.get_style_context().add_class("main-background")
        root.pack_start(body, True, True, 0)

        self.sidebar = self._build_sidebar()
        body.pack1(self.sidebar, resize=False, shrink=False)

        main_area = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        main_area.get_style_context().add_class("content-area")
        body.pack2(main_area, resize=True, shrink=False)

        # Cabeçalho da lista
        list_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        list_header.set_border_width(18)
        list_header.set_hexpand(True)

        self.source_label = Gtk.Label(label="Biblioteca")
        self.source_label.set_halign(Gtk.Align.START)
        self.source_label.set_xalign(0.0)
        self.source_label.get_style_context().add_class("title-1")
        list_header.pack_start(self.source_label, False, False, 0)

        search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        search_box.set_halign(Gtk.Align.END)
        search_box.set_hexpand(True)

        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("Pesquisar músicas, artista ou álbum...")
        self.search_entry.set_width_chars(32)
        self.search_entry.connect("search-changed", self.on_search_changed)
        search_box.pack_end(self.search_entry, True, True, 0)
        list_header.pack_end(search_box, True, True, 0)

        main_area.pack_start(list_header, False, False, 0)

        # Browser de álbuns
        self.album_browser_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.album_browser_box.set_border_width(0)
        self.album_browser_box.get_style_context().add_class("album-browser")

        album_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        album_header.set_hexpand(True)

        album_title_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.album_browser_label = Gtk.Label(label="Artista")
        self.album_browser_label.set_halign(Gtk.Align.START)
        self.album_browser_label.set_xalign(0.0)
        self.album_browser_label.get_style_context().add_class("title-2")
        album_title_box.pack_start(self.album_browser_label, False, False, 0)

        self.album_browser_subtitle = Gtk.Label(label="Selecione um artista para ver os álbuns.")
        self.album_browser_subtitle.set_halign(Gtk.Align.START)
        self.album_browser_subtitle.set_xalign(0.0)
        self.album_browser_subtitle.get_style_context().add_class("section-note")
        album_title_box.pack_start(self.album_browser_subtitle, False, False, 0)
        album_header.pack_start(album_title_box, True, True, 0)

        self.btn_artist_tracks = Gtk.Button.new_with_label("Todos os álbuns")
        self.btn_artist_tracks.get_style_context().add_class("control-btn-flat")
        self.btn_artist_tracks.connect("clicked", self.on_artist_tracks_clicked)
        album_header.pack_end(self.btn_artist_tracks, False, False, 0)
        self.album_browser_box.pack_start(album_header, False, False, 0)

        selector_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        selector_row.set_hexpand(True)

        self.album_selector = Gtk.ComboBoxText()
        self.album_selector.set_hexpand(True)
        self.album_selector.get_style_context().add_class("album-select")
        self.album_selector.connect("changed", self.on_album_selector_changed)
        selector_row.pack_start(self.album_selector, True, True, 0)

        self.album_count_label = Gtk.Label(label="")
        self.album_count_label.set_halign(Gtk.Align.END)
        self.album_count_label.get_style_context().add_class("section-note")
        selector_row.pack_end(self.album_count_label, False, False, 0)
        self.album_browser_box.pack_start(selector_row, False, False, 0)

        self.album_flowbox = Gtk.FlowBox()
        self.album_flowbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.album_flowbox.set_row_spacing(10)
        self.album_flowbox.set_column_spacing(10)
        self.album_flowbox.set_max_children_per_line(4)
        self.album_flowbox.set_min_children_per_line(1)

        album_scroll = Gtk.ScrolledWindow()
        album_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        album_scroll.set_shadow_type(Gtk.ShadowType.NONE)
        album_scroll.set_hexpand(True)
        album_scroll.set_vexpand(False)
        album_scroll.set_min_content_height(168)
        album_scroll.add(self.album_flowbox)

        self.album_empty_label = Gtk.Label(label="Selecione um artista para ver os álbuns.")
        self.album_empty_label.set_halign(Gtk.Align.CENTER)
        self.album_empty_label.set_valign(Gtk.Align.CENTER)
        self.album_empty_label.get_style_context().add_class("album-browser-empty")

        self.album_overlay = Gtk.Overlay()
        self.album_overlay.add(album_scroll)
        self.album_overlay.add_overlay(self.album_empty_label)

        self.album_browser_box.set_visible(False)
        main_area.pack_start(self.album_browser_box, False, False, 0)

        # Lista de faixas
        self.empty_label = Gtk.Label(label="Abra uma pasta para ver suas músicas.")
        self.empty_label.set_halign(Gtk.Align.CENTER)
        self.empty_label.set_valign(Gtk.Align.CENTER)
        self.empty_label.get_style_context().add_class("empty-state")

        self.track_scroll_overlay = Gtk.Overlay()
        self.track_scroll = Gtk.ScrolledWindow()
        self.track_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.track_scroll.set_shadow_type(Gtk.ShadowType.NONE)

        self.track_listbox = Gtk.ListBox()
        self.track_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.track_listbox.set_activate_on_single_click(True)
        self.track_listbox.connect("row-activated", self.on_track_activated)
        self.track_listbox.connect("row-selected", self.on_track_selected)
        self.track_listbox.connect("button-press-event", self.on_track_button_press)
        self.track_listbox.get_style_context().add_class("track-list")

        self.track_scroll.add(self.track_listbox)
        self.track_scroll_overlay.add(self.track_scroll)
        self.track_scroll_overlay.add_overlay(self.empty_label)
        main_area.pack_start(self.track_scroll_overlay, True, True, 0)

        # Barra inferior
        bottom_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
        bottom_bar.get_style_context().add_class("bottom-bar")
        bottom_bar.set_border_width(12)
        root.pack_end(bottom_bar, False, False, 0)

        # Now playing
        now_playing_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        now_playing_box.set_size_request(280, -1)

        self.cover_image = Gtk.Image()
        self.cover_image.set_size_request(60, 60)
        cover_frame = Gtk.Frame()
        cover_frame.get_style_context().add_class("cover-frame-small")
        cover_frame.add(self.cover_image)
        now_playing_box.pack_start(cover_frame, False, False, 0)

        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        info_box.set_valign(Gtk.Align.CENTER)

        self.track_label = Gtk.Label(label=self.current_title)
        self.track_label.set_halign(Gtk.Align.START)
        self.track_label.set_xalign(0.0)
        self.track_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.track_label.set_width_chars(28)
        self.track_label.set_max_width_chars(28)
        self.track_label.get_style_context().add_class("track-title-bold")
        info_box.pack_start(self.track_label, False, False, 0)

        self.artist_label = Gtk.Label(label=self.current_artist)
        self.artist_label.set_halign(Gtk.Align.START)
        self.artist_label.set_xalign(0.0)
        self.artist_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.artist_label.set_width_chars(28)
        self.artist_label.set_max_width_chars(28)
        self.artist_label.get_style_context().add_class("muted")
        info_box.pack_start(self.artist_label, False, False, 0)

        now_playing_box.pack_start(info_box, True, True, 0)
        bottom_bar.pack_start(now_playing_box, False, False, 0)

        # Controles centrais
        center_dock = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        center_dock.set_valign(Gtk.Align.CENTER)
        center_dock.set_hexpand(True)

        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        btn_row.set_halign(Gtk.Align.CENTER)

        self.btn_shuffle = Gtk.Button.new_from_icon_name("media-playlist-shuffle-symbolic", Gtk.IconSize.LARGE_TOOLBAR)
        self.btn_shuffle.get_style_context().add_class("control-btn-flat")
        self.btn_shuffle.get_style_context().add_class("unstarred")
        self.btn_shuffle.set_tooltip_text("Ordem aleatória")
        self.btn_shuffle.connect("clicked", self.on_shuffle_clicked)

        self.btn_prev = Gtk.Button.new_from_icon_name("media-skip-backward-symbolic", Gtk.IconSize.LARGE_TOOLBAR)
        self.btn_prev.get_style_context().add_class("control-btn-flat")
        self.btn_prev.connect("clicked", self.on_prev_clicked)

        self.btn_play = Gtk.Button.new_from_icon_name("media-playback-start-symbolic", Gtk.IconSize.LARGE_TOOLBAR)
        self.btn_play.get_style_context().add_class("control-btn-main")
        self.btn_play.connect("clicked", self.on_play_clicked)

        self.btn_next = Gtk.Button.new_from_icon_name("media-skip-forward-symbolic", Gtk.IconSize.LARGE_TOOLBAR)
        self.btn_next.get_style_context().add_class("control-btn-flat")
        self.btn_next.connect("clicked", self.on_next_clicked)

        for btn in [self.btn_shuffle, self.btn_prev, self.btn_play, self.btn_next]:
            btn.set_sensitive(False)
            btn_row.pack_start(btn, False, False, 0)

        center_dock.pack_start(btn_row, False, False, 0)

        progress_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.time_current = Gtk.Label(label="00:00")
        self.time_current.get_style_context().add_class("muted-small")
        self.time_total = Gtk.Label(label="00:00")
        self.time_total.get_style_context().add_class("muted-small")

        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_valign(Gtk.Align.CENTER)

        progress_row.pack_start(self.time_current, False, False, 0)
        progress_row.pack_start(self.progress_bar, True, True, 0)
        progress_row.pack_start(self.time_total, False, False, 0)

        center_dock.pack_start(progress_row, True, True, 0)
        bottom_bar.pack_start(center_dock, True, True, 0)

        # Ações (favoritar, playlist)
        actions_dock = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions_dock.set_valign(Gtk.Align.CENTER)
        actions_dock.set_halign(Gtk.Align.END)
        actions_dock.set_size_request(250, -1)

        self.btn_favorite_dock = Gtk.Button.new_from_icon_name("emblem-favorite-symbolic", Gtk.IconSize.BUTTON)
        self.btn_favorite_dock.get_style_context().add_class("control-btn-flat")
        self.btn_favorite_dock.get_style_context().add_class("unstarred")
        self.btn_favorite_dock.set_tooltip_text("Favoritar")
        self.btn_favorite_dock.connect("clicked", self.on_toggle_favorite_clicked)
        self.btn_favorite_dock.set_sensitive(False)
        actions_dock.pack_end(self.btn_favorite_dock, False, False, 0)

        self.btn_add_playlist = Gtk.Button.new_from_icon_name("list-add-symbolic", Gtk.IconSize.BUTTON)
        self.btn_add_playlist.get_style_context().add_class("control-btn-flat")
        self.btn_add_playlist.set_tooltip_text("Adicionar à playlist")
        self.btn_add_playlist.connect("clicked", self.on_add_to_playlist_clicked)
        self.btn_add_playlist.set_sensitive(False)
        actions_dock.pack_end(self.btn_add_playlist, False, False, 0)

        bottom_bar.pack_end(actions_dock, False, False, 0)

    def _build_sidebar(self) -> Gtk.Widget:
        wrapper = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        wrapper.set_size_request(286, -1)
        wrapper.get_style_context().add_class("sidebar")

        top_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        top_box.set_border_width(14)

        lbl_menu = Gtk.Label(label="Sua coleção")
        lbl_menu.set_halign(Gtk.Align.START)
        lbl_menu.set_xalign(0.0)
        lbl_menu.get_style_context().add_class("title-2")
        top_box.pack_start(lbl_menu, False, False, 0)

        lbl_hint = Gtk.Label(label="Artistas rápidos, sem listas longas.")
        lbl_hint.set_halign(Gtk.Align.START)
        lbl_hint.set_xalign(0.0)
        lbl_hint.get_style_context().add_class("section-note")
        top_box.pack_start(lbl_hint, False, False, 0)
        wrapper.pack_start(top_box, False, False, 0)

        sidebar_scroll = Gtk.ScrolledWindow()
        sidebar_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sidebar_scroll.set_shadow_type(Gtk.ShadowType.NONE)
        sidebar_scroll.set_hexpand(True)
        sidebar_scroll.set_vexpand(True)

        sidebar_content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        sidebar_content.set_border_width(12)
        sidebar_scroll.add(sidebar_content)

        nav_section, self.nav_listbox, _ = sidebar_section("Navegação")
        self.nav_listbox.connect("row-selected", self.on_sidebar_selected)
        sidebar_content.pack_start(nav_section, False, False, 0)

        artists_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        artists_section.set_border_width(12)

        artists_header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        artist_label = Gtk.Label(label="Artistas")
        artist_label.set_halign(Gtk.Align.START)
        artist_label.set_xalign(0.0)
        artist_label.get_style_context().add_class("title-2")
        artists_header.pack_start(artist_label, False, False, 0)

        artist_note = Gtk.Label(label="Selecione um artista para ver os álbuns.")
        artist_note.set_halign(Gtk.Align.START)
        artist_note.set_xalign(0.0)
        artist_note.get_style_context().add_class("section-note")
        artists_header.pack_start(artist_note, False, False, 0)
        artists_section.pack_start(artists_header, False, False, 0)

        self.artist_search_entry = Gtk.SearchEntry()
        self.artist_search_entry.set_placeholder_text("Filtrar artistas...")
        self.artist_search_entry.set_hexpand(True)
        self.artist_search_entry.connect("search-changed", self.on_artist_filter_changed)
        self.artist_search_entry.get_style_context().add_class("search-field")
        artists_section.pack_start(self.artist_search_entry, False, False, 0)

        self.artists_listbox = Gtk.ListBox()
        self.artists_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.artists_listbox.set_activate_on_single_click(True)
        self.artists_listbox.connect("row-selected", self.on_sidebar_selected)
        self.artists_listbox.get_style_context().add_class("track-list")

        artists_scroll = Gtk.ScrolledWindow()
        artists_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        artists_scroll.set_shadow_type(Gtk.ShadowType.NONE)
        artists_scroll.set_hexpand(True)
        artists_scroll.set_vexpand(True)
        artists_scroll.set_min_content_height(220)
        artists_scroll.add(self.artists_listbox)
        artists_section.pack_start(artists_scroll, True, True, 0)

        sidebar_content.pack_start(artists_section, True, True, 0)

        playlist_section, self.playlist_listbox, playlist_add_btn = sidebar_section("Playlists", with_add_button=True)
        self.playlist_listbox.connect("row-selected", self.on_sidebar_selected)
        self.playlist_listbox.connect("button-press-event", self.on_sidebar_button_press)
        if playlist_add_btn:
            playlist_add_btn.connect("clicked", self.on_new_playlist_clicked)
        sidebar_content.pack_start(playlist_section, False, False, 0)

        wrapper.pack_start(sidebar_scroll, True, True, 0)
        return wrapper

    # ------------------------------------------------------------------
    # Estado persistido
    # ------------------------------------------------------------------

    def _load_state(self) -> None:
        if not self.config_file.exists():
            return
        try:
            data = json.loads(self.config_file.read_text(encoding="utf-8"))
            self.library_folder = data.get("library_folder")
            self.favorites = set(data.get("favorites", []))
            playlists = data.get("playlists", {})
            if isinstance(playlists, dict):
                self.playlists = {
                    str(key): list(value)
                    for key, value in playlists.items()
                    if isinstance(value, list)
                }
        except Exception:
            pass

    def _save_state(self) -> None:
        data = {
            "library_folder": self.library_folder,
            "favorites": sorted(self.favorites),
            "playlists": self.playlists,
        }
        try:
            self.config_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Biblioteca
    # ------------------------------------------------------------------

    def _scan_library(self, folder: str, quiet: bool = False) -> None:
        root = Path(folder)
        if not root.exists():
            self.library_tracks = []
            self.track_by_path = {}
            self.artist_index = {}
            self.album_index = {}
            self._refresh_sidebar()
            self._update_header_subtitle()
            self._apply_track_view()
            return

        tracks: list[dict] = []
        for current_root, _, files in os.walk(root):
            for filename in files:
                path = Path(current_root) / filename
                if path.suffix.lower() in AUDIO_EXTENSIONS:
                    tracks.append(read_audio_metadata(str(path)))

        tracks.sort(key=lambda item: (
            item["artist"].lower(),
            item["album"].lower(),
            item["title"].lower(),
        ))

        self.library_tracks = tracks
        self.track_by_path = {track["path"]: track for track in tracks}

        artist_map: dict[str, list[dict]] = defaultdict(list)
        album_map: dict[tuple[str, str], list[dict]] = defaultdict(list)

        for track in tracks:
            artist_map[track["artist"]].append(track)
            album_map[(track["album"], track["artist"])].append(track)

        self.artist_index = dict(artist_map)
        self.album_index = dict(album_map)

        self.library_folder = folder
        self._save_state()
        self._refresh_sidebar()
        self._update_header_subtitle()
        self._apply_track_view()

    # ------------------------------------------------------------------
    # Sidebar
    # ------------------------------------------------------------------

    def _clear_listbox(self, listbox: Gtk.ListBox) -> None:
        for child in listbox.get_children():
            listbox.remove(child)

    def _refresh_sidebar(self) -> None:
        if not hasattr(self, "nav_listbox"):
            return

        self._clear_listbox(self.nav_listbox)
        self._clear_listbox(self.playlist_listbox)
        self._refresh_artist_browser()

        add_sidebar_row(self.nav_listbox, "Biblioteca", "library", "folder-music-symbolic")
        add_sidebar_row(self.nav_listbox, "Favoritos", "favorites", "emblem-favorite-symbolic")
        add_sidebar_row(self.nav_listbox, "Fila de reprodução", "queue", "media-playlist-consecutive-symbolic")

        for name in sorted(self.playlists.keys(), key=str.lower):
            tracks = self.playlists.get(name, [])
            subtitle = f"{len(tracks)} faixa{'s' if len(tracks) != 1 else ''}"
            add_sidebar_row(
                self.playlist_listbox,
                name,
                "playlist",
                "view-list-symbolic",
                subtitle=subtitle,
                playlist_name=name,
            )

        self.nav_listbox.show_all()
        self.playlist_listbox.show_all()

    def _refresh_artist_browser(self) -> None:
        if not hasattr(self, "artists_listbox"):
            return

        self._clear_listbox(self.artists_listbox)

        artist_filter = ""
        if hasattr(self, "artist_search_entry"):
            artist_filter = self.artist_search_entry.get_text().strip().lower()

        artists = sorted(self.artist_index.items(), key=lambda item: item[0].lower())
        visible_artists: list[str] = []

        for artist_name, tracks in artists:
            if artist_filter and artist_filter not in artist_name.lower():
                continue
            visible_artists.append(artist_name)
            album_keys = self._artist_album_keys(artist_name)
            add_sidebar_row(
                self.artists_listbox,
                artist_name,
                "artist",
                "avatar-default-symbolic",
                subtitle=f"{len(album_keys)} álbum{'s' if len(album_keys) != 1 else ''} • {len(tracks)} faixa{'s' if len(tracks) != 1 else ''}",
                artist_name=artist_name,
            )

        if not visible_artists:
            add_sidebar_row(self.artists_listbox, "Nenhum artista encontrado", "info", "avatar-default-symbolic")

        self.artists_listbox.show_all()

        if self.current_view in {"artist", "album"} and self.current_artist_name:
            self._refresh_album_browser(self.current_artist_name)
        else:
            self._set_album_browser_visible(False)
            self._clear_flowbox(self.album_flowbox)
            self.album_empty_label.set_text("Selecione um artista para ver os álbuns.")

    def _refresh_album_browser(self, artist_name: str | None) -> None:
        if not hasattr(self, "album_flowbox"):
            return

        self._clear_flowbox(self.album_flowbox)

        self.album_selector.handler_block_by_func(self.on_album_selector_changed)
        self.album_selector.remove_all()
        self.album_selector.append_text("Todos os álbuns")

        if not artist_name or artist_name not in self.artist_index:
            self.album_browser_label.set_text("Artista")
            self.album_browser_subtitle.set_text("Selecione um artista para ver os álbuns.")
            self.album_count_label.set_text("")
            self.album_empty_label.set_text("Selecione um artista para ver os álbuns.")
            self.album_selector.set_active(0)
            self.album_selector.handler_unblock_by_func(self.on_album_selector_changed)
            self._set_album_browser_visible(False)
            return

        tracks = self.artist_index.get(artist_name, [])
        album_keys = self._artist_album_keys(artist_name)
        self.album_browser_label.set_text(f"Artista: {artist_name}")
        self.album_browser_subtitle.set_text(
            f"{len(album_keys)} álbum{'s' if len(album_keys) != 1 else ''} • {len(tracks)} faixa{'s' if len(tracks) != 1 else ''}"
        )
        self.album_count_label.set_text(f"{len(album_keys)} álbum{'s' if len(album_keys) != 1 else ''}")
        self.album_empty_label.set_text("Selecione um álbum para ver as músicas.")

        current_album_name = None
        if self.current_album_key and self.current_album_key[1] == artist_name:
            current_album_name = self.current_album_key[0]

        for album_name, album_artist in album_keys:
            self.album_selector.append_text(album_name or "Álbum sem nome")
            album_tracks = self.album_index.get((album_name, album_artist), [])
            active = current_album_name == album_name
            child = self._build_album_card(album_name, album_artist, album_tracks, active=active)
            self.album_flowbox.add(child)

        if current_album_name is None:
            self.album_selector.set_active(0)
        else:
            for idx, (album_name, _) in enumerate(album_keys, start=1):
                if album_name == current_album_name:
                    self.album_selector.set_active(idx)
                    break
            else:
                self.album_selector.set_active(0)

        self.album_selector.handler_unblock_by_func(self.on_album_selector_changed)
        self.album_flowbox.show_all()
        self._set_album_browser_visible(True)

    def _artist_album_keys(self, artist_name: str) -> list[tuple[str, str]]:
        keys = {(track.get("album", ""), track.get("artist", "")) for track in self.artist_index.get(artist_name, [])}
        return sorted(keys, key=lambda item: (item[0].lower(), item[1].lower()))

    def _clear_flowbox(self, flowbox: Gtk.FlowBox) -> None:
        for child in list(flowbox.get_children()):
            flowbox.remove(child)

    def _set_album_browser_visible(self, visible: bool) -> None:
        if hasattr(self, "album_browser_box"):
            self.album_browser_box.set_visible(visible)

    def _build_album_card(self, album_name: str, album_artist: str, album_tracks: list[dict], active: bool = False) -> Gtk.Widget:
        child = Gtk.FlowBoxChild()
        button = Gtk.Button()
        button.set_relief(Gtk.ReliefStyle.NONE)
        button.set_halign(Gtk.Align.FILL)
        button.set_valign(Gtk.Align.FILL)
        button.set_hexpand(True)
        button.set_size_request(168, 92)
        button.get_style_context().add_class("album-card")
        if active:
            button.get_style_context().add_class("album-card-active")
        button.connect("clicked", self.on_album_card_clicked, album_name, album_artist)

        content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        content.set_margin_top(2)
        content.set_margin_bottom(2)
        content.set_margin_start(2)
        content.set_margin_end(2)

        icon = Gtk.Image.new_from_icon_name("media-optical-symbolic", Gtk.IconSize.DIALOG)
        icon.get_style_context().add_class("album-card-icon")
        content.pack_start(icon, False, False, 0)

        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title = Gtk.Label(label=album_name or "Álbum sem nome")
        title.set_halign(Gtk.Align.START)
        title.set_xalign(0.0)
        title.set_ellipsize(Pango.EllipsizeMode.END)
        title.get_style_context().add_class("album-card-title")
        text_box.pack_start(title, False, False, 0)

        subtitle = Gtk.Label(label=f"{album_artist} • {len(album_tracks)} faixa{'s' if len(album_tracks) != 1 else ''}")
        subtitle.set_halign(Gtk.Align.START)
        subtitle.set_xalign(0.0)
        subtitle.set_ellipsize(Pango.EllipsizeMode.END)
        subtitle.get_style_context().add_class("album-card-subtitle")
        text_box.pack_start(subtitle, False, False, 0)

        content.pack_start(text_box, True, True, 0)
        button.add(content)
        child.add(button)
        return child

    # ------------------------------------------------------------------
    # View e fila
    # ------------------------------------------------------------------

    def _update_header_subtitle(self) -> None:
        if self.library_folder:
            self.header.set_subtitle(f"{Path(self.library_folder).name} • {len(self.library_tracks)} faixas")
        else:
            self.header.set_subtitle("Nenhuma pasta selecionada")

    def _active_view_title(self) -> str:
        if self.current_view == "library":
            return "Biblioteca"
        if self.current_view == "favorites":
            return "Favoritos"
        if self.current_view == "queue":
            return "Fila de reprodução"
        if self.current_view == "playlist" and self.current_playlist_name:
            return self.current_playlist_name
        if self.current_view in {"artist", "album"} and self.current_artist_name:
            if self.current_album_key:
                album, _ = self.current_album_key
                return f"Artista: {self.current_artist_name} • {album}"
            return f"Artista: {self.current_artist_name}"
        return "Biblioteca"

    def _view_tracks(self) -> list[dict]:
        if self.current_view == "library":
            return self.library_tracks[:]
        if self.current_view == "favorites":
            return [t for t in self.library_tracks if t["path"] in self.favorites]
        if self.current_view == "queue":
            return self.user_queue[:]
        if self.current_view == "playlist" and self.current_playlist_name:
            return self._resolve_playlist_tracks(self.current_playlist_name)
        if self.current_view in {"artist", "album"} and self.current_artist_name:
            if self.current_album_key:
                return self.album_index.get(self.current_album_key, [])[:]
            return self.artist_index.get(self.current_artist_name, [])[:]
        return self.library_tracks[:]

    def _track_matches_search(self, track: dict, query: str) -> bool:
        if not query:
            return True
        query = query.lower()
        blob = " ".join([track.get("title", ""), track.get("artist", ""), track.get("album", ""), track.get("path", "")]).lower()
        return query in blob

    def _resolve_playlist_tracks(self, name: str) -> list[dict]:
        tracks: list[dict] = []
        for path in self.playlists.get(name, []):
            if path in self.track_by_path:
                tracks.append(self.track_by_path[path])
            elif Path(path).exists():
                tracks.append(read_audio_metadata(path))
        return tracks

    def _apply_track_view(self) -> None:
        query = self.search_entry.get_text().strip()
        tracks = [t for t in self._view_tracks() if self._track_matches_search(t, query)]

        self.current_queue = tracks
        self._rebuild_track_list(tracks)
        self.source_label.set_text(self._active_view_title())

        has_tracks = len(tracks) > 0
        self.btn_shuffle.set_sensitive(has_tracks and self.current_view in {"library", "favorites", "queue", "playlist", "artist", "album"})
        self.btn_prev.set_sensitive(has_tracks)
        self.btn_next.set_sensitive(has_tracks)
        self.btn_play.set_sensitive(has_tracks)
        self.empty_label.set_visible(not has_tracks)
        self._set_album_browser_visible(self.current_view in {"artist", "album"} and bool(self.current_artist_name))

        if not has_tracks and not self.current_track_path:
            self.btn_favorite_dock.set_sensitive(False)
            self.btn_add_playlist.set_sensitive(False)

    def _set_view(
        self,
        view: str,
        playlist_name: str | None = None,
        artist_name: str | None = None,
        album_key: tuple[str, str] | None = None,
    ) -> None:
        self.current_view = view
        self.current_playlist_name = playlist_name
        self.current_artist_name = artist_name
        self.current_album_key = album_key
        self._select_sidebar_row_for_view()
        self._apply_track_view()

    def _select_sidebar_row_for_view(self) -> None:
        self._syncing_sidebar_selection = True
        try:
            self.nav_listbox.unselect_all()
            self.playlist_listbox.unselect_all()
            if hasattr(self, "artists_listbox"):
                self.artists_listbox.unselect_all()

            if self.current_view == "library":
                self._select_row_by_kind(self.nav_listbox, "library")
                self._set_album_browser_visible(False)
            elif self.current_view == "favorites":
                self._select_row_by_kind(self.nav_listbox, "favorites")
                self._set_album_browser_visible(False)
            elif self.current_view == "queue":
                self._select_row_by_kind(self.nav_listbox, "queue")
                self._set_album_browser_visible(False)
            elif self.current_view == "playlist" and self.current_playlist_name:
                self._select_row_by_attr(self.playlist_listbox, "playlist_name", self.current_playlist_name)
                self._set_album_browser_visible(False)
            elif self.current_view in {"artist", "album"} and self.current_artist_name:
                self._select_row_by_attr(self.artists_listbox, "artist_name", self.current_artist_name)
                self._refresh_album_browser(self.current_artist_name)
        finally:
            self._syncing_sidebar_selection = False

    def _select_row_by_kind(self, listbox: Gtk.ListBox, kind: str) -> None:
        for row in listbox.get_children():
            if getattr(row, "kind", None) == kind:
                listbox.select_row(row)
                break

    def _select_row_by_attr(self, listbox: Gtk.ListBox, attr: str, value: str) -> None:
        for row in listbox.get_children():
            if getattr(row, attr, None) == value:
                listbox.select_row(row)
                break

    # ------------------------------------------------------------------
    # Lista de faixas
    # ------------------------------------------------------------------

    def _rebuild_track_list(self, tracks: list[dict]) -> None:
        self._clear_listbox(self.track_listbox)

        for item in tracks:
            row = Gtk.ListBoxRow()
            row.track_path = item["path"]
            row.get_style_context().add_class("track-row")

            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)

            icon = Gtk.Image.new_from_icon_name("audio-x-generic-symbolic", Gtk.IconSize.MENU)
            icon.get_style_context().add_class("muted")
            box.pack_start(icon, False, False, 0)

            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)

            title_lbl = Gtk.Label(label=item["title"])
            title_lbl.set_halign(Gtk.Align.START)
            title_lbl.set_xalign(0.0)
            title_lbl.set_ellipsize(Pango.EllipsizeMode.END)
            title_lbl.get_style_context().add_class("track-title-bold")
            vbox.pack_start(title_lbl, False, False, 0)

            subtitle_lbl = Gtk.Label(label=f'{item["artist"]} • {item["album"]}')
            subtitle_lbl.set_halign(Gtk.Align.START)
            subtitle_lbl.set_xalign(0.0)
            subtitle_lbl.set_ellipsize(Pango.EllipsizeMode.END)
            subtitle_lbl.get_style_context().add_class("muted-small")
            vbox.pack_start(subtitle_lbl, False, False, 0)

            box.pack_start(vbox, True, True, 0)

            duration = item.get("duration") or 0.0
            if duration > 0:
                dur_lbl = Gtk.Label(label=self.format_time_from_seconds(duration))
                dur_lbl.get_style_context().add_class("muted-small")
                box.pack_end(dur_lbl, False, False, 0)

            if item["path"] in self.favorites:
                fav_icon = Gtk.Image.new_from_icon_name("emblem-favorite-symbolic", Gtk.IconSize.MENU)
                box.pack_end(fav_icon, False, False, 0)

            row.add(box)
            self.track_listbox.add(row)

        self.track_listbox.show_all()
        self._update_list_highlight()

    def _update_list_highlight(self) -> None:
        for row in self.track_listbox.get_children():
            if not hasattr(row, "track_path"):
                continue
            ctx = row.get_style_context()
            if row.track_path == self.current_track_path:
                ctx.add_class("playing-row")
            else:
                ctx.remove_class("playing-row")

    def _get_selected_track_path(self) -> str | None:
        row = self.track_listbox.get_selected_row()
        if row and hasattr(row, "track_path"):
            return row.track_path
        return self.selected_track_path or self.current_track_path

    # ------------------------------------------------------------------
    # Now playing UI
    # ------------------------------------------------------------------

    def _update_now_playing_ui(self) -> None:
        self.track_label.set_text(self.current_title)
        if self.current_album:
            self.artist_label.set_text(f"{self.current_artist} • {self.current_album}")
        else:
            self.artist_label.set_text(self.current_artist)

        path = self.selected_track_path or self.current_track_path
        if path:
            is_fav = path in self.favorites
            ctx = self.btn_favorite_dock.get_style_context()
            if is_fav:
                ctx.remove_class("unstarred")
                ctx.add_class("starred")
            else:
                ctx.remove_class("starred")
                ctx.add_class("unstarred")
            self.btn_favorite_dock.set_sensitive(True)
            self.btn_add_playlist.set_sensitive(True)

    def _update_play_pause_icon(self) -> None:
        icon = "media-playback-pause-symbolic" if self._player.is_playing else "media-playback-start-symbolic"
        self.btn_play.set_image(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.LARGE_TOOLBAR))

    def _set_default_cover(self) -> None:
        theme = Gtk.IconTheme.get_default()
        try:
            pixbuf = theme.load_icon("audio-x-generic-symbolic", 60, 0)
            self.cover_image.set_from_pixbuf(pixbuf)
        except Exception:
            self.cover_image.set_from_icon_name("audio-x-generic", Gtk.IconSize.DND)

    def _load_cover_from_bytes(self, raw: bytes | None, size: int = 60) -> bool:
        if not raw:
            return False
        try:
            loader = GdkPixbuf.PixbufLoader()
            loader.write(raw)
            loader.close()
            pixbuf = loader.get_pixbuf()
            if pixbuf is None:
                return False
            scaled = pixbuf.scale_simple(size, size, GdkPixbuf.InterpType.BILINEAR)
            if scaled:
                self.cover_image.set_from_pixbuf(scaled)
                return True
        except Exception:
            return False
        return False

    # ------------------------------------------------------------------
    # Reprodução
    # ------------------------------------------------------------------

    def play_track(self, path: str, push_history: bool = True) -> None:
        if not path or not Path(path).exists():
            return

        track = self.track_by_path.get(path) or read_audio_metadata(path)

        # Atualização local da imagem da capa para que o MPRIS e o applet do sistema tenham acesso ao arquivo visual
        cover_path = self.base_dir / "current_cover.jpg"
        cover_data = track.get("cover_data")
        if cover_data:
            try:
                cover_path.write_bytes(cover_data)
                self.current_cover_url = f"file://{cover_path.absolute()}"
            except Exception:
                self.current_cover_url = ""
        else:
            if cover_path.exists():
                cover_path.unlink()
            self.current_cover_url = ""

        if push_history and self.current_track_path and self.current_track_path != path:
            self.play_history.append(self.current_track_path)

        if not self._load_cover_from_bytes(cover_data, 60):
            self._set_default_cover()

        self.current_title = track["title"]
        self.current_artist = track["artist"]
        self.current_album = track["album"]
        self.current_track_path = path

        self._update_now_playing_ui()
        self.progress_bar.set_fraction(0.0)
        self.time_current.set_text("00:00")
        duration = float(track.get("duration") or 0.0)
        self.time_total.set_text(self.format_time_from_seconds(duration) if duration > 0 else "00:00")

        self._player.play_uri(path)
        self._update_play_pause_icon()
        self._update_list_highlight()

        # Dispara eventos MPRIS assim que muda a faixa
        self.mpris.notify_metadata()
        self.mpris.notify_status()

    def stop_playback(self) -> None:
        self._player.stop()
        self.progress_bar.set_fraction(0.0)
        self.time_current.set_text("00:00")
        self._update_play_pause_icon()
        self.mpris.notify_status()

    def _on_player_progress(self, fraction: float, pos_s: float, dur_s: float) -> None:
        self.progress_bar.set_fraction(fraction)
        self.time_current.set_text(self.format_time_from_seconds(pos_s))
        self.time_total.set_text(self.format_time_from_seconds(dur_s))

    def format_time_from_seconds(self, seconds: float) -> str:
        total = max(0, int(seconds))
        if total >= 3600:
            return f"{total // 3600:02d}:{total % 3600 // 60:02d}:{total % 60:02d}"
        return f"{total // 60:02d}:{total % 60:02d}"

    def _prepare_next_queue_from_selected(self, path: str) -> None:
        idx = next((i for i, t in enumerate(self.current_queue) if t["path"] == path), -1)
        if idx == -1:
            return
        if self.is_shuffle:
            remaining = [t for i, t in enumerate(self.current_queue) if i != idx]
            random.shuffle(remaining)
            self.user_queue = remaining
        else:
            self.user_queue = self.current_queue[idx + 1:]

    def _shift_track(self, direction: int) -> None:
        if direction == 1:
            if self.user_queue:
                next_track = self.user_queue.pop(0)
                if self.current_view == "queue":
                    self._apply_track_view()
                self.play_track(next_track["path"])
                return
            if self.current_queue:
                current = self.current_track_path
                if not current:
                    self.play_track(self.current_queue[0]["path"], push_history=False)
                    return
                idx = next((i for i, t in enumerate(self.current_queue) if t["path"] == current), -1)
                if idx != -1 and idx + 1 < len(self.current_queue):
                    self.play_track(self.current_queue[idx + 1]["path"])
                else:
                    self.stop_playback()
            return

        if direction == -1:
            if self.play_history:
                previous = self.play_history.pop()
                self.play_track(previous, push_history=False)
                return
            if not self.current_queue:
                return
            current = self.current_track_path or self._get_selected_track_path()
            if not current:
                return
            idx = next((i for i, t in enumerate(self.current_queue) if t["path"] == current), -1)
            if idx == -1:
                return
            prev_idx = (idx - 1) % len(self.current_queue)
            prev_track = self.current_queue[prev_idx]
            if not self.is_shuffle:
                self.user_queue = self.current_queue[prev_idx + 1:]
            self.play_track(prev_track["path"])
            if self.current_view == "queue":
                self._apply_track_view()

    # ------------------------------------------------------------------
    # Callbacks do player GStreamer
    # ------------------------------------------------------------------

    def on_tag_found(self, bus, message) -> None:
        try:
            taglist = message.parse_tag()
        except Exception:
            return

        def get_string_tag(tag):
            try:
                ret, val = taglist.get_string(tag)
                return val if ret else None
            except Exception:
                return None

        title = get_string_tag(Gst.TAG_TITLE)
        artist = get_string_tag(Gst.TAG_ARTIST)
        album = get_string_tag(Gst.TAG_ALBUM)
        updated = False

        if title:
            self.current_title = title
            updated = True
        if artist:
            self.current_artist = artist
            updated = True
        if album:
            self.current_album = album
            updated = True

        if updated:
            GLib.idle_add(self._update_now_playing_ui)
            GLib.idle_add(self.mpris.notify_metadata)

        try:
            if hasattr(taglist, "get_sample"):
                success, sample = taglist.get_sample(Gst.TAG_IMAGE)
                if success and sample:
                    buffer = sample.get_buffer()
                    suc, map_info = buffer.map(Gst.MapFlags.READ)
                    if suc:
                        loader = GdkPixbuf.PixbufLoader()
                        loader.write(map_info.data)
                        loader.close()
                        pixbuf = loader.get_pixbuf()
                        if pixbuf:
                            scaled = pixbuf.scale_simple(60, 60, GdkPixbuf.InterpType.BILINEAR)
                            if scaled:
                                GLib.idle_add(self.cover_image.set_from_pixbuf, scaled)
                        buffer.unmap(map_info)
        except Exception:
            pass

    def on_eos(self, bus, message) -> None:
        self.on_next_clicked(None)

    def on_error(self, bus, message) -> None:
        self._player.stop()
        self.current_track_path = None
        self.progress_bar.set_fraction(0.0)
        self.time_current.set_text("00:00")
        self._update_play_pause_icon()
        self._set_default_cover()
        self.mpris.notify_status()

    # ------------------------------------------------------------------
    # Callbacks de controles
    # ------------------------------------------------------------------

    def on_play_clicked(self, widget) -> None:
        if not self.current_track_path:
            path = self._get_selected_track_path()
            if path:
                self._prepare_next_queue_from_selected(path)
                self.play_track(path)
            return
        self._player.pause_or_resume()
        self._update_play_pause_icon()
        self.mpris.notify_status()

    def on_shuffle_clicked(self, widget) -> None:
        self.is_shuffle = not self.is_shuffle
        ctx = self.btn_shuffle.get_style_context()
        if self.is_shuffle:
            ctx.remove_class("unstarred")
            ctx.add_class("starred")
            random.shuffle(self.user_queue)
        else:
            ctx.remove_class("starred")
            ctx.add_class("unstarred")
            if self.current_track_path and self.current_queue:
                idx = next((i for i, t in enumerate(self.current_queue) if t["path"] == self.current_track_path), -1)
                if idx != -1:
                    self.user_queue = self.current_queue[idx + 1:]
        if self.current_view == "queue":
            self._apply_track_view()

    def on_prev_clicked(self, widget) -> None:
        self._shift_track(-1)

    def on_next_clicked(self, widget) -> None:
        self._shift_track(1)

    def on_search_changed(self, widget) -> None:
        self._apply_track_view()

    def on_track_selected(self, listbox, row) -> None:
        if row and hasattr(row, "track_path"):
            self.selected_track_path = row.track_path
        else:
            self.selected_track_path = None
        self._update_now_playing_ui()

    def on_track_activated(self, listbox, row) -> None:
        if row and hasattr(row, "track_path"):
            path = row.track_path
            self._prepare_next_queue_from_selected(path)
            self.play_track(path)

    def on_toggle_favorite_clicked(self, widget) -> None:
        path = self._get_selected_track_path()
        if path:
            self.toggle_favorite(path)

    def on_add_to_playlist_clicked(self, widget) -> None:
        path = self._get_selected_track_path()
        if not path:
            return
        dialog = PlaylistDialog(self, sorted(self.playlists.keys(), key=str.lower))
        if dialog.run() == Gtk.ResponseType.OK:
            name = dialog.get_choice()
            if name:
                self.playlists.setdefault(name, [])
                if path not in self.playlists[name]:
                    self.playlists[name].append(path)
                    self._save_state()
                    self._refresh_sidebar()
        dialog.destroy()

    def on_choose_folder_clicked(self, widget) -> None:
        dialog = Gtk.FileChooserDialog("Selecione a pasta", self, Gtk.FileChooserAction.SELECT_FOLDER)
        dialog.add_buttons("Cancelar", Gtk.ResponseType.CANCEL, "Selecionar", Gtk.ResponseType.OK)
        if self.library_folder:
            dialog.set_filename(self.library_folder)
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            folder = dialog.get_filename()
            if folder:
                self._scan_library(folder)
                self._set_view("library")
        dialog.destroy()

    def on_refresh_clicked(self, widget) -> None:
        if self.library_folder:
            self._scan_library(self.library_folder)

    def on_about_clicked(self, widget) -> None:
        show_about_dialog(self)

    def on_artist_filter_changed(self, widget) -> None:
        self._refresh_artist_browser()

    def on_artist_tracks_clicked(self, widget) -> None:
        if self.current_artist_name:
            self.current_album_key = None
            self._syncing_sidebar_selection = True
            try:
                self.album_selector.set_active(0)
            finally:
                self._syncing_sidebar_selection = False
            self._set_view("artist", artist_name=self.current_artist_name)

    def on_album_selector_changed(self, widget) -> None:
        if self._syncing_sidebar_selection or not self.current_artist_name:
            return
        active = self.album_selector.get_active()
        if active <= 0:
            self.current_album_key = None
        else:
            album_name = self.album_selector.get_active_text()
            self.current_album_key = (album_name, self.current_artist_name)
        self._apply_track_view()

    def on_album_card_clicked(self, button, album_name: str, album_artist: str) -> None:
        self._set_view("album", artist_name=album_artist, album_key=(album_name, album_artist))

    def on_sidebar_selected(self, listbox, row) -> None:
        if self._syncing_sidebar_selection:
            return
        if not row or not hasattr(row, "kind"):
            return

        self._syncing_sidebar_selection = True
        try:
            if listbox == self.nav_listbox:
                self.playlist_listbox.unselect_all()
                if hasattr(self, "artists_listbox"):
                    self.artists_listbox.unselect_all()
                if row.kind == "library":
                    self._set_view("library")
                elif row.kind == "favorites":
                    self._set_view("favorites")
                elif row.kind == "queue":
                    self._set_view("queue")
                return

            if listbox == self.artists_listbox:
                self.nav_listbox.unselect_all()
                self.playlist_listbox.unselect_all()
                artist_name = getattr(row, "artist_name", None)
                if artist_name:
                    self._set_view("artist", artist_name=artist_name)
                return

            if listbox == self.playlist_listbox:
                self.nav_listbox.unselect_all()
                if hasattr(self, "artists_listbox"):
                    self.artists_listbox.unselect_all()
                self._set_view("playlist", playlist_name=getattr(row, "playlist_name", None))
                return
        finally:
            self._syncing_sidebar_selection = False

    def on_sidebar_button_press(self, listbox, event) -> bool:
        if event.button == 3:
            row = listbox.get_row_at_y(int(event.y))
            if row and hasattr(row, "playlist_name"):
                listbox.select_row(row)
                menu = Gtk.Menu()
                item_rename = Gtk.MenuItem(label="Renomear playlist")
                item_rename.connect("activate", lambda *_: self.rename_playlist(row.playlist_name))
                menu.append(item_rename)
                item_delete = Gtk.MenuItem(label="Excluir playlist")
                item_delete.connect("activate", lambda *_: self.delete_playlist(row.playlist_name))
                menu.append(item_delete)
                menu.show_all()
                menu.popup_at_pointer(event)
                return True
        return False

    def on_track_button_press(self, listbox, event) -> bool:
        if event.button == 3:
            row = listbox.get_row_at_y(int(event.y))
            if row and hasattr(row, "track_path"):
                listbox.select_row(row)
                menu = Gtk.Menu()

                item_queue = Gtk.MenuItem(label="Adicionar à fila")
                item_queue.connect("activate", lambda *_: self.add_to_queue(row.track_path))
                menu.append(item_queue)

                item_fav = Gtk.MenuItem(
                    label="Remover dos favoritos" if row.track_path in self.favorites else "Adicionar aos favoritos"
                )
                item_fav.connect("activate", lambda *_: self.toggle_favorite(row.track_path))
                menu.append(item_fav)

                if self.current_view == "playlist":
                    item_remove = Gtk.MenuItem(label="Remover desta playlist")
                    item_remove.connect("activate", lambda *_: self.remove_from_current_playlist(row.track_path))
                    menu.append(item_remove)

                if self.current_view == "queue":
                    item_rm_queue = Gtk.MenuItem(label="Remover da fila")
                    item_rm_queue.connect("activate", lambda *_: self.remove_from_queue(row.track_path))
                    menu.append(item_rm_queue)

                menu.show_all()
                menu.popup_at_pointer(event)
                return True
        return False

    def on_new_playlist_clicked(self, widget) -> None:
        dialog = Gtk.Dialog(title="Nova playlist", transient_for=self, flags=0)
        dialog.add_buttons("Cancelar", Gtk.ResponseType.CANCEL, "Criar", Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        box.set_border_width(18)

        entry = Gtk.Entry()
        entry.set_placeholder_text("Nome da playlist")
        box.pack_start(entry, True, True, 0)
        dialog.show_all()

        if dialog.run() == Gtk.ResponseType.OK:
            name = entry.get_text().strip()
            if name and name not in self.playlists:
                self.playlists[name] = []
                self._save_state()
                self._refresh_sidebar()
        dialog.destroy()

    # ------------------------------------------------------------------
    # Ações sobre faixas e playlists
    # ------------------------------------------------------------------

    def toggle_favorite(self, path: str) -> None:
        if path in self.favorites:
            self.favorites.discard(path)
        else:
            self.favorites.add(path)
        self._save_state()
        self._refresh_sidebar()
        self._apply_track_view()
        self._update_now_playing_ui()

    def add_to_queue(self, track_path: str) -> None:
        track = self.track_by_path.get(track_path) or read_audio_metadata(track_path)
        self.user_queue.append(track)
        if self.current_view == "queue":
            self._apply_track_view()

    def remove_from_queue(self, track_path: str) -> None:
        self.user_queue = [t for t in self.user_queue if t["path"] != track_path]
        if self.current_view == "queue":
            self._apply_track_view()

    def remove_from_current_playlist(self, track_path: str) -> None:
        if self.current_view == "playlist" and self.current_playlist_name:
            name = self.current_playlist_name
            if name in self.playlists and track_path in self.playlists[name]:
                self.playlists[name].remove(track_path)
                self._save_state()
                self._refresh_sidebar()
                self._apply_track_view()

    def rename_playlist(self, old_name: str) -> None:
        dialog = Gtk.Dialog(title="Renomear playlist", transient_for=self, flags=0)
        dialog.add_buttons("Cancelar", Gtk.ResponseType.CANCEL, "Salvar", Gtk.ResponseType.OK)
        box = dialog.get_content_area()
        box.set_border_width(18)

        entry = Gtk.Entry()
        entry.set_text(old_name)
        box.pack_start(entry, True, True, 0)
        dialog.show_all()

        if dialog.run() == Gtk.ResponseType.OK:
            new_name = entry.get_text().strip()
            if new_name and new_name != old_name and new_name not in self.playlists:
                self.playlists[new_name] = self.playlists.pop(old_name, [])
                self._save_state()
                self._refresh_sidebar()
                if self.current_view == "playlist" and self.current_playlist_name == old_name:
                    self._set_view("playlist", playlist_name=new_name)
        dialog.destroy()

    def delete_playlist(self, name: str) -> None:
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f"Excluir a playlist '{name}'?",
        )
        if dialog.run() == Gtk.ResponseType.YES:
            self.playlists.pop(name, None)
            self._save_state()
            self._refresh_sidebar()
            if self.current_view == "playlist" and self.current_playlist_name == name:
                self._set_view("library")
        dialog.destroy()

    # ------------------------------------------------------------------
    # Atualização
    # ------------------------------------------------------------------

    def _on_update_available(self, tag: str, download_url: str) -> bool:
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f"Nova versão disponível: {tag}",
        )
        dialog.format_secondary_text(
            f"Você está usando a versão {APP_VERSION}.\n"
            "Deseja baixar e instalar a atualização agora?\n"
            "O aplicativo será reiniciado automaticamente."
        )
        response = dialog.run()
        dialog.destroy()

        if response == Gtk.ResponseType.YES:
            download_and_restart(self, tag, download_url)

        return False