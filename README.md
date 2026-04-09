# Disney Piano Stream

AI-powered Disney-style piano livestream with a web UI for generating, managing, and streaming falling-note visualizations to YouTube.

## Quick Install

```bash
git clone https://github.com/danward28/disney-stream.git && cd disney-stream && bash deploy.sh
```

Then open `http://YOUR_SERVER_IP:8080` in your browser.

## What It Does

- **Generates** Disney-inspired piano arrangements using Claude API, with falling-note visualization videos
- **Stores** everything in a persistent asset library — generate once, stream forever (no recurring API costs)
- **Streams** to YouTube 24/7 via RTMP with configurable ad/product overlays
- **Supports** 4 music generators: Piano (Claude), ACE-Step, MusicGen, and Suno

## Features

### Web Dashboard
- Real-time generation progress via Server-Sent Events
- Library browser with video previews and thumbnails
- Start/stop/refresh YouTube stream from the UI

### Asset Library
- Videos saved permanently with metadata
- Enable/disable individual assets without deleting
- Filter by generator type

### Stream Overlays
- Promote books, products, or messages during your stream
- 7 style presets (Elegant Gold, Neon Purple, Ocean Blue, Rose Garden, Enchanted Forest, Cinematic Dark, Sunset Warm)
- Image + text cards, text banners, or full image banners
- Live preview while editing, configurable show duration and cycle interval
- Automatic scheduling — overlays rotate on a timer

### Video Generation
- 30 Disney songs x 12 variation styles = 360+ possible combinations
- 8 background themes (Midnight Blue, Enchanted Purple, Ocean Deep, Aurora Green, Rose Night, Golden Palace, Frozen Crystal, Sunset Dream)
- "Now Playing" title cards burned into each video
- 1920x1080 @ 30fps falling-note visualization with piano keyboard

## Setup

### Requirements
- Ubuntu/Debian Linux (or any system with apt)
- Python 3.10+
- FFmpeg, FluidSynth
- Anthropic API key (for Piano generator)
- YouTube stream key (for streaming)

### Manual Setup (if not using deploy.sh)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
sudo apt install ffmpeg fluidsynth fluid-soundfont-gm fonts-dejavu-core
cp .env.example .env   # Edit with your API keys
python app.py           # Start on port 8080
```

### Configuration

Edit `.env` or use the Settings page in the web UI:

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes (for Piano) | From console.anthropic.com |
| `YOUTUBE_STREAM_KEY` | Yes (for streaming) | From YouTube Studio > Go Live |
| `SUNO_API_KEY` | Optional | Only for Suno generator |
| `FLASK_PORT` | Optional | Default: 8080 |

### Production Deployment

`deploy.sh` installs a systemd service automatically. Manage it with:

```bash
sudo systemctl status disney-stream
sudo systemctl restart disney-stream
sudo journalctl -u disney-stream -f
```

Runs on a 2 vCPU / 4GB RAM VM (~$5-10/month on Hetzner, DigitalOcean, etc.).

## Architecture

```
Flask Web UI (Gunicorn, 1 worker, 4 threads)
  ├── Generation Worker (background thread)
  │   ├── Piano: Claude API → MIDI → FluidSynth → PIL video → FFmpeg
  │   ├── ACE-Step: local AI model
  │   ├── MusicGen: Meta's audiocraft
  │   └── Suno: cloud API
  ├── Asset Library (catalog.json + video files + thumbnails)
  ├── Stream Manager (FFmpeg subprocess → YouTube RTMP)
  └── Overlay Scheduler (PIL renders → atomic PNG swap → FFmpeg overlay)
```

## License

MIT
