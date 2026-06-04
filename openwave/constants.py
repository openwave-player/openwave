from __future__ import annotations

import os
from pathlib import Path

# Versão do aplicativo
APP_VERSION = "0.1.4"

# APIs e Endpoints do GitHub para Atualização
GITHUB_RELEASES_API = "https://api.github.com/repos/openwave-player/openwave/releases/latest"
DOWNLOAD_URL_TEMPLATE = "https://github.com/openwave-player/openwave/archive/refs/tags/{tag}.zip"


SCRIPT_PATH = Path(os.path.abspath(__file__)).parent.parent / "app.py"


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