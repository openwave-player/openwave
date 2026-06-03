from __future__ import annotations

import os
from pathlib import Path

APP_VERSION = "0.1.3"
GITHUB_RELEASES_API = "https://api.github.com/repos/openwave-player/openwave/releases/latest"
DOWNLOAD_URL_TEMPLATE = "https://raw.githubusercontent.com/openwave-player/openwave/{tag}/app.py"

# Caminho absoluto resolvido UMA VEZ quando o módulo é carregado.
SCRIPT_PATH = Path(os.path.abspath(__file__)).parent / "app.py"

AUDIO_EXTENSIONS = {
    ".mp3",
    ".wav",
    ".ogg",
    ".flac",
    ".m4a",
    ".aac",
    ".opus",
    ".wma",
    ".aiff",
    ".aif",
    ".alac",
    ".mp2",
    ".mka",
}
