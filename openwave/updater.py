from __future__ import annotations

import json
import os
import sys
import threading
import urllib.request
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
    """Baixa a nova versão e reinicia o aplicativo."""
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
                new_source = resp.read()

            tmp_path = SCRIPT_PATH.with_suffix(".tmp")
            tmp_path.write_bytes(new_source)
            tmp_path.replace(SCRIPT_PATH)

            GLib.idle_add(_finish_ok)
        except Exception as exc:
            import traceback
            traceback.print_exc()
            GLib.idle_add(_finish_error, str(exc))

    def _finish_ok():
        print("[update] _finish_ok chamado")
        progress_dialog.destroy()
        import shutil
        pycache = SCRIPT_PATH.parent / "__pycache__"
        if pycache.exists():
            shutil.rmtree(pycache, ignore_errors=True)
        pyc = SCRIPT_PATH.with_suffix(".pyc")
        if pyc.exists():
            pyc.unlink(missing_ok=True)
        print(f"[update] execv: {sys.executable} {SCRIPT_PATH}")
        print(f"[update] arquivo existe: {SCRIPT_PATH.exists()}, tamanho: {SCRIPT_PATH.stat().st_size} bytes")
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
