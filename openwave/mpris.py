from __future__ import annotations

import os

import gi
gi.require_version("GLib", "2.0")
from gi.repository import GLib

try:
    import dbus
    import dbus.service
    from dbus.mainloop.glib import DBusGMainLoop
    DBUS_AVAILABLE = True
except ImportError:
    DBUS_AVAILABLE = False


class MPRISProvider:
    """Gerenciador do MPRIS que encapsula a lógica do DBus de forma segura."""
    
    def __init__(self, window):
        self.window = window
        self.interface = None
        if DBUS_AVAILABLE:
            try:
                DBusGMainLoop(set_as_default=True)
                self.interface = _MPRISInterface(window)
            except Exception as e:
                print(f"Aviso: Não foi possível iniciar o suporte a MPRIS2: {e}")

    def notify_metadata(self):
        if self.interface:
            self.interface.notify_metadata()

    def notify_status(self):
        if self.interface:
            self.interface.notify_status()


if DBUS_AVAILABLE:
    class _MPRISInterface(dbus.service.Object):
        def __init__(self, window):
            self.window = window
            self.bus = dbus.SessionBus()
            
            # O nome do bus deve ser único. Tratamento em caso de múltiplas instâncias abertas.
            bus_name_str = "org.mpris.MediaPlayer2.openwave"
            try:
                self.bus_name = dbus.service.BusName(bus_name_str, self.bus)
            except Exception:
                self.bus_name = dbus.service.BusName(f"{bus_name_str}.instance{os.getpid()}", self.bus)

            super().__init__(self.bus_name, "/org/mpris/MediaPlayer2")

        def notify_status(self):
            status = "Playing" if self.window._player.is_playing else "Paused"
            if not self.window.current_track_path:
                status = "Stopped"
            self.PropertiesChanged('org.mpris.MediaPlayer2.Player', {'PlaybackStatus': dbus.String(status)}, [])

        def notify_metadata(self):
            self.PropertiesChanged('org.mpris.MediaPlayer2.Player', {'Metadata': self._get_metadata()}, [])

        def _get_metadata(self):
            metadata = dbus.Dictionary(signature='sv')
            if not self.window.current_track_path:
                return metadata

            track_id = str(hash(self.window.current_track_path) % 1000000)
            metadata['mpris:trackid'] = dbus.ObjectPath(f"/org/openwave/track/{track_id}")
            metadata['xesam:title'] = dbus.String(self.window.current_title)
            metadata['xesam:artist'] = dbus.Array([dbus.String(self.window.current_artist)], signature='s')
            metadata['xesam:album'] = dbus.String(self.window.current_album)

            dur = self.window._player.current_duration
            if dur:
                metadata['mpris:length'] = dbus.Int64(int(dur * 1000000))

            if hasattr(self.window, 'current_cover_url') and self.window.current_cover_url:
                metadata['mpris:artUrl'] = dbus.String(self.window.current_cover_url)

            return metadata

        # ========================================================
        # org.freedesktop.DBus.Properties
        # ========================================================
        @dbus.service.method(dbus.PROPERTIES_IFACE, in_signature='ss', out_signature='v')
        def Get(self, interface_name, property_name):
            return self.GetAll(interface_name).get(property_name, None)

        @dbus.service.method(dbus.PROPERTIES_IFACE, in_signature='s', out_signature='a{sv}')
        def GetAll(self, interface_name):
            if interface_name == 'org.mpris.MediaPlayer2':
                return {
                    'CanQuit': dbus.Boolean(True),
                    'CanRaise': dbus.Boolean(True),
                    'HasTrackList': dbus.Boolean(False),
                    'Identity': dbus.String('OpenWave'),
                    'DesktopEntry': dbus.String('openwave'),
                    'SupportedUriSchemes': dbus.Array(['file'], signature='s'),
                    'SupportedMimeTypes': dbus.Array(['audio/mpeg', 'audio/x-wav', 'audio/flac', 'audio/ogg'], signature='s'),
                }
            elif interface_name == 'org.mpris.MediaPlayer2.Player':
                status = "Playing" if self.window._player.is_playing else "Paused"
                if not self.window.current_track_path:
                    status = "Stopped"

                return {
                    'PlaybackStatus': dbus.String(status),
                    'LoopStatus': dbus.String('None'),
                    'Rate': dbus.Double(1.0),
                    'Shuffle': dbus.Boolean(self.window.is_shuffle),
                    'Metadata': self._get_metadata(),
                    'Volume': dbus.Double(1.0),
                    'Position': dbus.Int64(self.window._player.get_position_us()),
                    'MinimumRate': dbus.Double(1.0),
                    'MaximumRate': dbus.Double(1.0),
                    'CanGoNext': dbus.Boolean(True),
                    'CanGoPrevious': dbus.Boolean(True),
                    'CanPlay': dbus.Boolean(True),
                    'CanPause': dbus.Boolean(True),
                    'CanSeek': dbus.Boolean(False),
                    'CanControl': dbus.Boolean(True),
                }
            return {}

        @dbus.service.signal(dbus.PROPERTIES_IFACE, signature='sa{sv}as')
        def PropertiesChanged(self, interface_name, changed_properties, invalidated_properties):
            pass

        # ========================================================
        # org.mpris.MediaPlayer2
        # ========================================================
        @dbus.service.method('org.mpris.MediaPlayer2', in_signature='', out_signature='')
        def Raise(self):
            GLib.idle_add(self.window.present)

        @dbus.service.method('org.mpris.MediaPlayer2', in_signature='', out_signature='')
        def Quit(self):
            GLib.idle_add(self.window.destroy)

        # ========================================================
        # org.mpris.MediaPlayer2.Player
        # ========================================================
        @dbus.service.method('org.mpris.MediaPlayer2.Player', in_signature='', out_signature='')
        def Next(self):
            GLib.idle_add(self.window.on_next_clicked, None)

        @dbus.service.method('org.mpris.MediaPlayer2.Player', in_signature='', out_signature='')
        def Previous(self):
            GLib.idle_add(self.window.on_prev_clicked, None)

        @dbus.service.method('org.mpris.MediaPlayer2.Player', in_signature='', out_signature='')
        def Pause(self):
            if self.window._player.is_playing:
                GLib.idle_add(self.window.on_play_clicked, None)

        @dbus.service.method('org.mpris.MediaPlayer2.Player', in_signature='', out_signature='')
        def PlayPause(self):
            GLib.idle_add(self.window.on_play_clicked, None)

        @dbus.service.method('org.mpris.MediaPlayer2.Player', in_signature='', out_signature='')
        def Play(self):
            if not self.window._player.is_playing:
                GLib.idle_add(self.window.on_play_clicked, None)

        @dbus.service.method('org.mpris.MediaPlayer2.Player', in_signature='', out_signature='')
        def Stop(self):
            GLib.idle_add(self.window.stop_playback)