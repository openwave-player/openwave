from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, Gtk, Pango


def apply_css(css: str) -> None:
    """Aplica uma string CSS à tela padrão."""
    provider = Gtk.CssProvider()
    provider.load_from_data(css.encode("utf-8"))
    screen = Gdk.Screen.get_default()
    if screen:
        Gtk.StyleContext.add_provider_for_screen(
            screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )


APP_CSS = """
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


def build_header(
    on_choose_folder,
    on_refresh,
    on_about,
) -> tuple[Gtk.HeaderBar, Gtk.Button, Gtk.Button, Gtk.Button]:
    """Constrói e retorna o HeaderBar junto com os botões principais."""
    header = Gtk.HeaderBar()
    header.set_show_close_button(True)
    header.set_title("OpenWave")

    btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)

    btn_choose_folder = Gtk.Button.new_from_icon_name("folder-open-symbolic", Gtk.IconSize.BUTTON)
    btn_choose_folder.set_tooltip_text("Abrir pasta da biblioteca")
    btn_choose_folder.connect("clicked", on_choose_folder)
    btn_box.pack_start(btn_choose_folder, False, False, 0)

    btn_refresh = Gtk.Button.new_from_icon_name("view-refresh-symbolic", Gtk.IconSize.BUTTON)
    btn_refresh.set_tooltip_text("Reescanear biblioteca")
    btn_refresh.connect("clicked", on_refresh)
    btn_box.pack_start(btn_refresh, False, False, 0)

    header.pack_start(btn_box)

    btn_about = Gtk.Button.new_from_icon_name("help-about-symbolic", Gtk.IconSize.BUTTON)
    btn_about.set_tooltip_text("Sobre")
    btn_about.connect("clicked", on_about)
    header.pack_end(btn_about)

    return header, btn_choose_folder, btn_refresh, btn_about


def sidebar_section(title: str, with_add_button: bool = False):
    """Cria uma seção da sidebar com título opcional e botão de adicionar."""
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


def add_sidebar_row(
    listbox: Gtk.ListBox,
    title: str,
    kind: str,
    icon_name: str,
    subtitle: str | None = None,
    playlist_name: str | None = None,
    artist_name: str | None = None,
    album_name: str | None = None,
    album_artist: str | None = None,
) -> None:
    """Adiciona uma linha à sidebar."""
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

    lbl = Gtk.Label(label=title)
    lbl.set_halign(Gtk.Align.START)
    lbl.set_xalign(0.0)
    lbl.set_ellipsize(Pango.EllipsizeMode.END)
    text_box.pack_start(lbl, False, False, 0)

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
