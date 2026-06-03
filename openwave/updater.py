from __future__ import annotations

import json
import os
import sys
import threading
import urllib.request
import zipfile
import shutil
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk

from .constants import APP_VERSION, GITHUB_RELEASES_API, DOWNLOAD_URL_TEMPLATE, SCRIPT_PATH
from .utils import parse_version


def check_for_updates(on_update_available) -> None:
    """Verifica novas versões em background e chama on_update_available na thread GTK."""

    def _run():
        try:
            req = urllib.request.Request(
                GITHUB_RELEASES_API,
                headers={"User-Agent": f"OpenWave/{APP_VERSION}"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())

            tag = data.get("tag_name", "").strip()
            if not tag:
                return

            if parse_version(tag) > parse_version(APP_VERSION):
                download_url = DOWNLOAD_URL_TEMPLATE.format(tag=tag)
                GLib.idle_add(on_update_available, tag, download_url)
        except Exception:
            pass

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()


def download_and_restart(parent_window: Gtk.Window, tag: str, download_url: str) -> None:
    """Baixa a nova versão compactada (ZIP), extrai substituindo o app antigo e reinicia."""
    print(f"[update] download_and_restart chamado: tag={tag}")
    print(f"[update] SCRIPT_PATH={SCRIPT_PATH}")
    print(f"[update] download_url={download_url}")

    progress_dialog = Gtk.Dialog(
        title="Atualizando OpenWave…",
        transient_for=parent_window,
        modal=True,
    )
    progress_dialog.set_deletable(False)
    progress_dialog.set_default_size(360, -1)
    content = progress_dialog.get_content_area()
    content.set_border_width(18)
    content.set_spacing(12)

    lbl = Gtk.Label(label=f"Baixando versão {tag}…")
    lbl.set_halign(Gtk.Align.START)
    content.pack_start(lbl, False, False, 0)

    spinner = Gtk.Spinner()
    spinner.start()
    content.pack_start(spinner, False, False, 0)
    progress_dialog.show_all()

    def _do_download():
        print("[update] _do_download iniciou")
        try:
            req = urllib.request.Request(
                download_url,
                headers={"User-Agent": f"OpenWave/{APP_VERSION}"},
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                zip_data = resp.read()

            root_dir = SCRIPT_PATH.parent  # Direitório raiz: ~/.local/share/openwave
            zip_tmp = root_dir / "update.zip"
            
            # 1. Salva o arquivo ZIP temporariamente na pasta raiz
            zip_tmp.write_bytes(zip_data)

            # 2. Cria uma pasta temporária isolada para extração
            extract_to = root_dir / "tmp_update"
            if extract_to.exists():
                shutil.rmtree(extract_to)

            with zipfile.ZipFile(zip_tmp) as z:
                z.extractall(extract_to)

            # O GitHub compacta o repositório dentro de uma subpasta chamada "openwave-{tag}"
            extracted_folder = next(extract_to.glob("openwave-*"))

            # 3. Move e mescla todos os arquivos extraídos para o diretório oficial do app
            for item in extracted_folder.iterdir():
                dest = root_dir / item.name
                if item.is_dir():
                    # dirs_exist_ok=True garante a mesclagem segura de arquivos sem deletar a pasta ativa
                    shutil.copytree(item, dest, dirs_exist_ok=True)
                else:
                    shutil.copy2(item, dest)

            # 4. Limpeza dos resíduos temporários de instalação
            zip_tmp.unlink(missing_ok=True)
            shutil.rmtree(extract_to, ignore_errors=True)

            GLib.idle_add(_finish_ok)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            GLib.idle_add(_finish_error, str(exc))

    def _finish_ok():
        print("[update] _finish_ok chamado")
        progress_dialog.destroy()
        
        # Limpeza de caches antigos de compilação (__pycache__) para evitar conflitos de leitura
        pycache_root = SCRIPT_PATH.parent / "__pycache__"
        if pycache_root.exists():
            shutil.rmtree(pycache_root, ignore_errors=True)
            
        pycache_module = SCRIPT_PATH.parent / "openwave" / "__pycache__"
        if pycache_module.exists():
            shutil.rmtree(pycache_module, ignore_errors=True)
            
        pyc = SCRIPT_PATH.with_suffix(".pyc")
        if pyc.exists():
            pyc.unlink(missing_ok=True)
            
        print(f"[update] execv: {sys.executable} {SCRIPT_PATH}")
        print(f"[update] arquivo existe: {SCRIPT_PATH.exists()}, tamanho: {SCRIPT_PATH.stat().st_size} bytes")
        
        # Substitui o processo atual pelo app.py atualizado na raiz
        os.execv(sys.executable, [sys.executable, str(SCRIPT_PATH)])
        return False

    def _finish_error(msg: str):
        progress_dialog.destroy()
        err = Gtk.MessageDialog(
            transient_for=parent_window,
            modal=True,
            message_type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            text="Falha ao atualizar",
        )
        err.format_secondary_text(msg)
        err.run()
        err.destroy()
        return False

    thread = threading.Thread(target=_do_download, daemon=False)
    thread.start()