"""Asset library - persistent storage for generated videos."""

import json
import os
import random
import shutil
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from uuid import uuid4

PROJECT_DIR = Path(__file__).parent
LIBRARY_DIR = PROJECT_DIR / "library"
VIDEOS_DIR = LIBRARY_DIR / "videos"
THUMBS_DIR = LIBRARY_DIR / "thumbnails"
CATALOG_FILE = LIBRARY_DIR / "catalog.json"

_lock = threading.Lock()


def _ensure_dirs():
    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    THUMBS_DIR.mkdir(parents=True, exist_ok=True)


def _load_catalog():
    if CATALOG_FILE.exists():
        try:
            return json.loads(CATALOG_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return []


def _save_catalog(entries):
    _ensure_dirs()
    CATALOG_FILE.write_text(json.dumps(entries, indent=2) + "\n")


def _generate_thumbnail(video_path, thumb_path):
    """Extract first frame as thumbnail."""
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(video_path),
             "-vframes", "1", "-s", "320x180",
             "-q:v", "5", str(thumb_path)],
            capture_output=True, timeout=30
        )
    except Exception:
        pass


def add(video_path, song="", movie="", style="", generator="piano"):
    """Add a video to the library. Moves the file and generates a thumbnail."""
    _ensure_dirs()
    asset_id = uuid4().hex[:8]
    ext = Path(video_path).suffix or ".mp4"
    dest = VIDEOS_DIR / f"{asset_id}{ext}"
    thumb = THUMBS_DIR / f"{asset_id}.jpg"

    shutil.move(str(video_path), str(dest))
    _generate_thumbnail(dest, thumb)

    file_size = dest.stat().st_size / (1024 * 1024)

    # Get duration via ffprobe
    duration = 0.0
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json",
             "-show_format", str(dest)],
            capture_output=True, text=True, timeout=15
        )
        info = json.loads(result.stdout)
        duration = float(info.get("format", {}).get("duration", 0))
    except Exception:
        pass

    entry = {
        "id": asset_id,
        "song": song,
        "movie": movie,
        "style": style,
        "generator": generator,
        "duration_sec": round(duration, 1),
        "file_size_mb": round(file_size, 1),
        "created": datetime.now().isoformat(timespec="seconds"),
        "enabled": True,
    }

    with _lock:
        catalog = _load_catalog()
        catalog.append(entry)
        _save_catalog(catalog)

    return entry


def remove(asset_id):
    """Delete an asset from the library."""
    with _lock:
        catalog = _load_catalog()
        entry = next((e for e in catalog if e["id"] == asset_id), None)
        if not entry:
            return False
        catalog = [e for e in catalog if e["id"] != asset_id]
        _save_catalog(catalog)

    video = VIDEOS_DIR / f"{asset_id}.mp4"
    thumb = THUMBS_DIR / f"{asset_id}.jpg"
    for f in [video, thumb]:
        if f.exists():
            f.unlink()
    return True


def toggle(asset_id):
    """Toggle enabled/disabled for an asset."""
    with _lock:
        catalog = _load_catalog()
        for entry in catalog:
            if entry["id"] == asset_id:
                entry["enabled"] = not entry["enabled"]
                _save_catalog(catalog)
                return entry["enabled"]
    return None


def list_assets(generator=None, enabled_only=False):
    """List library assets with optional filtering."""
    catalog = _load_catalog()
    if generator:
        catalog = [e for e in catalog if e["generator"] == generator]
    if enabled_only:
        catalog = [e for e in catalog if e.get("enabled", True)]
    return catalog


def get_asset(asset_id):
    """Get a single asset entry."""
    catalog = _load_catalog()
    return next((e for e in catalog if e["id"] == asset_id), None)


def get_video_path(asset_id):
    """Get the filesystem path for an asset's video."""
    path = VIDEOS_DIR / f"{asset_id}.mp4"
    return str(path) if path.exists() else None


def get_thumb_path(asset_id):
    """Get the filesystem path for an asset's thumbnail."""
    path = THUMBS_DIR / f"{asset_id}.jpg"
    return str(path) if path.exists() else None


def get_playlist(shuffle=True):
    """Get list of enabled video paths for streaming."""
    assets = list_assets(enabled_only=True)
    if shuffle:
        random.shuffle(assets)
    return [str(VIDEOS_DIR / f"{a['id']}.mp4") for a in assets
            if (VIDEOS_DIR / f"{a['id']}.mp4").exists()]


def stats():
    """Library statistics."""
    catalog = _load_catalog()
    enabled = [e for e in catalog if e.get("enabled", True)]
    total_duration = sum(e.get("duration_sec", 0) for e in enabled)
    total_size = sum(e.get("file_size_mb", 0) for e in catalog)

    by_generator = {}
    for e in catalog:
        g = e.get("generator", "unknown")
        by_generator[g] = by_generator.get(g, 0) + 1

    return {
        "total": len(catalog),
        "enabled": len(enabled),
        "total_duration_sec": round(total_duration, 1),
        "total_duration_min": round(total_duration / 60, 1),
        "total_size_mb": round(total_size, 1),
        "by_generator": by_generator,
    }
