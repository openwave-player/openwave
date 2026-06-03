from __future__ import annotations

from pathlib import Path

from mutagen import File as MutagenFile


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def normalize_text(value: object, fallback: str) -> str:
    if value is None:
        return fallback
    if isinstance(value, (list, tuple)):
        if not value:
            return fallback
        value = value[0]
    if isinstance(value, bytes):
        value = value.decode("utf-8", "ignore")
    text = str(value).strip()
    return text or fallback


def read_audio_metadata(path: str) -> dict:
    file_path = Path(path)
    title = file_path.stem or "Faixa sem nome"
    artist = "Artista desconhecido"
    album = "Álbum desconhecido"
    duration = 0.0
    cover_data = None

    try:
        easy_file = MutagenFile(path, easy=True)
        if easy_file:
            title = normalize_text(easy_file.get("title"), title)
            artist = normalize_text(easy_file.get("artist"), artist)
            album = normalize_text(easy_file.get("album"), album)

        full_file = MutagenFile(path)
        if full_file is not None:
            info = getattr(full_file, "info", None)
            if info is not None:
                duration = float(getattr(info, "length", 0.0) or 0.0)

            tags = getattr(full_file, "tags", None)
            if tags:
                pictures = []
                getall = getattr(tags, "getall", None)
                if callable(getall):
                    try:
                        pictures = getall("APIC")
                    except Exception:
                        pictures = []

                if pictures:
                    cover_data = getattr(pictures[0], "data", None)

                if cover_data is None and hasattr(tags, "pictures"):
                    pics = getattr(tags, "pictures", [])
                    if pics:
                        cover_data = getattr(pics[0], "data", None)

                if cover_data is None:
                    covr = tags.get("covr")
                    if covr:
                        try:
                            cover_data = bytes(covr[0])
                        except Exception:
                            pass
    except Exception:
        pass

    return {
        "path": str(file_path),
        "title": title,
        "artist": artist,
        "album": album.strip() or "Álbum desconhecido",
        "duration": duration,
        "cover_data": cover_data,
    }


def parse_version(v: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in v.lstrip("v").split("."))
    except Exception:
        return (0,)
