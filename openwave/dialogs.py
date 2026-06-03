from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from .constants import APP_VERSION


class PlaylistDialog(Gtk.Dialog):
    """Diálogo para adicionar uma faixa a uma playlist existente ou nova."""

    def __init__(self, parent: Gtk.Window, playlists: list[str]):
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

    def get_choice(self) -> str | None:
        active = self.combo.get_active_text()
        new_name = self.entry.get_text().strip()
        if active == "Nova playlist...":
            return new_name or None
        return active


def show_about_dialog(parent: Gtk.Window) -> None:
    """Exibe o diálogo 'Sobre' do OpenWave."""
    about = Gtk.AboutDialog()
    about.set_transient_for(parent)
    about.set_modal(True)
    about.set_program_name("OpenWave")
    about.set_version(APP_VERSION)
    about.set_comments("Player de música planejado para a estética do tema Mint-Y.")
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
