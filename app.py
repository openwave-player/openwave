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
from mutagen import File as MutagenFile


AUDIO_EXTENSIONS = {
    ".mp3",
    ".wav",
    ".ogg",
    ".flac",
    ".m4a",
    ".aac",
    ".opus",
    ".wma",
    ".aiff",
    ".aif",
    ".alac",
    ".mp2",
    ".mka",
}


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def normalize_text(value: object, fallback: str) -> str:
    if value is None:
        return fallback
    if isinstance(value, (list, tuple)):
        if not value:
            return fallback
        value = value[0]
    if isinstance(value, bytes):
        value = value.decode("utf-8", "ignore")
    text = str(value).strip()
    return text or fallback


def pretty_album_name(album: str, artist: str) -> str:
    album = album.strip() or "Álbum desconhecido"
    artist = artist.strip() or "Artista desconhecido"
    if album.lower() == artist.lower():
        return album
    return album


def read_audio_metadata(path: str) -> dict:
    file_path = Path(path)
    title = file_path.stem or "Faixa sem nome"
    artist = "Artista desconhecido"
    album = "Álbum desconhecido"
    duration = 0.0
    cover_data = None

    try:
        easy_file = MutagenFile(path, easy=True)
        if easy_file:
            title = normalize_text(easy_file.get("title"), title)
            artist = normalize_text(easy_file.get("artist"), artist)
            album = normalize_text(easy_file.get("album"), album)

        full_file = MutagenFile(path)
        if full_file is not None:
            info = getattr(full_file, "info", None)
            if info is not None:
                duration = float(getattr(info, "length", 0.0) or 0.0)

            tags = getattr(full_file, "tags", None)
            if tags:
                pictures = []
                getall = getattr(tags, "getall", None)
                if callable(getall):
                    try:
                        pictures = getall("APIC")
                    except Exception:
                        pictures = []

                if pictures:
                    cover_data = getattr(pictures[0], "data", None)

                if cover_data is None and hasattr(tags, "pictures"):
                    pics = getattr(tags, "pictures", [])
                    if pics:
                        cover_data = getattr(pics[0], "data", None)

                if cover_data is None:
                    covr = tags.get("covr")
                    if covr:
                        try:
                            cover_data = bytes(covr[0])
                        except Exception:
                            pass
    except Exception:
        pass

    return {
        "path": str(file_path),
        "title": title,
        "artist": artist,
        "album": pretty_album_name(album, artist),
        "duration": duration,
        "cover_data": cover_data,
    }


class PlaylistDialog(Gtk.Dialog):
    def __init__(self, parent, playlists: list[str]):
        super().__init__(title="Adicionar à playlist", transient_for=parent, flags=0)
        self.set_modal(True)
        self.add_buttons("Cancelar", Gtk.ResponseType.CANCEL, "Adicionar", Gtk.ResponseType.OK)
        self.set_default_size(380, 160)

        content = self.get_content_area()
        content.set_border_width(18)
        content.set_spacing(12)

        info = Gtk.Label(label="Escolha uma playlist existente ou crie uma nova.")
        info.set_line_wrap(True)
        info.set_halign(Gtk.Align.START)
        content.pack_start(info, False, False, 0)

        grid = Gtk.Grid(column_spacing=12, row_spacing=12)
        content.pack_start(grid, False, False, 0)

        lbl_existing = Gtk.Label(label="Playlist:")
        lbl_existing.set_halign(Gtk.Align.START)
        grid.attach(lbl_existing, 0, 0, 1, 1)

        self.combo = Gtk.ComboBoxText()
        self.combo.append_text("Nova playlist...")
        for name in playlists:
            self.combo.append_text(name)
        self.combo.set_active(0)
        grid.attach(self.combo, 1, 0, 1, 1)

        lbl_new = Gtk.Label(label="Nome:")
        lbl_new.set_halign(Gtk.Align.START)
        grid.attach(lbl_new, 0, 1, 1, 1)

        self.entry = Gtk.Entry()
        self.entry.set_placeholder_text("Ex.: Chill, Estudos")
        grid.attach(self.entry, 1, 1, 1, 1)

        self.show_all()

    def get_choice(self):
        active = self.combo.get_active_text()
        new_name = self.entry.get_text().strip()
        if active == "Nova playlist...":
            return new_name or None
        return active


class OpenWave(Gtk.Window):
    def __init__(self):
        super().__init__(title="OpenWave")
        self.set_default_size(1180, 760)
        self.set_resizable(True)

        self.base_dir = Path(GLib.get_user_config_dir()) / "openwave"
        ensure_dir(self.base_dir)
        self.config_file = self.base_dir / "state.json"

        self.library_folder: str | None = None
        self.library_tracks: list[dict] = []
        self.track_by_path: dict[str, dict] = {}
        self.artist_index: dict[str, list[dict]] = {}
        self.album_index: dict[tuple[str, str], list[dict]] = {}

        self.favorites: set[str] = set()
        self.playlists: dict[str, list[str]] = {}

        self.current_view = "library"
        self.current_playlist_name: str | None = None
        self.current_artist_name: str | None = None
        self.current_album_key: tuple[str, str] | None = None
        self._syncing_sidebar_selection = False

        self.current_queue: list[dict] = []
        self.user_queue: list[dict] = []
        self.play_history: list[str] = []

        self.selected_track_path: str | None = None
        self.current_track_path: str | None = None
        self.is_playing = False
        self.is_shuffle = False
        self.timer_id = None
        self.current_duration = 0.0

        self.current_title = "Nenhuma faixa"
        self.current_artist = "OpenWave"
        self.current_album = ""

        self._load_state()
        self._setup_css()
        self._setup_header()
        self._init_gstreamer()
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
        self.empty_label.set_visible(True)

    def _on_destroy(self, *args):
        try:
            self.player.set_state(Gst.State.NULL)
        except Exception:
            pass
        self._save_state()

    def _init_gstreamer(self):
        Gst.init(None)
        self.player = Gst.ElementFactory.make("playbin", "player")
        if not self.player:
            raise RuntimeError("Não foi possível iniciar o GStreamer playbin.")
        bus = self.player.get_bus()
        bus.add_signal_watch()
        bus.connect("message::tag", self.on_tag_found)
        bus.connect("message::eos", self.on_eos)
        bus.connect("message::error", self.on_error)

    def _build_ui(self):
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

        bottom_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
        bottom_bar.get_style_context().add_class("bottom-bar")
        bottom_bar.set_border_width(12)
        root.pack_end(bottom_bar, False, False, 0)

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

    def _sidebar_section(self, title: str, with_add_button: bool = False):
        section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        section.set_border_width(12)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        header.set_hexpand(True)

        label = Gtk.Label(label=title)
        label.set_halign(Gtk.Align.START)
        label.set_xalign(0.0)
        label.get_style_context().add_class("title-2")
        header.pack_start(label, True, True, 0)

        add_button = None
        if with_add_button:
            add_button = Gtk.Button.new_from_icon_name("list-add-symbolic", Gtk.IconSize.MENU)
            add_button.get_style_context().add_class("control-btn-flat")
            header.pack_end(add_button, False, False, 0)

        section.pack_start(header, False, False, 0)

        listbox = Gtk.ListBox()
        listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        listbox.set_activate_on_single_click(True)
        listbox.get_style_context().add_class("track-list")
        section.pack_start(listbox, False, False, 0)

        return section, listbox, add_button


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

        nav_section, self.nav_listbox, _ = self._sidebar_section("Navegação")
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

        playlist_section, self.playlist_listbox, playlist_add_btn = self._sidebar_section("Playlists", with_add_button=True)
        self.playlist_listbox.connect("row-selected", self.on_sidebar_selected)
        self.playlist_listbox.connect("button-press-event", self.on_sidebar_button_press)
        if playlist_add_btn:
            playlist_add_btn.connect("clicked", self.on_new_playlist_clicked)
        sidebar_content.pack_start(playlist_section, False, False, 0)

        wrapper.pack_start(sidebar_scroll, True, True, 0)
        return wrapper

    def _setup_css(self) -> None:
        css = """
        .main-background { background-color: @theme_bg_color; }
        .sidebar { background-color: shade(@theme_bg_color, 0.96); border-right: 1px solid alpha(@theme_fg_color, 0.08); }
        .content-area { background-color: @theme_bg_color; }
        .bottom-bar { background-color: shade(@theme_bg_color, 0.92); border-top: 1px solid alpha(@theme_fg_color, 0.1); padding: 8px 16px; }

        .muted { opacity: 0.65; }
        .muted-small { opacity: 0.65; font-size: 11px; }
        .title-1 { font-size: 26px; font-weight: 800; letter-spacing: -0.5px; }
        .title-2 { font-size: 13px; font-weight: 700; opacity: 0.55; }

        .section-note { opacity: 0.52; font-size: 11px; }
        .search-field { margin: 0 10px 6px 10px; }
        .search-field entry { border-radius: 999px; }

        .empty-state { opacity: 0.55; font-size: 15px; }
        .album-browser-empty { opacity: 0.48; font-size: 13px; }

        .cover-frame-small { border-radius: 10px; border: 1px solid alpha(@theme_fg_color, 0.1); }
        .album-browser { padding: 8px 18px 0 18px; }
        .album-select { min-height: 34px; border-radius: 999px; }
        .track-title-bold { font-weight: 700; font-size: 14px; }

        .sidebar-row { padding: 10px 14px; border-radius: 10px; margin: 2px 10px; font-weight: 600; }
        .sidebar-row:hover { background-color: alpha(@theme_fg_color, 0.05); }
        .sidebar-row:selected { background-color: alpha(@theme_selected_bg_color, 0.15); color: @theme_selected_bg_color; }

        .track-list { background: transparent; }
        .track-row { padding: 12px 16px; border-bottom: 1px solid alpha(@theme_fg_color, 0.03); }
        .track-row:hover { background-color: alpha(@theme_fg_color, 0.04); }
        .track-row:selected { background-color: alpha(@theme_selected_bg_color, 0.1); }
        .playing-row { background-color: alpha(@theme_selected_bg_color, 0.12); border-left: 4px solid @theme_selected_bg_color; }

        .control-btn-flat { background: transparent; border: none; box-shadow: none; padding: 8px; border-radius: 999px; }
        .control-btn-flat:hover { background: alpha(@theme_fg_color, 0.1); }
        .control-btn-flat.unstarred { opacity: 0.45; }
        .control-btn-flat.starred { opacity: 1.0; color: @theme_selected_bg_color; }
        .control-btn-main { border-radius: 999px; padding: 12px; background-color: @theme_selected_bg_color; color: @theme_selected_fg_color; border: none; }
        .control-btn-main:hover { background-color: shade(@theme_selected_bg_color, 1.08); }

        progressbar trough { min-height: 4px; border-radius: 2px; }
        progressbar progress { min-height: 4px; border-radius: 2px; background-color: @theme_selected_bg_color; }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode("utf-8"))
        screen = Gdk.Screen.get_default()
        if screen:
            Gtk.StyleContext.add_provider_for_screen(
                screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )

    def _setup_header(self) -> None:
        self.header = Gtk.HeaderBar()
        self.header.set_show_close_button(True)
        self.header.set_title("OpenWave")
        self.set_titlebar(self.header)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)

        self.btn_choose_folder = Gtk.Button.new_from_icon_name("folder-open-symbolic", Gtk.IconSize.BUTTON)
        self.btn_choose_folder.set_tooltip_text("Abrir pasta da biblioteca")
        self.btn_choose_folder.connect("clicked", self.on_choose_folder_clicked)
        btn_box.pack_start(self.btn_choose_folder, False, False, 0)

        self.btn_refresh = Gtk.Button.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.BUTTON)
        self.btn_refresh.set_tooltip_text("Reescanear biblioteca")
        self.btn_refresh.connect("clicked", self.on_refresh_clicked)
        btn_box.pack_start(self.btn_refresh, False, False, 0)

        self.header.pack_start(btn_box)

        self.btn_about = Gtk.Button.new_from_icon_name("help-about-symbolic", Gtk.IconSize.BUTTON)
        self.btn_about.set_tooltip_text("Sobre")
        self.btn_about.connect("clicked", self.on_about_clicked)
        self.header.pack_end(self.btn_about)

    def on_artist_filter_changed(self, widget) -> None:
        self._refresh_artist_browser()

    def on_artist_tracks_clicked(self, widget) -> None:
        if self.current_artist_name:
            self.current_album_key = None
            if hasattr(self, "album_selector"):
                self._syncing_sidebar_selection = True
                try:
                    self.album_selector.set_active(0)
                finally:
                    self._syncing_sidebar_selection = False
            self._set_view("artist", artist_name=self.current_artist_name)

    def on_album_selector_changed(self, widget) -> None:
        if self._syncing_sidebar_selection or not self.current_artist_name:
            return
        if not hasattr(self, "album_selector"):
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

    def _set_default_cover(self) -> None:
        theme = Gtk.IconTheme.get_default()
        try:
            pixbuf = theme.load_icon("audio-x-generic-symbolic", 60, 0)
            self.cover_image.set_from_pixbuf(pixbuf)
        except Exception:
            self.cover_image.set_from_icon_name("audio-x-generic", Gtk.IconSize.DND)

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

    def _update_header_subtitle(self) -> None:
        if self.library_folder:
            self.header.set_subtitle(
                f"{Path(self.library_folder).name} • {len(self.library_tracks)} faixas"
            )
        else:
            self.header.set_subtitle("Nenhuma pasta selecionada")


    def _clear_listbox(self, listbox: Gtk.ListBox) -> None:
        for child in listbox.get_children():
            listbox.remove(child)

    def _refresh_sidebar(self) -> None:
        if not hasattr(self, "nav_listbox"):
            return

        self._clear_listbox(self.nav_listbox)
        self._clear_listbox(self.playlist_listbox)
        self._refresh_artist_browser()

        self._add_sidebar_row(self.nav_listbox, "Biblioteca", "library", "folder-music-symbolic")
        self._add_sidebar_row(self.nav_listbox, "Favoritos", "favorites", "emblem-favorite-symbolic")
        self._add_sidebar_row(
            self.nav_listbox,
            "Fila de reprodução",
            "queue",
            "media-playlist-consecutive-symbolic",
        )

        for name in sorted(self.playlists.keys(), key=str.lower):
            tracks = self.playlists.get(name, [])
            subtitle = f"{len(tracks)} faixa{'s' if len(tracks) != 1 else ''}"
            self._add_sidebar_row(
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
            self._add_sidebar_row(
                self.artists_listbox,
                artist_name,
                "artist",
                "avatar-default-symbolic",
                subtitle=f"{len(album_keys)} álbum{'s' if len(album_keys) != 1 else ''} • {len(tracks)} faixa{'s' if len(tracks) != 1 else ''}",
                artist_name=artist_name,
            )

        if not visible_artists:
            self._add_sidebar_row(
                self.artists_listbox,
                "Nenhum artista encontrado",
                "info",
                "avatar-default-symbolic",
                subtitle="Tente outra busca ou carregue músicas com metadados.",
            )

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

        if hasattr(self, "album_selector"):
            self.album_selector.handler_block_by_func(self.on_album_selector_changed)
            try:
                self.album_selector.remove_all()
            except Exception:
                pass
            self.album_selector.append_text("Todos os álbuns")
        else:
            self.album_selector = None

        if not artist_name or artist_name not in self.artist_index:
            self.album_browser_label.set_text("Artista")
            self.album_browser_subtitle.set_text("Selecione um artista para ver os álbuns.")
            self.album_count_label.set_text("")
            self.album_empty_label.set_text("Selecione um artista para ver os álbuns.")
            if hasattr(self, "album_selector"):
                try:
                    self.album_selector.set_active(0)
                except Exception:
                    pass
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

        if hasattr(self, "album_selector"):
            current_album_name = None
            if self.current_album_key and self.current_album_key[1] == artist_name:
                current_album_name = self.current_album_key[0]
            for album_name, album_artist in album_keys:
                self.album_selector.append_text(album_name or "Álbum sem nome")
                album_tracks = self.album_index.get((album_name, album_artist), [])
                active = current_album_name == album_name
                child = self._build_album_card(album_name, album_artist, album_tracks, active=active)
                self.album_flowbox.add(child)
            try:
                if current_album_name is None:
                    self.album_selector.set_active(0)
                else:
                    for idx, (album_name, _album_artist) in enumerate(album_keys, start=1):
                        if album_name == current_album_name:
                            self.album_selector.set_active(idx)
                            break
                    else:
                        self.album_selector.set_active(0)
            finally:
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
        button._album_name = album_name
        button._album_artist = album_artist
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

    def _build_artist_tree_model(self) -> Gtk.TreeStore:
        store = Gtk.TreeStore(str, str, str, str, str, str, str)
        if not self.artist_index:
            return store

        for artist, artist_tracks in sorted(self.artist_index.items(), key=lambda item: item[0].lower()):
            artist_tracks_sorted = sorted(
                artist_tracks,
                key=lambda track: (
                    track.get("album", "").lower(),
                    track.get("title", "").lower(),
                ),
            )
            albums: dict[tuple[str, str], list[dict]] = defaultdict(list)
            for track in artist_tracks_sorted:
                albums[(track["album"], track["artist"])].append(track)

            artist_markup = self._sidebar_markup(
                artist,
                f"{len(albums)} álbum{'s' if len(albums) != 1 else ''} • {len(artist_tracks_sorted)} faixa{'s' if len(artist_tracks_sorted) != 1 else ''}",
                bold=True,
            )
            artist_iter = store.append(None, [artist_markup, "artist", "avatar-default-symbolic", artist, "", "", ""])

            for (album, album_artist), album_tracks in sorted(
                albums.items(), key=lambda item: (item[0][0].lower(), item[0][1].lower())
            ):
                album_sorted = sorted(album_tracks, key=lambda track: track.get("title", "").lower())
                album_markup = self._sidebar_markup(
                    album,
                    f"{album_artist} • {len(album_sorted)} faixa{'s' if len(album_sorted) != 1 else ''}",
                    bold=True,
                )
                album_iter = store.append(artist_iter, [album_markup, "album", "media-optical-symbolic", artist, album, album_artist, ""])

                for track in album_sorted:
                    duration = track.get("duration") or 0.0
                    duration_text = self.format_time_from_seconds(duration) if duration > 0 else ""
                    track_subtitle = f"{track['artist']}"
                    if track.get("album"):
                        track_subtitle = f"{track_subtitle} • {track['album']}"
                    if duration_text:
                        track_subtitle = f"{track_subtitle} • {duration_text}"
                    track_markup = self._sidebar_markup(track["title"], track_subtitle, bold=False)
                    store.append(album_iter, [track_markup, "track", "audio-x-generic-symbolic", track["artist"], track["album"], track["artist"], track["path"]])

        return store

    def _sidebar_markup(self, title: str, subtitle: str = "", bold: bool = True) -> str:
        from xml.sax.saxutils import escape

        title_text = escape(title)
        subtitle_text = escape(subtitle)
        if bold:
            if subtitle_text:
                return f"<b>{title_text}</b>\n<small>{subtitle_text}</small>"
            return f"<b>{title_text}</b>"
        if subtitle_text:
            return f"{title_text}\n<small>{subtitle_text}</small>"
        return title_text

    def _sidebar_tree_section(self, title: str):
        section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        section.set_border_width(12)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        header.set_hexpand(True)

        label = Gtk.Label(label=title)
        label.set_halign(Gtk.Align.START)
        label.set_xalign(0.0)
        label.get_style_context().add_class("title-2")
        header.pack_start(label, True, True, 0)

        section.pack_start(header, False, False, 0)

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.set_shadow_type(Gtk.ShadowType.NONE)
        scroll.set_hexpand(True)
        scroll.set_vexpand(False)
        scroll.set_min_content_height(240)

        tree = Gtk.TreeView()
        tree.set_headers_visible(False)
        tree.set_enable_tree_lines(True)
        tree.get_style_context().add_class("track-list")
        tree.get_selection().set_mode(Gtk.SelectionMode.SINGLE)
        tree.get_selection().connect("changed", self.on_artists_tree_selection_changed)

        icon_renderer = Gtk.CellRendererPixbuf()
        text_renderer = Gtk.CellRendererText()
        text_renderer.set_property("wrap-mode", Pango.WrapMode.WORD_CHAR)
        text_renderer.set_property("wrap-width", 220)
        text_renderer.set_property("ellipsize", Pango.EllipsizeMode.END)

        column = Gtk.TreeViewColumn()
        column.pack_start(icon_renderer, False)
        column.pack_start(text_renderer, True)
        column.add_attribute(icon_renderer, "icon-name", 2)
        column.add_attribute(text_renderer, "markup", 0)
        tree.append_column(column)

        scroll.add(tree)
        section.pack_start(scroll, False, False, 0)

        return section, tree

    def _add_sidebar_row(
        self,
        listbox,
        title: str,
        kind: str,
        icon_name: str,
        subtitle: str | None = None,
        playlist_name: str | None = None,
        artist_name: str | None = None,
        album_name: str | None = None,
        album_artist: str | None = None,
    ) -> None:
        row = Gtk.ListBoxRow()
        row.kind = kind
        row.playlist_name = playlist_name
        row.artist_name = artist_name
        row.album_name = album_name
        row.album_artist = album_artist
        row.get_style_context().add_class("sidebar-row")

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        icon = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.MENU)
        box.pack_start(icon, False, False, 0)

        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        label = Gtk.Label(label=title)
        label.set_halign(Gtk.Align.START)
        label.set_xalign(0.0)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        text_box.pack_start(label, False, False, 0)

        if subtitle:
            sub = Gtk.Label(label=subtitle)
            sub.set_halign(Gtk.Align.START)
            sub.set_xalign(0.0)
            sub.set_ellipsize(Pango.EllipsizeMode.END)
            sub.get_style_context().add_class("muted-small")
            text_box.pack_start(sub, False, False, 0)

        box.pack_start(text_box, True, True, 0)
        row.add(box)
        listbox.add(row)

    def _track_matches_search(self, track: dict, query: str) -> bool:
        if not query:
            return True
        query = query.lower()
        blob = " ".join(
            [
                track.get("title", ""),
                track.get("artist", ""),
                track.get("album", ""),
                track.get("path", ""),
            ]
        ).lower()
        return query in blob

    def _resolve_playlist_tracks(self, name: str) -> list[dict]:
        tracks: list[dict] = []
        for path in self.playlists.get(name, []):
            if path in self.track_by_path:
                tracks.append(self.track_by_path[path])
            elif Path(path).exists():
                tracks.append(read_audio_metadata(path))
        return tracks

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
                album, _artist = self.current_album_key
                return f"Artista: {self.current_artist_name} • {album}"
            return f"Artista: {self.current_artist_name}"
        return "Biblioteca"

    def _view_tracks(self) -> list[dict]:
        if self.current_view == "library":
            return self.library_tracks[:]
        if self.current_view == "favorites":
            return [track for track in self.library_tracks if track["path"] in self.favorites]
        if self.current_view == "queue":
            return self.user_queue[:]
        if self.current_view == "playlist" and self.current_playlist_name:
            return self._resolve_playlist_tracks(self.current_playlist_name)
        if self.current_view in {"artist", "album"} and self.current_artist_name:
            if self.current_album_key:
                return self.album_index.get(self.current_album_key, [])[:]
            return self.artist_index.get(self.current_artist_name, [])[:]
        return self.library_tracks[:]

    def _apply_track_view(self) -> None:
        query = self.search_entry.get_text().strip()

        tracks = [track for track in self._view_tracks() if self._track_matches_search(track, query)]

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

        if self.current_view in {"artist", "album"} and self.current_artist_name:
            self._refresh_album_browser(self.current_artist_name)

        if not has_tracks and not self.current_track_path:
            self.btn_favorite_dock.set_sensitive(False)
            self.btn_add_playlist.set_sensitive(False)

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

            title = Gtk.Label(label=item["title"])
            title.set_halign(Gtk.Align.START)
            title.set_xalign(0.0)
            title.set_ellipsize(Pango.EllipsizeMode.END)
            title.get_style_context().add_class("track-title-bold")
            vbox.pack_start(title, False, False, 0)

            subtitle_text = f'{item["artist"]} • {item["album"]}'
            subtitle = Gtk.Label(label=subtitle_text)
            subtitle.set_halign(Gtk.Align.START)
            subtitle.set_xalign(0.0)
            subtitle.set_ellipsize(Pango.EllipsizeMode.END)
            subtitle.get_style_context().add_class("muted-small")
            vbox.pack_start(subtitle, False, False, 0)

            box.pack_start(vbox, True, True, 0)

            duration = item.get("duration") or 0.0
            if duration > 0:
                duration_label = Gtk.Label(label=self.format_time_from_seconds(duration))
                duration_label.get_style_context().add_class("muted-small")
                box.pack_end(duration_label, False, False, 0)

            if item["path"] in self.favorites:
                fav = Gtk.Image.new_from_icon_name("emblem-favorite-symbolic", Gtk.IconSize.MENU)
                box.pack_end(fav, False, False, 0)

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
        icon = "media-playback-pause-symbolic" if self.is_playing else "media-playback-start-symbolic"
        self.btn_play.set_image(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.LARGE_TOOLBAR))

    def _set_view(self, view: str, playlist_name: str | None = None, artist_name: str | None = None, album_key: tuple[str, str] | None = None) -> None:
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

    def _select_row_by_kind(self, listbox, kind: str) -> None:
        for row in listbox.get_children():
            if getattr(row, "kind", None) == kind:
                listbox.select_row(row)
                break

    def _select_row_by_attr(self, listbox, attr: str, value: str) -> None:
        for row in listbox.get_children():
            if getattr(row, attr, None) == value:
                listbox.select_row(row)
                break

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

    def play_track(self, path: str, push_history: bool = True) -> None:
        if not path or not Path(path).exists():
            return

        track = self.track_by_path.get(path) or read_audio_metadata(path)

        if push_history and self.current_track_path and self.current_track_path != path:
            self.play_history.append(self.current_track_path)

        self.player.set_state(Gst.State.NULL)

        if not self._load_cover_from_bytes(track.get("cover_data"), 60):
            self._set_default_cover()

        self.current_title = track["title"]
        self.current_artist = track["artist"]
        self.current_album = track["album"]
        self.current_duration = float(track.get("duration") or 0.0)
        self.current_track_path = path

        self.player.set_property("uri", GLib.filename_to_uri(path, None))
        self._update_now_playing_ui()

        self.progress_bar.set_fraction(0.0)
        self.time_current.set_text("00:00")
        self.time_total.set_text(
            self.format_time_from_seconds(self.current_duration) if self.current_duration > 0 else "00:00"
        )

        self.player.set_state(Gst.State.PLAYING)
        self.is_playing = True
        self._update_play_pause_icon()
        self._update_list_highlight()

        if self.timer_id is None:
            self.timer_id = GLib.timeout_add(1000, self.update_progress)

    def stop_playback(self) -> None:
        self.player.set_state(Gst.State.PAUSED)
        self.is_playing = False
        self._update_play_pause_icon()

    def on_choose_folder_clicked(self, widget) -> None:
        dialog = Gtk.FileChooserDialog(
            "Selecione a pasta",
            self,
            Gtk.FileChooserAction.SELECT_FOLDER,
        )
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
                    item_remove.connect(
                        "activate", lambda *_: self.remove_from_current_playlist(row.track_path)
                    )
                    menu.append(item_remove)

                if self.current_view == "queue":
                    item_rm_queue = Gtk.MenuItem(label="Remover da fila")
                    item_rm_queue.connect("activate", lambda *_: self.remove_from_queue(row.track_path))
                    menu.append(item_rm_queue)

                menu.show_all()
                menu.popup_at_pointer(event)
                return True
        return False

    def add_to_queue(self, track_path: str) -> None:
        track = self.track_by_path.get(track_path)
        if not track:
            track = read_audio_metadata(track_path)
        self.user_queue.append(track)
        if self.current_view == "queue":
            self._apply_track_view()

    def remove_from_queue(self, track_path: str) -> None:
        self.user_queue = [track for track in self.user_queue if track["path"] != track_path]
        if self.current_view == "queue":
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

    def remove_from_current_playlist(self, track_path: str) -> None:
        if self.current_view == "playlist" and self.current_playlist_name:
            name = self.current_playlist_name
            if name in self.playlists and track_path in self.playlists[name]:
                self.playlists[name].remove(track_path)
                self._save_state()
                self._refresh_sidebar()
                self._apply_track_view()

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

    def _prepare_next_queue_from_selected(self, path: str) -> None:
        idx = next((i for i, track in enumerate(self.current_queue) if track["path"] == path), -1)
        if idx == -1:
            return

        if self.is_shuffle:
            remaining = [track for i, track in enumerate(self.current_queue) if i != idx]
            random.shuffle(remaining)
            self.user_queue = remaining
        else:
            self.user_queue = self.current_queue[idx + 1 :]

    def on_play_clicked(self, widget) -> None:
        if not self.current_track_path:
            path = self._get_selected_track_path()
            if path:
                self._prepare_next_queue_from_selected(path)
                self.play_track(path)
            return

        self.player.set_state(Gst.State.PAUSED if self.is_playing else Gst.State.PLAYING)
        self.is_playing = not self.is_playing
        self._update_play_pause_icon()

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
                idx = next(
                    (i for i, track in enumerate(self.current_queue) if track["path"] == self.current_track_path),
                    -1,
                )
                if idx != -1:
                    self.user_queue = self.current_queue[idx + 1 :]

        if self.current_view == "queue":
            self._apply_track_view()

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
                idx = next(
                    (i for i, track in enumerate(self.current_queue) if track["path"] == current),
                    -1,
                )
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

            idx = next((i for i, track in enumerate(self.current_queue) if track["path"] == current), -1)
            if idx == -1:
                return

            prev_idx = (idx - 1) % len(self.current_queue)
            prev_track = self.current_queue[prev_idx]

            if not self.is_shuffle:
                self.user_queue = self.current_queue[prev_idx + 1 :]

            self.play_track(prev_track["path"])
            if self.current_view == "queue":
                self._apply_track_view()

    def on_prev_clicked(self, widget) -> None:
        self._shift_track(-1)

    def on_next_clicked(self, widget) -> None:
        self._shift_track(1)

    def toggle_favorite(self, path: str) -> None:
        if path in self.favorites:
            self.favorites.discard(path)
        else:
            self.favorites.add(path)
        self._save_state()
        self._refresh_sidebar()
        self._apply_track_view()
        self._update_now_playing_ui()

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

    def _set_cover_from_tag_bytes(self, data: bytes | None) -> None:
        if data and not self._load_cover_from_bytes(data, 60):
            self._set_default_cover()

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
        try:
            self.player.set_state(Gst.State.NULL)
        except Exception:
            pass
        self.is_playing = False
        self._update_play_pause_icon()
        self._set_default_cover()

    def format_time(self, ns: int) -> str:
        seconds = max(0, ns) // Gst.SECOND
        return self.format_time_from_seconds(seconds)

    def format_time_from_seconds(self, seconds: float) -> str:
        total = max(0, int(seconds))
        if total >= 3600:
            return f"{total // 3600:02d}:{total % 3600 // 60:02d}:{total % 60:02d}"
        return f"{total // 60:02d}:{total % 60:02d}"

    def update_progress(self) -> bool:
        if not self.is_playing:
            return True
        try:
            suc_pos, pos = self.player.query_position(Gst.Format.TIME)
            suc_dur, dur = self.player.query_duration(Gst.Format.TIME)
            if suc_pos and suc_dur and dur > 0:
                self.progress_bar.set_fraction(min(max(pos / dur, 0.0), 1.0))
                self.time_current.set_text(self.format_time(pos))
                self.time_total.set_text(self.format_time(dur))
                self.current_duration = dur / Gst.SECOND
        except Exception:
            pass
        return True

    def on_about_clicked(self, widget) -> None:
        about = Gtk.AboutDialog()
        about.set_transient_for(self)
        about.set_modal(True)

        about.set_program_name("OpenWave")
        about.set_version("0.1")
        about.set_comments(
            "Player de música planejado para a estética do tema Mint-Y."
        )
        about.set_copyright("© 2026 Desenvolvedores do OpenWave")
        about.set_license_type(Gtk.License.MIT_X11)
        about.set_website("https://github.com/openwave-player/openwave")
        about.set_website_label("Página oficial do código-fonte")
        about.set_authors(["Mateus Calixto <contato@mateuscalixto.com.br>"])
        about.set_artists(
            [
                "GNOME Project (ícones simbólicos)",
                "Linux Mint Desktop Team (inspiração visual)",
            ]
        )
        about.set_logo_icon_name("multimedia-audio-player")
        about.run()
        about.destroy()


if __name__ == "__main__":
    Gst.init(None) 
    
    Gtk.Window.set_default_icon_name("multimedia-audio-player")
    
    window = OpenWave() 
    window.connect("destroy", Gtk.main_quit)
    window.show_all()
    Gtk.main()