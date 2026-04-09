"""Overlay system for stream ads, messages, and product promotions."""

import json
import os
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageDraw, ImageFont

PROJECT_DIR = Path(__file__).parent
OVERLAYS_DIR = PROJECT_DIR / "overlays"
IMAGES_DIR = OVERLAYS_DIR / "images"
CONFIG_FILE = OVERLAYS_DIR / "config.json"
CURRENT_OVERLAY = OVERLAYS_DIR / "current.png"
EMPTY_OVERLAY = OVERLAYS_DIR / "empty.png"

STREAM_WIDTH = 1920
STREAM_HEIGHT = 1080

_lock = threading.Lock()

# ── Overlay Style Presets ────────────────────────────────────────────────────

OVERLAY_STYLES = {
    "elegant_gold": {
        "name": "Elegant Gold",
        "bg": (10, 5, 30, 200),
        "border": (212, 168, 67, 230),
        "text_color": (255, 225, 150, 255),
        "shadow_color": (0, 0, 0, 150),
        "accent": (212, 168, 67, 180),
        "border_width": 2,
    },
    "neon_purple": {
        "name": "Neon Purple",
        "bg": (20, 5, 40, 210),
        "border": (180, 100, 240, 255),
        "text_color": (230, 180, 255, 255),
        "shadow_color": (80, 20, 120, 100),
        "accent": (180, 100, 240, 200),
        "border_width": 3,
    },
    "ocean_blue": {
        "name": "Ocean Blue",
        "bg": (5, 15, 40, 200),
        "border": (70, 160, 230, 220),
        "text_color": (180, 220, 255, 255),
        "shadow_color": (0, 10, 30, 150),
        "accent": (70, 160, 230, 180),
        "border_width": 2,
    },
    "rose_garden": {
        "name": "Rose Garden",
        "bg": (30, 5, 15, 200),
        "border": (220, 100, 140, 230),
        "text_color": (255, 200, 220, 255),
        "shadow_color": (40, 0, 10, 150),
        "accent": (220, 100, 140, 180),
        "border_width": 2,
    },
    "enchanted_forest": {
        "name": "Enchanted Forest",
        "bg": (5, 25, 15, 200),
        "border": (100, 200, 120, 220),
        "text_color": (200, 255, 210, 255),
        "shadow_color": (0, 15, 5, 150),
        "accent": (100, 200, 120, 180),
        "border_width": 2,
    },
    "cinematic_dark": {
        "name": "Cinematic Dark",
        "bg": (0, 0, 0, 220),
        "border": (60, 60, 60, 200),
        "text_color": (240, 240, 240, 255),
        "shadow_color": (0, 0, 0, 200),
        "accent": (100, 100, 100, 150),
        "border_width": 1,
    },
    "sunset_warm": {
        "name": "Sunset Warm",
        "bg": (35, 10, 5, 200),
        "border": (240, 160, 60, 230),
        "text_color": (255, 230, 180, 255),
        "shadow_color": (30, 5, 0, 150),
        "accent": (240, 160, 60, 180),
        "border_width": 2,
    },
}


def _ensure_dirs():
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)


def _load_font(size):
    for fp in ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
               "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]:
        if os.path.exists(fp):
            return ImageFont.truetype(fp, size)
    return ImageFont.load_default()


def _create_empty_overlay():
    """Create a transparent 1920x1080 PNG."""
    _ensure_dirs()
    img = Image.new("RGBA", (STREAM_WIDTH, STREAM_HEIGHT), (0, 0, 0, 0))
    img.save(str(EMPTY_OVERLAY), "PNG")
    # Also set as current
    img.save(str(CURRENT_OVERLAY), "PNG")


def init():
    """Initialize overlay system."""
    _ensure_dirs()
    if not EMPTY_OVERLAY.exists():
        _create_empty_overlay()
    if not CURRENT_OVERLAY.exists():
        _create_empty_overlay()


def _load_config():
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"overlays": []}


def _save_config(data):
    _ensure_dirs()
    CONFIG_FILE.write_text(json.dumps(data, indent=2) + "\n")


def render_overlay(overlay):
    """Render an overlay definition to a transparent PNG image."""
    img = Image.new("RGBA", (STREAM_WIDTH, STREAM_HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    otype = overlay.get("type", "text_banner")
    position = overlay.get("position", "bottom")
    text = overlay.get("text", "")
    style_id = overlay.get("style", "elegant_gold")
    style = OVERLAY_STYLES.get(style_id, OVERLAY_STYLES["elegant_gold"])

    # Semi-transparent background bar
    bar_height = 80
    bar_y = STREAM_HEIGHT - bar_height - 40  # 40px from bottom
    if position == "top":
        bar_y = 40

    # Draw background bar with style colors
    bar_bg = Image.new("RGBA", (STREAM_WIDTH, bar_height), (0, 0, 0, 0))
    bar_draw = ImageDraw.Draw(bar_bg)
    bar_draw.rectangle([0, 0, STREAM_WIDTH, bar_height], fill=style["bg"])
    # Border lines
    bw = style["border_width"]
    bar_draw.line([(0, 0), (STREAM_WIDTH, 0)], fill=style["border"], width=bw)
    bar_draw.line([(0, bar_height - 1), (STREAM_WIDTH, bar_height - 1)],
                  fill=style["border"], width=bw)
    img.paste(bar_bg, (0, bar_y), bar_bg)

    text_color = style["text_color"]
    shadow_color = style["shadow_color"]

    if otype == "text_banner":
        font = _load_font(32)
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        tx = (STREAM_WIDTH - tw) // 2
        ty = bar_y + (bar_height - 32) // 2
        draw.text((tx + 2, ty + 2), text, fill=shadow_color, font=font)
        draw.text((tx, ty), text, fill=text_color, font=font)

    elif otype == "image_text":
        image_file = overlay.get("image", "")
        image_path = IMAGES_DIR / image_file

        text_x = 60
        if image_file and image_path.exists():
            try:
                product_img = Image.open(str(image_path)).convert("RGBA")
                thumb_h = bar_height - 16
                aspect = product_img.width / product_img.height
                thumb_w = int(thumb_h * aspect)
                product_img = product_img.resize((thumb_w, thumb_h), Image.LANCZOS)

                paste_x = 30
                paste_y = bar_y + 8
                img.paste(product_img, (paste_x, paste_y), product_img)
                text_x = paste_x + thumb_w + 20
            except Exception:
                pass

        font = _load_font(28)
        ty = bar_y + (bar_height - 28) // 2
        draw.text((text_x + 2, ty + 2), text, fill=shadow_color, font=font)
        draw.text((text_x, ty), text, fill=text_color, font=font)

    elif otype == "full_banner":
        image_file = overlay.get("image", "")
        image_path = IMAGES_DIR / image_file
        if image_file and image_path.exists():
            try:
                banner = Image.open(str(image_path)).convert("RGBA")
                banner = banner.resize((STREAM_WIDTH - 60, bar_height - 8), Image.LANCZOS)
                img.paste(banner, (30, bar_y + 4), banner)
            except Exception:
                pass

    # Add sparkle decorations with style accent color
    _add_sparkles(draw, bar_y, bar_height, style["accent"])

    return img


def _add_sparkles(draw, bar_y, bar_height, star_color=(212, 168, 67, 180)):
    """Add small star decorations near the overlay bar."""
    positions = [(15, bar_y - 8), (STREAM_WIDTH - 25, bar_y - 8),
                 (15, bar_y + bar_height + 3), (STREAM_WIDTH - 25, bar_y + bar_height + 3)]
    for x, y in positions:
        for size in [4, 2]:
            draw.ellipse([x - size, y - size, x + size, y + size], fill=star_color)


def _atomic_write_png(img, path):
    """Write PNG atomically via temp file + rename."""
    tmp = str(path) + ".tmp"
    img.save(tmp, "PNG")
    os.replace(tmp, str(path))


def set_current(overlay):
    """Render and set the current overlay."""
    img = render_overlay(overlay)
    _atomic_write_png(img, CURRENT_OVERLAY)


def clear_current():
    """Clear overlay to transparent."""
    if EMPTY_OVERLAY.exists():
        img = Image.open(str(EMPTY_OVERLAY))
        _atomic_write_png(img, CURRENT_OVERLAY)
    else:
        _create_empty_overlay()


# ── CRUD operations ──────────────────────────────────────────────────────────

def list_overlays():
    config = _load_config()
    return config.get("overlays", [])


def get_overlay(overlay_id):
    for o in list_overlays():
        if o["id"] == overlay_id:
            return o
    return None


def create_overlay(otype, text="", image="", position="bottom",
                   duration_sec=15, interval_sec=300, style="elegant_gold"):
    overlay = {
        "id": uuid4().hex[:8],
        "type": otype,
        "text": text,
        "image": image,
        "position": position,
        "style": style,
        "duration_sec": duration_sec,
        "interval_sec": interval_sec,
        "enabled": True,
        "created": datetime.now().isoformat(timespec="seconds"),
    }
    with _lock:
        config = _load_config()
        config["overlays"].append(overlay)
        _save_config(config)
    return overlay


def update_overlay(overlay_id, **kwargs):
    with _lock:
        config = _load_config()
        for o in config["overlays"]:
            if o["id"] == overlay_id:
                for k, v in kwargs.items():
                    if k != "id":
                        o[k] = v
                _save_config(config)
                return o
    return None


def delete_overlay(overlay_id):
    with _lock:
        config = _load_config()
        overlay = next((o for o in config["overlays"] if o["id"] == overlay_id), None)
        if not overlay:
            return False
        # Remove associated image if it exists
        if overlay.get("image"):
            img_path = IMAGES_DIR / overlay["image"]
            if img_path.exists():
                img_path.unlink()
        config["overlays"] = [o for o in config["overlays"] if o["id"] != overlay_id]
        _save_config(config)
    return True


def toggle_overlay(overlay_id):
    with _lock:
        config = _load_config()
        for o in config["overlays"]:
            if o["id"] == overlay_id:
                o["enabled"] = not o["enabled"]
                _save_config(config)
                return o["enabled"]
    return None


def save_uploaded_image(file_storage):
    """Save an uploaded image file. Returns the filename."""
    _ensure_dirs()
    ext = Path(file_storage.filename).suffix or ".png"
    filename = f"{uuid4().hex[:8]}{ext}"
    dest = IMAGES_DIR / filename
    file_storage.save(str(dest))
    return filename


# ── Overlay scheduler thread ────────────────────────────────────────────────

class OverlayScheduler:
    """Background thread that cycles through enabled overlays on schedule."""

    def __init__(self):
        self._thread = None
        self._stop = threading.Event()
        self._running = False

    def start(self):
        if self._running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._running = True

    def stop(self):
        self._stop.set()
        self._running = False

    @property
    def running(self):
        return self._running

    def _run(self):
        init()
        while not self._stop.is_set():
            overlays = [o for o in list_overlays() if o.get("enabled", True)]
            if not overlays:
                clear_current()
                self._stop.wait(10)
                continue

            for overlay in overlays:
                if self._stop.is_set():
                    break

                # Show this overlay
                set_current(overlay)
                show_time = overlay.get("duration_sec", 15)
                self._stop.wait(show_time)
                if self._stop.is_set():
                    break

                # Clear and wait for interval
                clear_current()
                gap = overlay.get("interval_sec", 300) - show_time
                if gap > 0:
                    self._stop.wait(gap)

        clear_current()
