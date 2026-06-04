#!/usr/bin/env python3

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