#!/usr/bin/env python3
import sys
import os
import shutil
import subprocess
import threading
from pathlib import Path
import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gtk, GLib, Gdk

class OpenWaveInstaller(Gtk.Assistant):
    def __init__(self):
        super().__init__()
        self.set_title("Assistente do OpenWave")
        self.set_default_size(680, 460)
        self.set_resizable(False)
        self.set_position(Gtk.WindowPosition.CENTER)
        
        self._apply_refined_css()
        
        self.install_dir = Path.home() / ".local" / "share" / "openwave"
        self.create_shortcut = True
        
        self._build_intro_page()
        self._build_config_page()
        self._build_progress_page()
        self._build_summary_page()
        
        self.set_forward_page_func(self.forward_page_func, None)
        
        self.connect("cancel", self.on_cancel)
        self.connect("close", self.on_close)
        self.connect("prepare", self.on_prepare)
        
        self.show_all()

    def _apply_refined_css(self):
        css = """
        assistant { 
            background-color: @theme_bg_color; 
        }
        .main-title { 
            font-size: 24px; 
            font-weight: 800; 
            color: @theme_fg_color;
            letter-spacing: -0.5px;
        }
        .section-title { 
            font-size: 15px; 
            font-weight: 700; 
            color: @theme_fg_color;
            opacity: 0.9;
        }
        .text-body {
            font-size: 13px;
            opacity: 0.75;
        }
        .text-muted { 
            font-size: 12px;
            opacity: 0.5; 
        }
        .card-group {
            background-color: alpha(@theme_fg_color, 0.04);
            border: 1px solid alpha(@theme_fg_color, 0.08);
            border-radius: 8px;
            padding: 4px;
        }
        .card-row {
            padding: 12px 16px;
            border-radius: 6px;
            transition: background-color 200ms;
        }
        .card-row:hover {
            background-color: alpha(@theme_fg_color, 0.04);
        }
        .card-row:not(:last-child) {
            border-bottom: 1px solid alpha(@theme_fg_color, 0.05);
        }
        progressbar trough { 
            min-height: 8px; 
            border-radius: 4px; 
            background-color: alpha(@theme_fg_color, 0.08);
            border: none;
        }
        progressbar progress { 
            min-height: 8px; 
            border-radius: 4px; 
            background-color: @theme_selected_bg_color; 
        }
        entry {
            padding: 6px 10px;
            border-radius: 6px;
        }
        button.suggested-action {
            font-weight: bold;
        }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode("utf-8"))
        screen = Gdk.Screen.get_default()
        if screen:
            Gtk.StyleContext.add_provider_for_screen(
                screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )

    def _build_intro_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        box.set_border_width(28)
        
        header_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        icon = Gtk.Image.new_from_icon_name("multimedia-audio-player", Gtk.IconSize.DIALOG)
        icon.set_pixel_size(54)
        header_box.pack_start(icon, False, False, 0)
        
        title_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        title = Gtk.Label(label="OpenWave")
        title.get_style_context().add_class("main-title")
        title.set_halign(Gtk.Align.START)
        
        version = Gtk.Label(label="Assistente de Configuração • Versão 0.1.5")
        version.get_style_context().add_class("text-muted")
        version.set_halign(Gtk.Align.START)
        
        title_vbox.pack_start(title, False, False, 0)
        title_vbox.pack_start(version, False, False, 0)
        header_box.pack_start(title_vbox, True, True, 0)
        box.pack_start(header_box, False, False, 0)
        
        desc = Gtk.Label(
            label="Gerencie sua biblioteca de músicas com uma interface limpa, "
                  "suporte a playlists personalizadas e leitura inteligente de metadados de áudio. "
                  "Escolha a operação desejada:"
        )
        desc.get_style_context().add_class("text-body")
        desc.set_line_wrap(True)
        desc.set_halign(Gtk.Align.START)
        box.pack_start(desc, False, False, 4)
        
        group_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        group_box.get_style_context().add_class("card-group")
        
        row_install = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        row_install.get_style_context().add_class("card-row")
        self.rad_install = Gtk.RadioButton.new_with_label_from_widget(None, "Instalar ou atualizar o aplicativo no perfil do usuário")
        row_install.pack_start(self.rad_install, True, True, 0)
        
        row_uninstall = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        row_uninstall.get_style_context().add_class("card-row")
        self.rad_uninstall = Gtk.RadioButton.new_with_label_from_widget(self.rad_install, "Remover completamente o aplicativo e seus atalhos")
        row_uninstall.pack_start(self.rad_uninstall, True, True, 0)
        
        if (Path.home() / ".local" / "share" / "applications" / "openwave.desktop").exists():
            self.rad_uninstall.set_active(True)
        else:
            self.rad_install.set_active(True)
            
        group_box.pack_start(row_install, False, False, 0)
        group_box.pack_start(row_uninstall, False, False, 0)
        box.pack_start(group_box, False, False, 0)
        
        credits_lbl = Gtk.Label(label="Desenvolvido por Mateus Calixto • Código sob Licença MIT")
        credits_lbl.get_style_context().add_class("text-muted")
        credits_lbl.set_halign(Gtk.Align.START)
        box.pack_end(credits_lbl, False, False, 0)
        
        box.show_all()
        self.append_page(box)
        self.set_page_title(box, "Introdução")
        self.set_page_type(box, Gtk.AssistantPageType.INTRO)
        self.set_page_complete(box, True)

    def _build_config_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_border_width(28)
        
        title = Gtk.Label(label="Diretório de Destino")
        title.get_style_context().add_class("section-title")
        title.set_halign(Gtk.Align.START)
        box.pack_start(title, False, False, 0)
        
        dir_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.ent_dir = Gtk.Entry()
        self.ent_dir.set_text(str(self.install_dir))
        self.ent_dir.set_hexpand(True)
        dir_box.pack_start(self.ent_dir, True, True, 0)
        
        btn_browse = Gtk.Button(label="Procurar...")
        btn_browse.connect("clicked", self.on_browse_clicked)
        dir_box.pack_start(btn_browse, False, False, 0)
        box.pack_start(dir_box, False, False, 0)
        
        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        separator.set_margin_top(8)
        separator.set_margin_bottom(8)
        box.pack_start(separator, False, False, 0)
        
        self.chk_shortcut = Gtk.CheckButton(label="Adicionar lançador ao menu de aplicativos do sistema")
        self.chk_shortcut.set_active(True)
        box.pack_start(self.chk_shortcut, False, False, 0)
        
        box.show_all()
        self.append_page(box)
        self.set_page_title(box, "Configurações")
        self.set_page_type(box, Gtk.AssistantPageType.CONTENT)
        self.set_page_complete(box, True)

    def _build_progress_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.set_border_width(28)
        box.set_valign(Gtk.Align.CENTER)
        
        self.lbl_status = Gtk.Label(label="Preparando ambiente...")
        self.lbl_status.get_style_context().add_class("text-body")
        self.lbl_status.set_halign(Gtk.Align.START)
        box.pack_start(self.lbl_status, False, False, 0)
        
        self.progress_bar = Gtk.ProgressBar()
        box.pack_start(self.progress_bar, False, False, 0)
        
        box.show_all()
        self.append_page(box)
        self.set_page_title(box, "Processando")
        self.set_page_type(box, Gtk.AssistantPageType.PROGRESS)

    def _build_summary_page(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        box.set_border_width(28)
        
        self.lbl_summary_title = Gtk.Label()
        self.lbl_summary_title.get_style_context().add_class("main-title")
        self.lbl_summary_title.set_halign(Gtk.Align.START)
        box.pack_start(self.lbl_summary_title, False, False, 0)
        
        self.lbl_summary_desc = Gtk.Label()
        self.lbl_summary_desc.get_style_context().add_class("text-body")
        self.lbl_summary_desc.set_halign(Gtk.Align.START)
        box.pack_start(self.lbl_summary_desc, False, False, 0)
        
        self.chk_launch = Gtk.CheckButton(label="Iniciar o OpenWave agora")
        self.chk_launch.set_active(True)
        self.chk_launch.set_margin_top(10)
        box.pack_start(self.chk_launch, False, False, 0)
        
        box.show_all()
        self.append_page(box)
        self.set_page_title(box, "Conclusão")
        self.set_page_type(box, Gtk.AssistantPageType.SUMMARY)

    def forward_page_func(self, current_page, data):
        if current_page == 0:
            if self.rad_uninstall.get_active():
                return 2
            return 1
        return current_page + 1

    def on_browse_clicked(self, widget):
        dialog = Gtk.FileChooserDialog(
            title="Selecione a pasta de destino",
            parent=self,
            action=Gtk.FileChooserAction.SELECT_FOLDER
        )
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK)
        if dialog.run() == Gtk.ResponseType.OK:
            self.ent_dir.set_text(dialog.get_filename())
        dialog.destroy()

    def on_prepare(self, assistant, page):
        current_idx = assistant.get_current_page()
        is_uninstall = self.rad_uninstall.get_active()

        if current_idx == 2:
            self.set_page_complete(page, False)
            if is_uninstall:
                self.set_page_title(page, "Removendo componentes")
                threading.Thread(target=self.execute_uninstallation, daemon=True).start()
            else:
                self.install_dir = Path(self.ent_dir.get_text())
                self.create_shortcut = self.chk_shortcut.get_active()
                self.set_page_title(page, "Instalando arquivos")
                threading.Thread(target=self.execute_installation, daemon=True).start()
                
        elif current_idx == 3:
            if is_uninstall:
                self.lbl_summary_title.set_text("Remoção concluída")
                self.lbl_summary_desc.set_text("O OpenWave foi completamente removido do seu sistema operacional.")
                self.chk_launch.set_visible(False)
            else:
                self.lbl_summary_title.set_text("Pronto para tocar!")
                self.lbl_summary_desc.set_text("A instalação terminou com sucesso. Seus arquivos de áudio já podem ser gerenciados pelo player.")
                self.chk_launch.set_visible(True)

    def execute_installation(self):
        steps = [
            ("Criando árvore de diretórios...", self.step_create_dirs),
            ("Escrevendo binários e módulos...", self.step_copy_files),
            ("Validando subsistema de metadados...", self.step_install_deps),
            ("Registrando manifesto .desktop no sistema...", self.step_create_launcher)
        ]
        total = len(steps)
        for i, (msg, func) in enumerate(steps):
            GLib.idle_add(self.update_progress_ui, i / total, msg)
            try:
                func()
            except Exception as e:
                GLib.idle_add(self.update_progress_ui, i / total, f"Erro fatal: {e}")
                return
        GLib.idle_add(self.update_progress_ui, 1.0, "Configuração concluída.")
        GLib.idle_add(self.set_page_complete, self.get_nth_page(2), True)

    def step_create_dirs(self):
        self.install_dir.mkdir(parents=True, exist_ok=True)

    def step_copy_files(self):
        current_dir = Path(__file__).parent

        src_app = current_dir / "app.py"
        if not src_app.exists():
            raise FileNotFoundError("O arquivo 'app.py' precisa estar na mesma pasta do instalador.")

        src_pkg = current_dir / "openwave"
        if not src_pkg.exists() or not src_pkg.is_dir():
            raise FileNotFoundError("A pasta 'openwave/' precisa estar na mesma pasta do instalador.")

        # Copia app.py
        dest_app = self.install_dir / "app.py"
        dest_app.write_text(src_app.read_text(encoding="utf-8"), encoding="utf-8")
        dest_app.chmod(0o755)

        # Copia o pacote openwave/ (remove versao antiga antes)
        dest_pkg = self.install_dir / "openwave"
        if dest_pkg.exists():
            shutil.rmtree(dest_pkg)
        shutil.copytree(src_pkg, dest_pkg, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

    def step_install_deps(self):
        try:
            import mutagen
            return
        except ImportError:
            pass
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "--user", "mutagen", "--break-system-packages"],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        except Exception:
            raise Exception("Mutagen ausente. Execute manual: sudo apt install python3-mutagen")

    def step_create_launcher(self):
        if not self.create_shortcut:
            return
        apps_dir = Path.home() / ".local" / "share" / "applications"
        apps_dir.mkdir(parents=True, exist_ok=True)
        desktop_file = apps_dir / "openwave.desktop"
        content = f"""[Desktop Entry]
Version=1.0
Type=Application
Name=OpenWave
Comment=Player de música planejado para a estética do tema Mint-Y.
Exec={sys.executable} {self.install_dir}/app.py
Icon=multimedia-audio-player
Terminal=false
Categories=AudioVideo;Audio;Player;GTK;
"""
        desktop_file.write_text(content, encoding="utf-8")
        desktop_file.chmod(0o755)

    def execute_uninstallation(self):
        steps = [
            ("Expurgando atalhos de ambiente (.desktop)...", self.step_remove_launcher),
            ("Removendo arquivos de dados do armazenamento...", self.step_remove_files)
        ]
        total = len(steps)
        for i, (msg, func) in enumerate(steps):
            GLib.idle_add(self.update_progress_ui, i / total, msg)
            try:
                func()
            except Exception as e:
                GLib.idle_add(self.update_progress_ui, i / total, f"Erro na desinstalação: {e}")
                return
        GLib.idle_add(self.update_progress_ui, 1.0, "Remoção concluída.")
        GLib.idle_add(self.set_page_complete, self.get_nth_page(2), True)

    def step_remove_launcher(self):
        desktop_file = Path.home() / ".local" / "share" / "applications" / "openwave.desktop"
        if desktop_file.exists():
            desktop_file.unlink()

    def step_remove_files(self):
        if self.install_dir.exists():
            shutil.rmtree(self.install_dir)

    def update_progress_ui(self, fraction, message):
        self.progress_bar.set_fraction(fraction)
        self.lbl_status.set_text(message)

    def on_cancel(self, assistant):
        self.destroy()
        Gtk.main_quit()

    def on_close(self, assistant):
        if not self.rad_uninstall.get_active() and self.chk_launch.get_active():
            subprocess.Popen([sys.executable, str(self.install_dir / "app.py")])
        self.destroy()
        Gtk.main_quit()

if __name__ == "__main__":
    Gtk.Window.set_default_icon_name("multimedia-audio-player")
    
    app = OpenWaveInstaller()
    Gtk.main()