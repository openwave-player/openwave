from __future__ import annotations

from pathlib import Path

import gi

gi.require_version("Gst", "1.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gst, Gtk

from .utils import read_audio_metadata


class Player:
    """Encapsula o pipeline GStreamer e a lógica de reprodução."""

    def __init__(self):
        Gst.init(None)
        self._pipeline = Gst.ElementFactory.make("playbin", "player")
        if not self._pipeline:
            raise RuntimeError("Não foi possível iniciar o GStreamer playbin.")

        self.is_playing = False
        self.current_duration = 0.0
        self._timer_id = None

        # Callbacks definidos externamente
        self.on_tag_found_cb = None
        self.on_eos_cb = None
        self.on_error_cb = None
        self.on_progress_cb = None

        bus = self._pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message::tag", self._on_tag_message)
        bus.connect("message::eos", self._on_eos_message)
        bus.connect("message::error", self._on_error_message)

    # ------------------------------------------------------------------
    # Mensagens do bus GStreamer
    # ------------------------------------------------------------------

    def _on_tag_message(self, bus, message) -> None:
        if self.on_tag_found_cb:
            self.on_tag_found_cb(bus, message)

    def _on_eos_message(self, bus, message) -> None:
        if self.on_eos_cb:
            self.on_eos_cb(bus, message)

    def _on_error_message(self, bus, message) -> None:
        if self.on_error_cb:
            self.on_error_cb(bus, message)

    # ------------------------------------------------------------------
    # Controle de reprodução
    # ------------------------------------------------------------------

    def play_uri(self, path: str) -> None:
        self._pipeline.set_state(Gst.State.NULL)
        self._pipeline.set_property("uri", GLib.filename_to_uri(path, None))
        self._pipeline.set_state(Gst.State.PLAYING)
        self.is_playing = True
        if self._timer_id is None and self.on_progress_cb:
            self._timer_id = GLib.timeout_add(1000, self._tick)

    def pause_or_resume(self) -> None:
        if self.is_playing:
            self._pipeline.set_state(Gst.State.PAUSED)
        else:
            self._pipeline.set_state(Gst.State.PLAYING)
        self.is_playing = not self.is_playing

    def stop(self) -> None:
        self._pipeline.set_state(Gst.State.NULL)
        self.is_playing = False
        self._cancel_timer()

    def null(self) -> None:
        """Apenas coloca em NULL sem modificar is_playing (usado no destroy)."""
        try:
            self._pipeline.set_state(Gst.State.NULL)
        except Exception:
            pass
            
    def get_position_us(self) -> int:
        """Retorna a posição atual em microssegundos (usado pelo MPRIS)."""
        if not self.is_playing:
            return 0
        try:
            suc, pos = self._pipeline.query_position(Gst.Format.TIME)
            if suc and pos > 0:
                # Gst.Format.TIME retorna nanossegundos, converter para microssegundos
                return int(pos // 1000)
        except Exception:
            pass
        return 0

    # ------------------------------------------------------------------
    # Progresso
    # ------------------------------------------------------------------

    def _tick(self) -> bool:
        if not self.is_playing:
            return True
        try:
            suc_pos, pos = self._pipeline.query_position(Gst.Format.TIME)
            suc_dur, dur = self._pipeline.query_duration(Gst.Format.TIME)
            if suc_pos and suc_dur and dur > 0:
                fraction = min(max(pos / dur, 0.0), 1.0)
                pos_s = pos / Gst.SECOND
                dur_s = dur / Gst.SECOND
                self.current_duration = dur_s
                if self.on_progress_cb:
                    self.on_progress_cb(fraction, pos_s, dur_s)
        except Exception:
            pass
        return True

    def _cancel_timer(self) -> None:
        if self._timer_id is not None:
            GLib.source_remove(self._timer_id)
            self._timer_id = None