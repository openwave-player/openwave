import gi
import json
import os
from pathlib import Path

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Gst", "1.0")

from gi.repository import Gtk, Gdk, GdkPixbuf, GLib, Gst, Pango

AUDIO_EXTENSIONS = {
    ".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac", ".opus",
    ".wma", ".aiff", ".aif", ".alac", ".mp2", ".mka"
}

def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)

def natural_track_title(path: str) -> tuple[str, str]:
    stem = Path(path).stem.strip()
    if " - " in stem:
        artist, title = stem.split(" - ", 1)
        artist = artist.strip() or "Artista Desconhecido"
        title = title.strip() or stem
        return title, artist
    return stem or "Faixa sem nome", "Artista Desconhecido"

class PlaylistDialog(Gtk.Dialog):
    def __init__(self, parent, playlists: list[str]):
        super().__init__(title="Adicionar à playlist", transient_for=parent, flags=0)
        self.set_modal(True)
        self.add_buttons("Cancelar", Gtk.ResponseType.CANCEL, "Adicionar", Gtk.ResponseType.OK)
        self.set_default_size(360, 150)
        
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
        self.set_default_size(1100, 750)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.set_resizable(True)

        self.base_dir = Path(GLib.get_user_config_dir()) / "openwave"
        ensure_dir(self.base_dir)
        self.config_file = self.base_dir / "state.json"

        
        self.library_folder: str | None = None
        self.library_tracks: list[dict] = []
        self.favorites: set[str] = set()
        self.playlists: dict[str, list[str]] = {}
        self.current_view = "library"
        self.current_playlist_name: str | None = None
        self.current_queue: list[dict] = []
        self.selected_track_path: str | None = None
        self.current_track_path: str | None = None
        self.is_playing = False
        self.timer_id = None

        
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

        self.show_all()
        self.empty_label.show()

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
        
        self.source_label = Gtk.Label(label="Biblioteca")
        self.source_label.set_halign(Gtk.Align.START)
        self.source_label.get_style_context().add_class("title-1")
        list_header.pack_start(self.source_label, False, False, 0)

        search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("Pesquisar músicas...")
        self.search_entry.set_width_chars(30)
        self.search_entry.connect("search-changed", self.on_search_changed)
        search_box.pack_start(self.search_entry, True, True, 0)
        list_header.pack_end(search_box, False, False, 0)
        
        main_area.pack_start(list_header, False, False, 0)

        self.empty_label = Gtk.Label(label="Abra uma pasta para ver suas músicas.")
        self.empty_label.set_halign(Gtk.Align.CENTER)
        self.empty_label.set_valign(Gtk.Align.CENTER)
        self.empty_label.get_style_context().add_class("empty-state")

        self.track_scroll_overlay = Gtk.Overlay()
        self.track_scroll = Gtk.ScrolledWindow()
        self.track_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        
        self.track_listbox = Gtk.ListBox()
        self.track_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.track_listbox.set_activate_on_single_click(True)
        self.track_listbox.connect("row-activated", self.on_track_activated)
        self.track_listbox.connect("selected-rows-changed", self.on_track_selected)
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
        now_playing_box.set_size_request(250, -1)
        
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
        self.track_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.track_label.get_style_context().add_class("track-title-bold")
        info_box.pack_start(self.track_label, False, False, 0)

        self.artist_label = Gtk.Label(label=self.current_artist)
        self.artist_label.set_halign(Gtk.Align.START)
        self.artist_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.artist_label.get_style_context().add_class("muted")
        info_box.pack_start(self.artist_label, False, False, 0)
        
        now_playing_box.pack_start(info_box, True, True, 0)
        bottom_bar.pack_start(now_playing_box, False, False, 0)

        center_dock = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        center_dock.set_valign(Gtk.Align.CENTER)
        
        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        btn_row.set_halign(Gtk.Align.CENTER)
        
        self.btn_prev = Gtk.Button.new_from_icon_name("media-skip-backward-symbolic", Gtk.IconSize.LARGE_TOOLBAR)
        self.btn_prev.get_style_context().add_class("control-btn-flat")
        self.btn_prev.connect("clicked", self.on_prev_clicked)
        
        self.btn_play = Gtk.Button.new_from_icon_name("media-playback-start-symbolic", Gtk.IconSize.LARGE_TOOLBAR)
        self.btn_play.get_style_context().add_class("control-btn-main")
        self.btn_play.connect("clicked", self.on_play_clicked)
        
        self.btn_next = Gtk.Button.new_from_icon_name("media-skip-forward-symbolic", Gtk.IconSize.LARGE_TOOLBAR)
        self.btn_next.get_style_context().add_class("control-btn-flat")
        self.btn_next.connect("clicked", self.on_next_clicked)

        for btn in [self.btn_prev, self.btn_play, self.btn_next]:
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

    def _setup_css(self) -> None:
        css = """
        .main-background { background-color: @theme_bg_color; }
        .sidebar { background-color: shade(@theme_bg_color, 0.96); border-right: 1px solid alpha(@theme_fg_color, 0.08); }
        .content-area { background-color: @theme_bg_color; }
        .bottom-bar { background-color: shade(@theme_bg_color, 0.92); border-top: 1px solid alpha(@theme_fg_color, 0.1); padding: 8px 16px; }
        
        .muted { opacity: 0.65; }
        .muted-small { opacity: 0.65; font-size: 11px; }
        .title-1 { font-size: 26px; font-weight: 800; letter-spacing: -0.5px; }
        .title-2 { font-size: 13px; font-weight: 700; opacity: 0.5; margin-bottom: 8px; }
        
        .cover-frame-small { border-radius: 6px; border: 1px solid alpha(@theme_fg_color, 0.1); }
        .track-title-bold { font-weight: 700; font-size: 14px; }
        
        .sidebar-row { padding: 10px 14px; border-radius: 6px; margin: 2px 10px; font-weight: 600; }
        .sidebar-row:hover { background-color: alpha(@theme_fg_color, 0.05); }
        .sidebar-row:selected { background-color: alpha(@theme_selected_bg_color, 0.15); color: @theme_selected_bg_color; }
        
        .track-list { background: transparent; }
        .track-row { padding: 12px 16px; border-bottom: 1px solid alpha(@theme_fg_color, 0.03); transition: all 200ms ease; }
        .track-row:hover { background-color: alpha(@theme_fg_color, 0.04); }
        .track-row:selected { background-color: alpha(@theme_selected_bg_color, 0.1); }
        
        .control-btn-flat { background: transparent; border: none; box-shadow: none; padding: 8px; border-radius: 50%; }
        .control-btn-flat:hover { background: alpha(@theme_fg_color, 0.1); }
        .control-btn-flat.unstarred { opacity: 0.4; }
        .control-btn-flat.starred { opacity: 1.0; color: @theme_selected_bg_color; }
        .control-btn-main { border-radius: 50%; padding: 12px; background-color: @theme_selected_bg_color; color: @theme_selected_fg_color; border: none; }
        .control-btn-main:hover { background-color: shade(@theme_selected_bg_color, 1.1); }
        
        progressbar trough { min-height: 4px; border-radius: 2px; }
        progressbar progress { min-height: 4px; border-radius: 2px; background-color: @theme_selected_bg_color; }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        screen = Gdk.Screen.get_default()
        if screen:
            Gtk.StyleContext.add_provider_for_screen(screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def _setup_header(self) -> None:
        self.header = Gtk.HeaderBar()
        self.header.set_show_close_button(True)
        self.header.set_title("OpenWave")
        self.set_titlebar(self.header)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.btn_choose_folder = Gtk.Button.new_from_icon_name("folder-open-symbolic", Gtk.IconSize.BUTTON)
        self.btn_choose_folder.connect("clicked", self.on_choose_folder_clicked)
        btn_box.pack_start(self.btn_choose_folder, False, False, 0)

        self.btn_refresh = Gtk.Button.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.BUTTON)
        self.btn_refresh.connect("clicked", self.on_refresh_clicked)
        btn_box.pack_start(self.btn_refresh, False, False, 0)
        self.header.pack_start(btn_box)

        self.btn_about = Gtk.Button.new_from_icon_name("help-about-symbolic", Gtk.IconSize.BUTTON)
        self.btn_about.connect("clicked", self.on_about_clicked)
        self.header.pack_end(self.btn_about)

    def _build_sidebar(self) -> Gtk.Widget:
        wrapper = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        wrapper.set_size_request(240, -1)
        wrapper.get_style_context().add_class("sidebar")

        top_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        top_box.set_border_width(14)
        lbl_menu = Gtk.Label(label="Sua Coleção")
        lbl_menu.set_halign(Gtk.Align.START)
        lbl_menu.get_style_context().add_class("title-2")
        top_box.pack_start(lbl_menu, False, False, 0)

        self.sidebar_listbox = Gtk.ListBox()
        self.sidebar_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.sidebar_listbox.set_activate_on_single_click(True)
        self.sidebar_listbox.connect("row-selected", self.on_sidebar_selected)
        self.sidebar_listbox.get_style_context().add_class("track-list")
        top_box.pack_start(self.sidebar_listbox, False, False, 0)
        wrapper.pack_start(top_box, False, False, 0)

        play_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        play_box.set_border_width(14)
        header_play = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        lbl_play = Gtk.Label(label="Playlists")
        lbl_play.set_halign(Gtk.Align.START)
        lbl_play.get_style_context().add_class("title-2")
        header_play.pack_start(lbl_play, True, True, 0)
        
        btn_add = Gtk.Button.new_from_icon_name("list-add-symbolic", Gtk.IconSize.MENU)
        btn_add.get_style_context().add_class("control-btn-flat")
        btn_add.connect("clicked", self.on_new_playlist_clicked)
        header_play.pack_end(btn_add, False, False, 0)
        play_box.pack_start(header_play, False, False, 0)

        self.playlist_listbox = Gtk.ListBox()
        self.playlist_listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.playlist_listbox.set_activate_on_single_click(True)
        self.playlist_listbox.connect("row-selected", self.on_sidebar_selected)
        self.playlist_listbox.connect("button-press-event", self.on_sidebar_button_press)
        self.playlist_listbox.get_style_context().add_class("track-list")

        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.add(self.playlist_listbox)
        play_box.pack_start(scroll, True, True, 0)
        wrapper.pack_start(play_box, True, True, 0)

        self._refresh_sidebar()
        return wrapper

    def _load_state(self) -> None:
        if not self.config_file.exists(): return
        try:
            data = json.loads(self.config_file.read_text(encoding="utf-8"))
            self.library_folder = data.get("library_folder")
            self.favorites = set(data.get("favorites", []))
            playlists = data.get("playlists", {})
            if isinstance(playlists, dict):
                self.playlists = {str(k): list(v) for k, v in playlists.items() if isinstance(v, list)}
        except Exception: pass

    def _save_state(self) -> None:
        data = {"library_folder": self.library_folder, "favorites": sorted(self.favorites), "playlists": self.playlists}
        self.config_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

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
            self._update_header_subtitle()
            return
        tracks = []
        for current_root, _, files in os.walk(root):
            for filename in files:
                path = Path(current_root) / filename
                if path.suffix.lower() in AUDIO_EXTENSIONS:
                    title, artist = natural_track_title(str(path))
                    tracks.append({"path": str(path), "title": title, "artist": artist})
        tracks.sort(key=lambda item: item["title"].lower())
        self.library_tracks = tracks
        self.library_folder = folder
        self._save_state()
        self._refresh_sidebar()
        self._update_header_subtitle()
        self._set_view(self.current_view if self.current_view != "playlist" else "library")

    def _update_header_subtitle(self) -> None:
        if self.library_folder:
            self.header.set_subtitle(f"{Path(self.library_folder).name} • {len(self.library_tracks)} faixas")
        else:
            self.header.set_subtitle("Nenhuma pasta selecionada")

    def _refresh_sidebar(self) -> None:
        if not hasattr(self, "sidebar_listbox"): return
        for child in self.sidebar_listbox.get_children(): self.sidebar_listbox.remove(child)
        for child in self.playlist_listbox.get_children(): self.playlist_listbox.remove(child)

        self._add_sidebar_row(self.sidebar_listbox, "Biblioteca", "library", "folder-music-symbolic")
        self._add_sidebar_row(self.sidebar_listbox, "Favoritos", "favorites", "emblem-favorite-symbolic")
        for name in sorted(self.playlists.keys(), key=str.lower):
            self._add_sidebar_row(self.playlist_listbox, name, "playlist", "view-list-symbolic", name)
        self.sidebar_listbox.show_all()
        self.playlist_listbox.show_all()

    def _add_sidebar_row(self, listbox, title: str, kind: str, icon_name: str, playlist_name: str = None) -> None:
        row = Gtk.ListBoxRow()
        row.kind = kind
        row.playlist_name = playlist_name
        row.get_style_context().add_class("sidebar-row")
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        icon = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.MENU)
        box.pack_start(icon, False, False, 0)
        label = Gtk.Label(label=title)
        label.set_halign(Gtk.Align.START)
        box.pack_start(label, True, True, 0)
        row.add(box)
        listbox.add(row)

    def _apply_track_view(self) -> None:
        query = self.search_entry.get_text().strip().lower()
        if self.current_view == "library":
            tracks = self.library_tracks[:]
            self.source_label.set_text("Biblioteca")
        elif self.current_view == "favorites":
            tracks = [t for t in self.library_tracks if t["path"] in self.favorites]
            self.source_label.set_text("Favoritos")
        elif self.current_view == "playlist" and self.current_playlist_name:
            raw = self.playlists.get(self.current_playlist_name, [])
            lib_paths = {t["path"] for t in self.library_tracks}
            tracks = [{"path": p, **dict(zip(('title', 'artist'), natural_track_title(p)))} for p in raw if p in lib_paths or Path(p).exists()]
            self.source_label.set_text(self.current_playlist_name)
        else:
            tracks = self.library_tracks[:]

        if query:
            tracks = [t for t in tracks if query in t["title"].lower() or query in t["artist"].lower()]

        self.current_queue = tracks
        self._rebuild_track_list(tracks)
        has_tracks = len(tracks) > 0
        self.btn_prev.set_sensitive(has_tracks)
        self.btn_next.set_sensitive(has_tracks)
        self.btn_play.set_sensitive(has_tracks)
        self.empty_label.set_visible(not has_tracks)

    def _rebuild_track_list(self, tracks: list[dict]) -> None:
        for child in self.track_listbox.get_children(): self.track_listbox.remove(child)
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
            title.set_ellipsize(Pango.EllipsizeMode.END)
            title.get_style_context().add_class("track-title-bold")
            vbox.pack_start(title, False, False, 0)

            artist = Gtk.Label(label=item["artist"])
            artist.set_halign(Gtk.Align.START)
            artist.set_ellipsize(Pango.EllipsizeMode.END)
            artist.get_style_context().add_class("muted-small")
            vbox.pack_start(artist, False, False, 0)
            box.pack_start(vbox, True, True, 0)

            if item["path"] in self.favorites:
                fav = Gtk.Image.new_from_icon_name("emblem-favorite-symbolic", Gtk.IconSize.MENU)
                box.pack_end(fav, False, False, 0)
            row.add(box)
            self.track_listbox.add(row)
        self.track_listbox.show_all()

    def _get_selected_track_path(self) -> str | None:
        row = self.track_listbox.get_selected_row()
        return row.track_path if row and hasattr(row, "track_path") else (self.selected_track_path or self.current_track_path)

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
                ctx.remove_class("unstarred"); ctx.add_class("starred")
            else:
                ctx.remove_class("starred"); ctx.add_class("unstarred")
        self.btn_favorite_dock.set_sensitive(True)
        self.btn_add_playlist.set_sensitive(True)

    def _update_play_pause_icon(self) -> None:
        icon = "media-playback-pause-symbolic" if self.is_playing else "media-playback-start-symbolic"
        self.btn_play.set_image(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.LARGE_TOOLBAR))

    def _set_view(self, view: str, playlist_name: str = None) -> None:
        self.current_view = view
        self.current_playlist_name = playlist_name
        self.search_entry.set_text("")
        self._apply_track_view()

    def play_track(self, path: str) -> None:
        if not path or not Path(path).exists(): return
        self.player.set_state(Gst.State.NULL)
        self._set_default_cover()
        
        t, a = natural_track_title(path)
        self.current_title, self.current_artist, self.current_album = t, a, ""
        self.current_track_path = path
        
        self.player.set_property("uri", GLib.filename_to_uri(path, None))
        self._update_now_playing_ui()
        self.player.set_state(Gst.State.PLAYING)
        self.is_playing = True
        self._update_play_pause_icon()

        if self.timer_id is None:
            self.timer_id = GLib.timeout_add(1000, self.update_progress)

    def on_choose_folder_clicked(self, widget) -> None:
        dialog = Gtk.FileChooserDialog("Selecione a pasta", self, Gtk.FileChooserAction.SELECT_FOLDER)
        dialog.add_buttons("Cancelar", Gtk.ResponseType.CANCEL, "Selecionar", Gtk.ResponseType.OK)
        if self.library_folder: dialog.set_filename(self.library_folder)
        if dialog.run() == Gtk.ResponseType.OK:
            self._scan_library(dialog.get_filename())
            self._set_view("library")
        dialog.destroy()

    def on_refresh_clicked(self, widget) -> None:
        if self.library_folder: self._scan_library(self.library_folder)

    def on_sidebar_selected(self, listbox, row) -> None:
        if not row or not hasattr(row, "kind"): return
        other_list = self.playlist_listbox if listbox == self.sidebar_listbox else self.sidebar_listbox
        other_list.unselect_all()
        self._set_view(row.kind, row.playlist_name)

    def on_sidebar_button_press(self, listbox, event) -> bool:
        if event.button == 3:
            row = listbox.get_row_at_y(int(event.y))
            if row and hasattr(row, "kind") and row.kind == "playlist":
                listbox.select_row(row)
                menu = Gtk.Menu()
                item_rename = Gtk.MenuItem(label="Renomear Playlist")
                item_rename.connect("activate", lambda w: self.rename_playlist(row.playlist_name))
                menu.append(item_rename)
                item_delete = Gtk.MenuItem(label="Excluir Playlist")
                item_delete.connect("activate", lambda w: self.delete_playlist(row.playlist_name))
                menu.append(item_delete)
                menu.show_all()
                menu.popup_at_pointer(event)
                return True
        return False

    def on_track_button_press(self, listbox, event) -> bool:
        if event.button == 3 and self.current_view == "playlist":
            row = listbox.get_row_at_y(int(event.y))
            if row and hasattr(row, "track_path"):
                listbox.select_row(row)
                menu = Gtk.Menu()
                item_remove = Gtk.MenuItem(label="Remover desta Playlist")
                item_remove.connect("activate", lambda w: self.remove_from_current_playlist(row.track_path))
                menu.append(item_remove)
                menu.show_all()
                menu.popup_at_pointer(event)
                return True
        return False

    def rename_playlist(self, old_name: str) -> None:
        dialog = Gtk.Dialog(title="Renomear Playlist", transient_for=self, flags=0)
        dialog.add_buttons("Cancelar", Gtk.ResponseType.CANCEL, "Salvar", Gtk.ResponseType.OK)
        box = dialog.get_content_area(); box.set_border_width(18)
        entry = Gtk.Entry(); entry.set_text(old_name)
        box.pack_start(entry, True, True, 0); dialog.show_all()
        if dialog.run() == Gtk.ResponseType.OK and (new_name := entry.get_text().strip()):
            if new_name != old_name:
                self.playlists[new_name] = self.playlists.pop(old_name, [])
                self._save_state(); self._refresh_sidebar()
                if self.current_view == "playlist" and self.current_playlist_name == old_name:
                    self._set_view("playlist", new_name)
        dialog.destroy()

    def delete_playlist(self, name: str) -> None:
        dialog = Gtk.MessageDialog(transient_for=self, flags=0, message_type=Gtk.MessageType.QUESTION, buttons=Gtk.ButtonsType.YES_NO, text=f"Excluir a playlist '{name}'?")
        if dialog.run() == Gtk.ResponseType.YES:
            self.playlists.pop(name, None); self._save_state(); self._refresh_sidebar()
            if self.current_view == "playlist" and self.current_playlist_name == name: self._set_view("library")
        dialog.destroy()

    def remove_from_current_playlist(self, track_path: str) -> None:
        if self.current_view == "playlist" and self.current_playlist_name:
            name = self.current_playlist_name
            if name in self.playlists and track_path in self.playlists[name]:
                self.playlists[name].remove(track_path)
                self._save_state(); self._apply_track_view()

    def on_search_changed(self, widget) -> None: self._apply_track_view()

    def on_track_selected(self, listbox, *args) -> None:
        row = listbox.get_selected_row()
        self.selected_track_path = row.track_path if row else None
        self._update_now_playing_ui()

    def on_track_activated(self, listbox, row) -> None:
        if row and hasattr(row, "track_path"): self.play_track(row.track_path)

    def on_play_clicked(self, widget) -> None:
        if not self.current_track_path:
            path = self._get_selected_track_path()
            if path: self.play_track(path)
            return
        self.player.set_state(Gst.State.PAUSED if self.is_playing else Gst.State.PLAYING)
        self.is_playing = not self.is_playing
        self._update_play_pause_icon()

    def _shift_track(self, direction: int) -> None:
        if not self.current_queue: return
        path = self.current_track_path or self._get_selected_track_path()
        if not path: return
        idx = next((i for i, t in enumerate(self.current_queue) if t["path"] == path), 0)
        self.play_track(self.current_queue[(idx + direction) % len(self.current_queue)]["path"])

    def on_prev_clicked(self, widget) -> None: self._shift_track(-1)
    def on_next_clicked(self, widget) -> None: self._shift_track(1)

    def on_toggle_favorite_clicked(self, widget) -> None:
        path = self._get_selected_track_path()
        if not path: return
        if path in self.favorites: self.favorites.discard(path)
        else: self.favorites.add(path)
        self._save_state(); self._apply_track_view(); self._update_now_playing_ui()

    def on_add_to_playlist_clicked(self, widget) -> None:
        path = self._get_selected_track_path()
        if not path: return
        dialog = PlaylistDialog(self, sorted(self.playlists.keys(), key=str.lower))
        if dialog.run() == Gtk.ResponseType.OK and (name := dialog.get_choice()):
            self.playlists.setdefault(name, [])
            if path not in self.playlists[name]:
                self.playlists[name].append(path)
                self._save_state(); self._refresh_sidebar()
        dialog.destroy()

    def on_new_playlist_clicked(self, widget) -> None:
        dialog = Gtk.Dialog(title="Nova Playlist", transient_for=self, flags=0)
        dialog.add_buttons("Cancelar", Gtk.ResponseType.CANCEL, "Criar", Gtk.ResponseType.OK)
        box = dialog.get_content_area(); box.set_border_width(18)
        entry = Gtk.Entry(placeholder_text="Nome da playlist")
        box.pack_start(entry, True, True, 0); dialog.show_all()
        if dialog.run() == Gtk.ResponseType.OK and (name := entry.get_text().strip()):
            if name not in self.playlists:
                self.playlists[name] = []
                self._save_state(); self._refresh_sidebar()
        dialog.destroy()

    def on_tag_found(self, bus, message) -> None:
        try: taglist = message.parse_tag()
        except Exception: return

        def get_string_tag(tag):
            ret, val = taglist.get_string(tag)
            return val if ret else None

        title, artist, album = get_string_tag(Gst.TAG_TITLE), get_string_tag(Gst.TAG_ARTIST), get_string_tag(Gst.TAG_ALBUM)
        updated = False
        if title: self.current_title, updated = title, True
        if artist: self.current_artist, updated = artist, True
        if album: self.current_album, updated = album, True
        if updated: GLib.idle_add(self._update_now_playing_ui)

        try:
            success, sample = taglist.get_sample(Gst.TAG_IMAGE)
            if success and sample:
                buffer = sample.get_buffer()
                suc, map_info = buffer.map(Gst.MapFlags.READ)
                if suc:
                    loader = GdkPixbuf.PixbufLoader()
                    loader.write(map_info.data); loader.close()
                    if pixbuf := loader.get_pixbuf():
                        scaled = pixbuf.scale_simple(60, 60, GdkPixbuf.InterpType.BILINEAR)
                        GLib.idle_add(self.cover_image.set_from_pixbuf, scaled)
                    buffer.unmap(map_info)
        except Exception: pass

    def on_eos(self, bus, message) -> None: self.on_next_clicked(None)
    def on_error(self, bus, message) -> None:
        self.player.set_state(Gst.State.NULL); self.is_playing = False; self._update_play_pause_icon()

    def format_time(self, ns: int) -> str:
        s = max(0, ns) // Gst.SECOND
        return f"{s//3600:02d}:{s%3600//60:02d}:{s%60:02d}" if s >= 3600 else f"{s//60:02d}:{s%60:02d}"

    def update_progress(self) -> bool:
        if not self.is_playing: return True
        try:
            suc_pos, pos = self.player.query_position(Gst.Format.TIME)
            suc_dur, dur = self.player.query_duration(Gst.Format.TIME)
            if suc_pos and suc_dur and dur > 0:
                self.progress_bar.set_fraction(pos / dur)
                self.time_current.set_text(self.format_time(pos))
                self.time_total.set_text(self.format_time(dur))
        except Exception: pass
        return True

    def on_about_clicked(self, widget) -> None:
        about = Gtk.AboutDialog()
        about.set_transient_for(self)
        about.set_modal(True)
        
        about.set_program_name("OpenWave")
        about.set_version("3.2.0")
        about.set_comments("Um player de música simples e rápido, projetado com foco na estética do tema Mint-Y.")
        about.set_copyright("© 2026 Desenvolvedores do OpenWave")
        
        about.set_license_type(Gtk.License.MIT_X11)
        
        about.set_website("https://github.com/openwave-player/openwave")
        about.set_website_label("Página Oficial do Código Fonte")
        
        about.set_authors([
            "Mateus Calixto <contato@mateuscalixto.com.br>"
        ])
        about.set_artists([
            "GNOME Project (Design de Ícones Simbólicos)",
            "Linux Mint Desktop Team (Inspiração visual e design do tema Mint-Y)"

        ])
        
        about.set_logo_icon_name("multimedia-audio-player")
        
        about.run()
        about.destroy()

if __name__ == "__main__":
    app = OpenWave()
    app.connect("destroy", Gtk.main_quit)
    Gtk.main()