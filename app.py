"""Disney Piano Stream — Web Application."""

import json
import os
import queue
import time
from pathlib import Path

from flask import (Flask, Response, jsonify, redirect, render_template,
                   request, send_file, url_for)

import config
import library
import overlays
from generate import DISNEY_SONGS, VARIATION_STYLES, VIDEO_THEMES
from generate_music import DISNEY_STYLES as ACE_STEP_STYLES
from generate_music_musicgen import DISNEY_STYLES as MUSICGEN_STYLES
from generate_music_suno import DISNEY_STYLES_SUNO as SUNO_STYLES
from stream_manager import StreamManager
from worker import GenerationWorker

app = Flask(__name__)
app.secret_key = config.get("FLASK_SECRET_KEY", "disney-stream-secret-key")

# Global instances
worker = GenerationWorker()
stream_mgr = StreamManager()
overlay_scheduler = overlays.OverlayScheduler()


# ── Dashboard ────────────────────────────────────────────────────────────────

@app.route("/")
def dashboard():
    recent = library.list_assets()
    recent.sort(key=lambda a: a.get("created", ""), reverse=True)
    return render_template("dashboard.html",
                           stream=stream_mgr.get_status(),
                           current_task=worker.current_task,
                           queue_size=worker.queue_size,
                           history=list(reversed(worker.history[-10:])),
                           lib_stats=library.stats(),
                           recent_assets=recent[:8])


# ── Generate ─────────────────────────────────────────────────────────────────

@app.route("/generate")
def generate_page():
    return render_template("generate.html",
                           disney_songs=DISNEY_SONGS,
                           variation_styles=VARIATION_STYLES,
                           video_themes=VIDEO_THEMES,
                           ace_step_styles=ACE_STEP_STYLES,
                           musicgen_styles=MUSICGEN_STYLES,
                           suno_styles=SUNO_STYLES)


@app.route("/generate", methods=["POST"])
def generate_submit():
    generator = request.form.get("generator", "piano")

    if generator == "piano":
        song_idx = request.form.get("song", "")
        style_idx = request.form.get("style", "")
        theme = request.form.get("theme", "midnight_blue")
        song = movie = ""
        if song_idx and song_idx != "random":
            idx = int(song_idx)
            song, movie = DISNEY_SONGS[idx]
        if style_idx and style_idx != "random":
            style = VARIATION_STYLES[int(style_idx)]
        else:
            style = ""

        count = int(request.form.get("count", 1))
        for _ in range(count):
            worker.enqueue("piano", song=song, movie=movie, style=style,
                           **{"extra": {"theme": theme}})

    elif generator == "ace_step":
        style_id = request.form.get("ace_step_style", "enchanted_kingdom")
        worker.enqueue("ace_step", extra_style_id=style_id,
                       **{"extra": {"style_id": style_id}})

    elif generator == "musicgen":
        style_id = request.form.get("musicgen_style", "enchanted_kingdom")
        model = request.form.get("musicgen_model", "medium")
        worker.enqueue("musicgen",
                       **{"extra": {"style_id": style_id, "model": model}})

    elif generator == "suno":
        style_id = request.form.get("suno_style", "enchanted_kingdom")
        worker.enqueue("suno", **{"extra": {"style_id": style_id}})

    return redirect(url_for("dashboard"))


# ── Library ──────────────────────────────────────────────────────────────────

@app.route("/library")
def library_page():
    gen_filter = request.args.get("generator", "")
    assets = library.list_assets(generator=gen_filter if gen_filter else None)
    return render_template("library.html",
                           assets=assets,
                           stats=library.stats(),
                           current_filter=gen_filter)


@app.route("/library/toggle/<asset_id>", methods=["POST"])
def library_toggle(asset_id):
    library.toggle(asset_id)
    return redirect(url_for("library_page"))


@app.route("/library/delete/<asset_id>", methods=["POST"])
def library_delete(asset_id):
    library.remove(asset_id)
    return redirect(url_for("library_page"))


@app.route("/library/video/<asset_id>")
def library_video(asset_id):
    path = library.get_video_path(asset_id)
    if path and os.path.exists(path):
        return send_file(path, mimetype="video/mp4")
    return "Not found", 404


@app.route("/library/thumb/<asset_id>")
def library_thumb(asset_id):
    path = library.get_thumb_path(asset_id)
    if path and os.path.exists(path):
        return send_file(path, mimetype="image/jpeg")
    # Return a placeholder
    return "", 204


# ── Overlays ─────────────────────────────────────────────────────────────────

@app.route("/overlays")
def overlays_page():
    return render_template("overlays.html",
                           overlays=overlays.list_overlays(),
                           overlay_styles=overlays.OVERLAY_STYLES,
                           scheduler_running=overlay_scheduler.running)


@app.route("/overlays", methods=["POST"])
def overlays_create():
    otype = request.form.get("type", "text_banner")
    text = request.form.get("text", "")
    position = request.form.get("position", "bottom")
    duration = int(request.form.get("duration_sec", 15))
    interval = int(request.form.get("interval_sec", 300))

    image = ""
    if "image" in request.files and request.files["image"].filename:
        image = overlays.save_uploaded_image(request.files["image"])

    style = request.form.get("style", "elegant_gold")

    overlays.create_overlay(otype, text=text, image=image,
                            position=position, duration_sec=duration,
                            interval_sec=interval, style=style)
    return redirect(url_for("overlays_page"))


@app.route("/overlays/toggle/<overlay_id>", methods=["POST"])
def overlays_toggle(overlay_id):
    overlays.toggle_overlay(overlay_id)
    return redirect(url_for("overlays_page"))


@app.route("/overlays/delete/<overlay_id>", methods=["POST"])
def overlays_delete(overlay_id):
    overlays.delete_overlay(overlay_id)
    return redirect(url_for("overlays_page"))


@app.route("/overlays/preview/<overlay_id>")
def overlays_preview(overlay_id):
    overlay = overlays.get_overlay(overlay_id)
    if not overlay:
        return "Not found", 404
    img = overlays.render_overlay(overlay)
    import io
    buf = io.BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


@app.route("/overlays/live-preview")
def overlays_live_preview():
    """Render a live preview without saving - called via JS."""
    overlay = {
        "type": request.args.get("type", "text_banner"),
        "text": request.args.get("text", "Preview text here"),
        "position": request.args.get("position", "bottom"),
        "style": request.args.get("style", "elegant_gold"),
        "image": "",
    }
    img = overlays.render_overlay(overlay)
    import io
    buf = io.BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    return send_file(buf, mimetype="image/png")


@app.route("/overlays/scheduler/start", methods=["POST"])
def overlays_scheduler_start():
    overlay_scheduler.start()
    return redirect(url_for("overlays_page"))


@app.route("/overlays/scheduler/stop", methods=["POST"])
def overlays_scheduler_stop():
    overlay_scheduler.stop()
    return redirect(url_for("overlays_page"))


# ── Stream Control ───────────────────────────────────────────────────────────

@app.route("/stream/start", methods=["POST"])
def stream_start():
    key = request.form.get("stream_key") or config.get("YOUTUBE_STREAM_KEY", "")
    if not key:
        return redirect(url_for("settings_page"))
    result = stream_mgr.start(key)
    if not result["ok"]:
        return render_template("dashboard.html",
                               stream=stream_mgr.get_status(),
                               current_task=worker.current_task,
                               queue_size=worker.queue_size,
                               history=list(reversed(worker.history[-10:])),
                               lib_stats=library.stats(),
                               error=result["error"])
    return redirect(url_for("dashboard"))


@app.route("/stream/stop", methods=["POST"])
def stream_stop():
    stream_mgr.stop()
    return redirect(url_for("dashboard"))


@app.route("/stream/refresh", methods=["POST"])
def stream_refresh():
    stream_mgr.refresh()
    return redirect(url_for("dashboard"))


@app.route("/stream/status")
def stream_status():
    return jsonify(stream_mgr.get_status())


# ── Settings ─────────────────────────────────────────────────────────────────

@app.route("/settings")
def settings_page():
    return render_template("settings.html", config=config.get_all())


@app.route("/settings", methods=["POST"])
def settings_save():
    for key in ["ANTHROPIC_API_KEY", "YOUTUBE_STREAM_KEY", "SUNO_API_KEY"]:
        val = request.form.get(key, "").strip()
        if val:
            config.set_runtime(key, val)
            os.environ[key] = val
    return redirect(url_for("settings_page"))


# ── SSE Events ───────────────────────────────────────────────────────────────

@app.route("/events")
def events():
    def stream():
        q = queue.Queue()
        worker.register_callback(lambda evt: q.put(evt))

        try:
            while True:
                try:
                    evt = q.get(timeout=15)
                    yield f"data: {json.dumps(evt, default=str)}\n\n"
                except queue.Empty:
                    # Send keepalive
                    status = stream_mgr.get_status()
                    status["current_task"] = worker.current_task
                    status["queue_size"] = worker.queue_size
                    yield f"data: {json.dumps({'type': 'heartbeat', **status}, default=str)}\n\n"
        finally:
            worker.unregister_callback(lambda evt: q.put(evt))

    return Response(stream(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache",
                             "X-Accel-Buffering": "no"})


# ── Startup ──────────────────────────────────────────────────────────────────

def create_app():
    """Factory for Gunicorn."""
    library._ensure_dirs()
    overlays.init()
    worker.start()
    return app


# Start worker when running directly
worker.start()

if __name__ == "__main__":
    library._ensure_dirs()
    overlays.init()
    port = int(config.get("FLASK_PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=True, threaded=True)
