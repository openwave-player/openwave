#!/usr/bin/env python3
"""
OpenWave — ponto de entrada principal.

Este arquivo é mantido para compatibilidade com o script de instalação
e com o mecanismo de auto-atualização (que reescreve este arquivo).
"""
from __future__ import annotations

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk

from openwave.window import OpenWave


if __name__ == "__main__":
    Gtk.Window.set_default_icon_name("multimedia-audio-player")
    window = OpenWave()
    window.connect("destroy", Gtk.main_quit)
    Gtk.main()
