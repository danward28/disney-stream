#!/usr/bin/env python3
"""
Disney Piano Stream Generator

Generates Disney-style piano variations using Claude API,
converts to MIDI, renders audio, creates visualization video,
and streams to YouTube.

Usage:
  python generate.py                    # Generate one song
  python generate.py --count 5          # Generate 5 songs
  python generate.py --stream           # Generate and stream continuously
  python generate.py --stream-only      # Stream existing queue to YouTube
"""

import anthropic
import json
import math
import mido
import os
import random
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
from midi2audio import FluidSynth
from PIL import Image, ImageDraw, ImageFont

# ── Config ──────────────────────────────────────────────────────────────────

PROJECT_DIR = Path(__file__).parent
QUEUE_DIR = PROJECT_DIR / "queue"
OUTPUT_DIR = PROJECT_DIR / "output"
SOUNDFONT = "/usr/share/sounds/sf2/FluidR3_GM.sf2"

WIDTH, HEIGHT = 1920, 1080
FPS = 30
NOTE_SPEED = 200  # pixels per second

# Disney songs to generate variations of
DISNEY_SONGS = [
    ("A Whole New World", "Aladdin"),
    ("Let It Go", "Frozen"),
    ("Under the Sea", "The Little Mermaid"),
    ("Beauty and the Beast", "Beauty and the Beast"),
    ("Circle of Life", "The Lion King"),
    ("When You Wish Upon a Star", "Pinocchio"),
    ("Part of Your World", "The Little Mermaid"),
    ("Colors of the Wind", "Pocahontas"),
    ("Can You Feel the Love Tonight", "The Lion King"),
    ("A Dream Is a Wish Your Heart Makes", "Cinderella"),
    ("Reflection", "Mulan"),
    ("Go the Distance", "Hercules"),
    ("You've Got a Friend in Me", "Toy Story"),
    ("Remember Me", "Coco"),
    ("How Far I'll Go", "Moana"),
    ("Into the Unknown", "Frozen II"),
    ("Someday My Prince Will Come", "Snow White"),
    ("Once Upon a Dream", "Sleeping Beauty"),
    ("I See the Light", "Tangled"),
    ("Friend Like Me", "Aladdin"),
    ("Be Our Guest", "Beauty and the Beast"),
    ("Supercalifragilisticexpialidocious", "Mary Poppins"),
    ("Bibbidi-Bobbidi-Boo", "Cinderella"),
    ("Hakuna Matata", "The Lion King"),
    ("Kiss the Girl", "The Little Mermaid"),
    ("I Just Can't Wait to Be King", "The Lion King"),
    ("Whistle While You Work", "Snow White"),
    ("Chim Chim Cher-ee", "Mary Poppins"),
    ("It's a Small World", "Disney Parks"),
    ("Do You Want to Build a Snowman?", "Frozen"),
]

VARIATION_STYLES = [
    "gentle lullaby arrangement with soft arpeggios",
    "jazz piano arrangement with swing rhythm and extended chords",
    "classical romantic style with sweeping arpeggios and rubato",
    "ragtime arrangement with syncopated left hand",
    "music box style with high register tinkling notes",
    "nocturne style with flowing left hand accompaniment",
    "boogie-woogie arrangement with driving bass",
    "impressionist style with whole-tone scales and dreamy chords",
    "waltz arrangement in 3/4 time",
    "minimalist arrangement with repeating patterns",
    "stride piano with alternating bass and chord",
    "ballad arrangement with rich block chords",
]

# ── MIDI Generation via Claude ──────────────────────────────────────────────


def generate_midi_from_claude(song_title: str, movie: str, style: str,
                               progress_callback=None) -> str | None:
    """Ask Claude to generate a piano piece as raw MIDI note data."""
    if progress_callback:
        progress_callback("generating_notes", f"Asking Claude for {song_title}...")

    client = anthropic.Anthropic()

    prompt = f"""Generate a piano arrangement inspired by "{song_title}" from Disney's {movie}.
Style: {style}

Output EXACTLY a JSON array of note events. Each event is an object with:
- "note": MIDI note number (integer, 21-108 for piano range)
- "start": start time in seconds (float)
- "duration": duration in seconds (float)
- "velocity": MIDI velocity (integer, 30-110)

Requirements:
- The piece should be 60-90 seconds long
- Include both melody (right hand, notes 60-96) and accompaniment (left hand, notes 36-60)
- Use dynamics (varying velocity) for expressiveness
- Make it recognizably inspired by the original melody but as a creative piano variation
- Include at least 80 notes total
- Ensure musical coherence with proper harmony

Output ONLY the JSON array, no other text. Start with [ and end with ]."""

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=8000,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text.strip()
        # Extract JSON array from response
        match = re.search(r'\[[\s\S]*\]', text)
        if not match:
            print(f"  ERROR: No JSON array found in response")
            return None

        notes = json.loads(match.group())
        if len(notes) < 20:
            print(f"  ERROR: Too few notes ({len(notes)})")
            return None

        return json.dumps(notes)

    except Exception as e:
        print(f"  ERROR generating: {e}")
        return None


def notes_to_midi(notes_json: str, output_path: str) -> bool:
    """Convert JSON note events to a MIDI file."""
    try:
        notes = json.loads(notes_json)
        mid = mido.MidiFile(type=0, ticks_per_beat=480)
        track = mido.MidiTrack()
        mid.tracks.append(track)

        # Set tempo (120 BPM default, can be overridden)
        track.append(mido.MetaMessage('set_tempo', tempo=mido.bpm2tempo(100)))
        # Set piano instrument
        track.append(mido.Message('program_change', program=0, time=0))

        # Convert note events to MIDI messages
        events = []
        for note in notes:
            note_num = max(21, min(108, int(note["note"])))
            velocity = max(1, min(127, int(note.get("velocity", 80))))
            start = float(note["start"])
            duration = float(note["duration"])

            start_tick = int(start * 480 * 100 / 60)  # at 100 BPM
            dur_tick = max(1, int(duration * 480 * 100 / 60))

            events.append((start_tick, 'note_on', note_num, velocity))
            events.append((start_tick + dur_tick, 'note_off', note_num, 0))

        # Sort by time
        events.sort(key=lambda e: (e[0], 0 if e[1] == 'note_off' else 1))

        # Convert to delta times
        current_tick = 0
        for tick, msg_type, note_num, velocity in events:
            delta = max(0, tick - current_tick)
            track.append(mido.Message(msg_type, note=note_num, velocity=velocity, time=delta))
            current_tick = tick

        mid.save(output_path)
        return True
    except Exception as e:
        print(f"  ERROR creating MIDI: {e}")
        return False


# ── Audio Rendering ─────────────────────────────────────────────────────────


def render_audio(midi_path: str, wav_path: str) -> bool:
    """Render MIDI to WAV using FluidSynth."""
    try:
        fs = FluidSynth(sound_font=SOUNDFONT)
        fs.midi_to_audio(midi_path, wav_path)
        return True
    except Exception as e:
        print(f"  ERROR rendering audio: {e}")
        return False


# ── Video Generation ────────────────────────────────────────────────────────

# Disney-inspired color palette
COLORS = [
    (70, 130, 220),   # Royal blue
    (180, 100, 220),  # Purple
    (220, 150, 50),   # Gold
    (100, 200, 150),  # Seafoam
    (220, 80, 120),   # Rose
    (80, 180, 220),   # Sky blue
    (200, 120, 180),  # Pink
    (120, 200, 100),  # Green
    (240, 180, 80),   # Amber
    (150, 120, 220),  # Lavender
]

BG_COLOR = (12, 8, 24)        # Deep dark blue
PIANO_BG = (20, 15, 35)       # Slightly lighter
WHITE_KEY = (240, 238, 235)
BLACK_KEY = (30, 25, 45)
PIANO_HEIGHT = 120

# ── Video Background Themes ──────────────────────────────────────────────────

VIDEO_THEMES = {
    "midnight_blue": {
        "name": "Midnight Blue (Default)",
        "bg_top": (12, 8, 24),
        "bg_bottom": (20, 15, 40),
        "piano_bg": (20, 15, 35),
        "white_key": (240, 238, 235),
        "black_key": (30, 25, 45),
        "watermark_color": (40, 35, 55),
    },
    "enchanted_purple": {
        "name": "Enchanted Purple",
        "bg_top": (25, 5, 35),
        "bg_bottom": (40, 15, 55),
        "piano_bg": (30, 10, 40),
        "white_key": (235, 230, 240),
        "black_key": (40, 15, 50),
        "watermark_color": (50, 30, 60),
    },
    "ocean_deep": {
        "name": "Ocean Deep",
        "bg_top": (5, 12, 30),
        "bg_bottom": (10, 25, 50),
        "piano_bg": (8, 18, 38),
        "white_key": (230, 240, 245),
        "black_key": (15, 25, 45),
        "watermark_color": (25, 40, 60),
    },
    "aurora_green": {
        "name": "Aurora Green",
        "bg_top": (5, 18, 12),
        "bg_bottom": (12, 30, 22),
        "piano_bg": (8, 22, 16),
        "white_key": (235, 245, 238),
        "black_key": (15, 35, 25),
        "watermark_color": (25, 45, 35),
    },
    "rose_night": {
        "name": "Rose Night",
        "bg_top": (25, 8, 15),
        "bg_bottom": (40, 15, 28),
        "piano_bg": (30, 12, 20),
        "white_key": (240, 235, 237),
        "black_key": (40, 20, 30),
        "watermark_color": (55, 35, 42),
    },
    "golden_palace": {
        "name": "Golden Palace",
        "bg_top": (20, 15, 5),
        "bg_bottom": (35, 25, 10),
        "piano_bg": (28, 20, 8),
        "white_key": (245, 240, 230),
        "black_key": (40, 30, 15),
        "watermark_color": (55, 45, 25),
    },
    "frozen_crystal": {
        "name": "Frozen Crystal",
        "bg_top": (10, 15, 28),
        "bg_bottom": (18, 28, 48),
        "piano_bg": (14, 22, 38),
        "white_key": (235, 242, 250),
        "black_key": (20, 30, 50),
        "watermark_color": (35, 48, 65),
    },
    "sunset_dream": {
        "name": "Sunset Dream",
        "bg_top": (30, 12, 8),
        "bg_bottom": (45, 22, 15),
        "piano_bg": (35, 16, 10),
        "white_key": (248, 240, 235),
        "black_key": (45, 25, 18),
        "watermark_color": (60, 40, 30),
    },
}


def get_note_color(note: int) -> tuple:
    """Get a color based on the note's pitch class."""
    return COLORS[note % len(COLORS)]


def is_black_key(note: int) -> bool:
    """Check if a MIDI note is a black key."""
    return (note % 12) in [1, 3, 6, 8, 10]


def note_to_x(note: int, width: int) -> tuple:
    """Convert MIDI note to x position and width on screen."""
    # Piano range: 21 (A0) to 108 (C8) = 88 keys, 52 white keys
    white_notes = []
    for n in range(21, 109):
        if not is_black_key(n):
            white_notes.append(n)

    white_key_width = width / len(white_notes)

    if is_black_key(note):
        # Black key: position between adjacent white keys
        lower_white = note - 1
        while is_black_key(lower_white):
            lower_white -= 1
        if lower_white < 21:
            return (0, 0)
        idx = white_notes.index(lower_white) if lower_white in white_notes else 0
        x = (idx + 0.65) * white_key_width
        w = white_key_width * 0.7
        return (int(x), int(w))
    else:
        if note not in white_notes:
            return (0, 0)
        idx = white_notes.index(note)
        x = idx * white_key_width
        return (int(x), int(white_key_width))


def draw_piano(draw: ImageDraw.Draw, width: int, y_top: int,
               white_color=WHITE_KEY, black_color=BLACK_KEY):
    """Draw the piano keyboard at the bottom."""
    # White keys first
    white_key_count = sum(1 for n in range(21, 109) if not is_black_key(n))
    wk_width = width / white_key_count

    idx = 0
    for note in range(21, 109):
        if not is_black_key(note):
            x = int(idx * wk_width)
            draw.rectangle(
                [x, y_top, x + int(wk_width) - 1, y_top + PIANO_HEIGHT],
                fill=white_color, outline=(180, 178, 175)
            )
            idx += 1

    # Black keys on top
    for note in range(21, 109):
        if is_black_key(note):
            x, w = note_to_x(note, width)
            if w > 0:
                draw.rectangle(
                    [x, y_top, x + w, y_top + int(PIANO_HEIGHT * 0.65)],
                    fill=black_color
                )


def draw_sparkle(draw: ImageDraw.Draw, x: int, y: int, size: int, color: tuple, alpha: float):
    """Draw a small sparkle/glow effect."""
    r, g, b = color
    for i in range(size, 0, -1):
        factor = (i / size) * alpha
        c = (int(r * factor), int(g * factor), int(b * factor))
        draw.ellipse([x - i, y - i, x + i, y + i], fill=c)


def generate_video(midi_path: str, wav_path: str, mp4_path: str,
                   title: str, movie: str, progress_callback=None,
                   theme_id: str = "midnight_blue") -> bool:
    """Generate a falling-notes visualization video."""
    try:
        theme = VIDEO_THEMES.get(theme_id, VIDEO_THEMES["midnight_blue"])
        t_bg_top = theme["bg_top"]
        t_bg_bottom = theme["bg_bottom"]
        t_piano_bg = theme["piano_bg"]
        t_white_key = theme["white_key"]
        t_black_key = theme["black_key"]
        t_watermark = theme["watermark_color"]

        mid = mido.MidiFile(midi_path)

        # Extract note events with absolute times
        notes = []
        for track in mid.tracks:
            abs_time = 0
            tempo = 600000  # default 100 BPM
            active = {}

            for msg in track:
                abs_time += msg.time
                if msg.type == 'set_tempo':
                    tempo = msg.tempo
                elif msg.type == 'note_on' and msg.velocity > 0:
                    time_sec = mido.tick2second(abs_time, mid.ticks_per_beat, tempo)
                    active[msg.note] = (time_sec, msg.velocity)
                elif msg.type in ('note_off', 'note_on') and (msg.type == 'note_off' or msg.velocity == 0):
                    if msg.note in active:
                        start, vel = active.pop(msg.note)
                        end = mido.tick2second(abs_time, mid.ticks_per_beat, tempo)
                        notes.append({
                            'note': msg.note,
                            'start': start,
                            'end': end,
                            'velocity': vel,
                        })

        if not notes:
            print("  ERROR: No notes found in MIDI")
            return False

        duration = max(n['end'] for n in notes) + 3  # 3 sec buffer
        total_frames = int(duration * FPS)
        piano_y = HEIGHT - PIANO_HEIGHT

        # Title display duration
        title_fade_end = 10.0  # seconds

        print(f"  Rendering {total_frames} frames ({duration:.1f}s)...")

        # Pipe frames to ffmpeg
        ffmpeg_cmd = [
            'ffmpeg', '-y',
            '-f', 'rawvideo', '-vcodec', 'rawvideo',
            '-s', f'{WIDTH}x{HEIGHT}', '-pix_fmt', 'rgb24',
            '-r', str(FPS), '-i', 'pipe:0',
            '-i', wav_path,
            '-c:v', 'libx264', '-preset', 'medium',
            '-crf', '23', '-pix_fmt', 'yuv420p',
            '-c:a', 'aac', '-b:a', '192k',
            '-shortest',
            mp4_path
        ]

        proc = subprocess.Popen(
            ffmpeg_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Try to load a nice font
        font_large = None
        font_small = None
        try:
            for fp in ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                       "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]:
                if os.path.exists(fp):
                    font_large = ImageFont.truetype(fp, 48)
                    font_small = ImageFont.truetype(fp, 28)
                    break
        except Exception:
            pass
        if not font_large:
            font_large = ImageFont.load_default()
            font_small = ImageFont.load_default()

        for frame_idx in range(total_frames):
            t = frame_idx / FPS
            img = Image.new('RGB', (WIDTH, HEIGHT), t_bg_top)
            draw = ImageDraw.Draw(img)

            # Draw gradient background using theme colors
            for y in range(0, piano_y, 4):
                frac = y / piano_y
                r = int(t_bg_top[0] + (t_bg_bottom[0] - t_bg_top[0]) * frac)
                g = int(t_bg_top[1] + (t_bg_bottom[1] - t_bg_top[1]) * frac)
                b = int(t_bg_top[2] + (t_bg_bottom[2] - t_bg_top[2]) * frac)
                draw.rectangle([0, y, WIDTH, y + 4], fill=(r, g, b))

            # Draw falling notes
            active_notes = set()
            for note in notes:
                # Calculate note position
                note_bottom = piano_y - (note['start'] - t) * NOTE_SPEED
                note_top = piano_y - (note['end'] - t) * NOTE_SPEED

                # Only draw if visible
                if note_top > piano_y or note_bottom < 0:
                    continue

                # Clamp to visible area
                draw_top = max(0, int(note_top))
                draw_bottom = min(piano_y, int(note_bottom))

                if draw_bottom <= draw_top:
                    continue

                x, w = note_to_x(note['note'], WIDTH)
                if w <= 0:
                    continue

                color = get_note_color(note['note'])
                vel_factor = note['velocity'] / 127.0

                # Glow effect
                glow_color = tuple(int(c * 0.3 * vel_factor) for c in color)
                draw.rectangle(
                    [x - 2, draw_top - 2, x + w + 2, draw_bottom + 2],
                    fill=glow_color
                )

                # Main note block with rounded appearance
                bright_color = tuple(min(255, int(c * (0.7 + 0.3 * vel_factor))) for c in color)
                draw.rectangle([x, draw_top, x + w, draw_bottom], fill=bright_color)

                # Highlight edge
                highlight = tuple(min(255, c + 60) for c in bright_color)
                draw.rectangle([x, draw_top, x + 2, draw_bottom], fill=highlight)

                # Track active notes (touching piano)
                if note_bottom >= piano_y - 5 and note_top <= piano_y:
                    active_notes.add(note['note'])

            # Draw piano
            draw_piano(draw, WIDTH, piano_y, t_white_key, t_black_key)

            # Highlight active keys
            for n in active_notes:
                x, w = note_to_x(n, WIDTH)
                if w <= 0:
                    continue
                color = get_note_color(n)
                glow = tuple(min(255, c + 30) for c in color)
                if is_black_key(n):
                    draw.rectangle(
                        [x, piano_y, x + w, piano_y + int(PIANO_HEIGHT * 0.65)],
                        fill=glow
                    )
                else:
                    draw.rectangle(
                        [x + 1, piano_y, x + w - 1, piano_y + PIANO_HEIGHT],
                        fill=glow, outline=(180, 178, 175)
                    )

            # Draw title overlay at top (fades out after 7s)
            if t < title_fade_end:
                alpha = 1.0 if t < 7.0 else max(0, 1.0 - (t - 7.0) / 3.0)
                if alpha > 0:
                    overlay_y = 30
                    title_text = f"~ {title} ~"
                    movie_text = f"from {movie}"

                    text_color = tuple(int(220 * alpha) for _ in range(3))
                    sub_color = tuple(int(160 * alpha) for _ in range(3))

                    bbox = draw.textbbox((0, 0), title_text, font=font_large)
                    tw = bbox[2] - bbox[0]
                    draw.text(((WIDTH - tw) // 2, overlay_y), title_text,
                              fill=text_color, font=font_large)

                    bbox2 = draw.textbbox((0, 0), movie_text, font=font_small)
                    tw2 = bbox2[2] - bbox2[0]
                    draw.text(((WIDTH - tw2) // 2, overlay_y + 60), movie_text,
                              fill=sub_color, font=font_small)

            # Draw "Now Playing" lower-third bar (first 15 seconds, fades out)
            now_playing_end = 15.0
            if t < now_playing_end:
                np_alpha = 1.0 if t < 12.0 else max(0, 1.0 - (t - 12.0) / 3.0)
                if np_alpha > 0:
                    bar_h = 50
                    bar_y_pos = piano_y - bar_h - 10
                    # Semi-transparent bar
                    bar_img = Image.new('RGBA', (WIDTH, bar_h), (0, 0, 0, 0))
                    bar_draw = ImageDraw.Draw(bar_img)
                    bar_draw.rectangle([40, 0, WIDTH - 40, bar_h],
                                       fill=(10, 5, 30, int(180 * np_alpha)))
                    bar_draw.line([(40, 0), (WIDTH - 40, 0)],
                                  fill=(212, 168, 67, int(200 * np_alpha)), width=2)
                    bar_draw.line([(40, bar_h - 1), (WIDTH - 40, bar_h - 1)],
                                  fill=(212, 168, 67, int(200 * np_alpha)), width=2)

                    # Composite bar onto frame
                    temp = Image.new('RGBA', (WIDTH, HEIGHT), (0, 0, 0, 0))
                    temp.paste(bar_img, (0, bar_y_pos))
                    img = Image.alpha_composite(img.convert('RGBA'), temp).convert('RGB')
                    draw = ImageDraw.Draw(img)

                    # Now Playing text
                    np_label = "NOW PLAYING"
                    np_title = f"{title}  -  {movie}"
                    np_color = (212, 168, 67, int(255 * np_alpha))
                    title_color = (240, 235, 220, int(255 * np_alpha))

                    label_bbox = draw.textbbox((0, 0), np_label, font=font_small)
                    draw.text((60, bar_y_pos + 4), np_label,
                              fill=(int(212 * np_alpha), int(168 * np_alpha), int(67 * np_alpha)),
                              font=font_small)
                    label_w = label_bbox[2] - label_bbox[0]
                    draw.text((60 + label_w + 20, bar_y_pos + 6), np_title,
                              fill=(int(240 * np_alpha), int(235 * np_alpha), int(220 * np_alpha)),
                              font=font_small)

            # Draw subtle watermark
            wm_text = "AI Disney Piano Variations"
            wm_bbox = draw.textbbox((0, 0), wm_text, font=font_small)
            wm_w = wm_bbox[2] - wm_bbox[0]
            draw.text((WIDTH - wm_w - 20, HEIGHT - 30), wm_text,
                      fill=t_watermark, font=font_small)

            # Write frame
            proc.stdin.write(np.array(img).tobytes())

            if frame_idx % (FPS * 10) == 0:
                print(f"    Frame {frame_idx}/{total_frames} ({t:.0f}s)")
                if progress_callback:
                    pct = int(100 * frame_idx / total_frames)
                    progress_callback("rendering_video",
                                      f"Frame {frame_idx}/{total_frames} ({pct}%)")

        proc.stdin.close()
        proc.wait()

        if proc.returncode != 0:
            print(f"  ERROR: ffmpeg exited with code {proc.returncode}")
            return False

        print(f"  Video saved: {mp4_path}")
        return True

    except Exception as e:
        print(f"  ERROR generating video: {e}")
        import traceback
        traceback.print_exc()
        return False


# ── Pipeline ────────────────────────────────────────────────────────────────


def generate_one(song=None, movie=None, style=None,
                 progress_callback=None, theme="midnight_blue") -> dict | None:
    """Generate one Disney piano variation video.

    Returns dict with {path, song, movie, style} or None on failure.
    If song/movie/style are None, picks randomly.
    progress_callback(step, detail) is called at each stage.
    """
    if song is None or movie is None:
        song, movie = random.choice(DISNEY_SONGS)
    if style is None:
        style = random.choice(VARIATION_STYLES)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = re.sub(r'[^a-z0-9]+', '-', song.lower()).strip('-')
    base = f"{timestamp}_{slug}"

    midi_path = str(OUTPUT_DIR / f"{base}.mid")
    wav_path = str(OUTPUT_DIR / f"{base}.wav")
    mp4_path = str(QUEUE_DIR / f"{base}.mp4")

    def _cb(step, detail=""):
        if progress_callback:
            progress_callback(step, detail)

    print(f"\n{'='*60}")
    print(f"  Song:  {song} ({movie})")
    print(f"  Style: {style}")
    print(f"{'='*60}")

    # Step 1: Generate notes via Claude
    print("\n[1/4] Generating arrangement via Claude...")
    _cb("generating_notes", f"Asking Claude for {song}...")
    notes_json = generate_midi_from_claude(song, movie, style)
    if not notes_json:
        return None

    notes = json.loads(notes_json)
    print(f"  Generated {len(notes)} notes")

    # Step 2: Convert to MIDI
    print("\n[2/4] Creating MIDI file...")
    _cb("creating_midi", f"{len(notes)} notes")
    if not notes_to_midi(notes_json, midi_path):
        return None
    print(f"  MIDI saved: {midi_path}")

    # Step 3: Render audio
    print("\n[3/4] Rendering audio...")
    _cb("rendering_audio", "FluidSynth processing...")
    if not render_audio(midi_path, wav_path):
        return None
    print(f"  Audio saved: {wav_path}")

    # Step 4: Generate video
    print("\n[4/4] Generating visualization video...")
    _cb("rendering_video", "Starting frame rendering...")
    if not generate_video(midi_path, wav_path, mp4_path, song, movie,
                          progress_callback=progress_callback,
                          theme_id=theme):
        return None

    _cb("done", mp4_path)
    return {"path": mp4_path, "song": song, "movie": movie, "style": style}


def concat_queue(output_path: str) -> bool:
    """Concatenate all videos in the queue into one file."""
    videos = sorted(QUEUE_DIR.glob("*.mp4"))
    if not videos:
        print("No videos in queue!")
        return False

    # Create concat file
    concat_file = OUTPUT_DIR / "concat.txt"
    with open(concat_file, 'w') as f:
        for v in videos:
            f.write(f"file '{v}'\n")

    cmd = [
        'ffmpeg', '-y', '-f', 'concat', '-safe', '0',
        '-i', str(concat_file),
        '-c', 'copy', output_path
    ]
    result = subprocess.run(cmd, capture_output=True)
    return result.returncode == 0


def stream_to_youtube(stream_key: str, replace_process=False):
    """Stream queue videos to YouTube in an infinite loop.

    If replace_process=True, uses os.execvp (CLI mode).
    Otherwise returns subprocess.Popen handle (web UI mode).
    """
    concat_path = str(OUTPUT_DIR / "stream_concat.mp4")

    print("\nPreparing stream playlist...")
    if not concat_queue(concat_path):
        print("Failed to create playlist!")
        return None

    print(f"Streaming to YouTube...")
    cmd = [
        'ffmpeg', '-re', '-stream_loop', '-1',
        '-i', concat_path,
        '-c:v', 'libx264', '-preset', 'veryfast',
        '-b:v', '3000k', '-maxrate', '3000k', '-bufsize', '6000k',
        '-pix_fmt', 'yuv420p', '-g', '60',
        '-c:a', 'aac', '-b:a', '128k', '-ar', '44100',
        '-f', 'flv',
        f'rtmp://a.rtmp.youtube.com/live2/{stream_key}'
    ]

    print(f"Running: {' '.join(cmd[:6])} ... rtmp://...")
    if replace_process:
        os.execvp('ffmpeg', cmd)
    else:
        return subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
        )


# ── CLI ─────────────────────────────────────────────────────────────────────


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Disney Piano Stream Generator")
    parser.add_argument('--count', type=int, default=1,
                        help="Number of songs to generate")
    parser.add_argument('--stream', action='store_true',
                        help="Generate songs then stream to YouTube")
    parser.add_argument('--stream-only', action='store_true',
                        help="Stream existing queue to YouTube (no generation)")
    parser.add_argument('--stream-key', type=str,
                        help="YouTube stream key (or set YOUTUBE_STREAM_KEY env)")
    parser.add_argument('--list-queue', action='store_true',
                        help="List videos in the queue")

    args = parser.parse_args()

    QUEUE_DIR.mkdir(exist_ok=True)
    OUTPUT_DIR.mkdir(exist_ok=True)

    if args.list_queue:
        videos = sorted(QUEUE_DIR.glob("*.mp4"))
        if not videos:
            print("Queue is empty.")
        for v in videos:
            size_mb = v.stat().st_size / (1024 * 1024)
            print(f"  {v.name} ({size_mb:.1f} MB)")
        return

    stream_key = args.stream_key or os.environ.get('YOUTUBE_STREAM_KEY')

    if args.stream_only:
        if not stream_key:
            sys.exit("ERROR: Set --stream-key or YOUTUBE_STREAM_KEY env var")
        stream_to_youtube(stream_key, replace_process=True)
        return

    # Generate songs
    generated = 0
    for i in range(args.count):
        print(f"\n>>> Generating song {i+1}/{args.count}")
        result = generate_one()
        if result:
            generated += 1
            print(f"\n  SUCCESS: {result['path']}")
        else:
            print(f"\n  FAILED: Skipping...")

    print(f"\n{'='*60}")
    print(f"Generated {generated}/{args.count} songs")
    print(f"Queue: {len(list(QUEUE_DIR.glob('*.mp4')))} videos ready")
    print(f"{'='*60}")

    if args.stream:
        if not stream_key:
            sys.exit("ERROR: Set --stream-key or YOUTUBE_STREAM_KEY env var")
        stream_to_youtube(stream_key, replace_process=True)


if __name__ == '__main__':
    main()
