"""FFmpeg RTMP stream subprocess manager with overlay support."""

import os
import signal
import subprocess
import threading
import time
from pathlib import Path

import library
import overlays

PROJECT_DIR = Path(__file__).parent
OUTPUT_DIR = PROJECT_DIR / "output"


class StreamManager:
    """Manages the FFmpeg streaming process."""

    def __init__(self):
        self.process = None
        self.status = "stopped"  # stopped | starting | live | error
        self.stream_key = None
        self._start_time = None
        self._monitor_thread = None
        self._error_msg = ""

    def start(self, stream_key):
        """Start streaming to YouTube."""
        if self.process and self.process.poll() is None:
            return {"ok": False, "error": "Stream already running"}

        playlist = library.get_playlist(shuffle=True)
        if not playlist:
            return {"ok": False, "error": "No videos in library"}

        # Initialize overlay system
        overlays.init()

        # Create concat list
        OUTPUT_DIR.mkdir(exist_ok=True)
        concat_file = OUTPUT_DIR / "stream_playlist.txt"
        with open(concat_file, "w") as f:
            for video_path in playlist:
                f.write(f"file '{video_path}'\n")

        overlay_path = str(overlays.CURRENT_OVERLAY)

        cmd = [
            "ffmpeg", "-re",
            "-f", "concat", "-safe", "0", "-stream_loop", "-1",
            "-i", str(concat_file),
            "-stream_loop", "-1",
            "-i", overlay_path,
            "-filter_complex",
            "[0:v][1:v]overlay=0:0:format=auto,format=yuv420p",
            "-c:v", "libx264", "-preset", "veryfast",
            "-b:v", "3000k", "-maxrate", "3000k", "-bufsize", "6000k",
            "-g", "60",
            "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
            "-f", "flv",
            f"rtmp://a.rtmp.youtube.com/live2/{stream_key}",
        ]

        self.status = "starting"
        self.stream_key = stream_key
        self._error_msg = ""

        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            self._start_time = time.time()
            self.status = "live"

            # Start monitoring thread
            self._monitor_thread = threading.Thread(
                target=self._monitor, daemon=True
            )
            self._monitor_thread.start()

            return {"ok": True, "pid": self.process.pid}
        except Exception as e:
            self.status = "error"
            self._error_msg = str(e)
            return {"ok": False, "error": str(e)}

    def stop(self):
        """Stop the stream gracefully."""
        if not self.process or self.process.poll() is not None:
            self.status = "stopped"
            return {"ok": True}

        try:
            self.process.send_signal(signal.SIGTERM)
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        except Exception as e:
            return {"ok": False, "error": str(e)}

        self.status = "stopped"
        self.process = None
        self._start_time = None
        return {"ok": True}

    def refresh(self, stream_key=None):
        """Rebuild playlist and restart stream."""
        key = stream_key or self.stream_key
        if not key:
            return {"ok": False, "error": "No stream key"}

        was_live = self.status == "live"
        if was_live:
            self.stop()
            time.sleep(2)  # brief pause for YouTube to notice disconnect

        return self.start(key)

    def get_status(self):
        """Return current stream status."""
        uptime = 0
        if self._start_time and self.status == "live":
            uptime = int(time.time() - self._start_time)

        lib_stats = library.stats()

        return {
            "status": self.status,
            "uptime_sec": uptime,
            "uptime_str": self._format_uptime(uptime),
            "pid": self.process.pid if self.process and self.process.poll() is None else None,
            "error": self._error_msg,
            "library_videos": lib_stats["enabled"],
            "library_duration_min": lib_stats["total_duration_min"],
        }

    def _monitor(self):
        """Background thread: watch for process exit."""
        if not self.process:
            return
        returncode = self.process.wait()
        if returncode != 0 and self.status == "live":
            try:
                stderr = self.process.stderr.read().decode(errors="replace")[-500:]
            except Exception:
                stderr = ""
            self._error_msg = f"FFmpeg exited with code {returncode}: {stderr}"
            self.status = "error"
        elif self.status != "stopped":
            self.status = "stopped"

    @staticmethod
    def _format_uptime(seconds):
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            return f"{seconds // 60}m {seconds % 60}s"
        else:
            h = seconds // 3600
            m = (seconds % 3600) // 60
            return f"{h}h {m}m"
