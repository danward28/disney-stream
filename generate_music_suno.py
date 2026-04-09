#!/usr/bin/env python3
"""
Disney Stream — Suno API Music Generator (Alternative)
========================================================
Use this instead of generate_music.py if you prefer Suno's
quality and don't want to run ACE-Step locally.

Requires: pip install suno-api requests python-dotenv
Or use the unofficial Suno API wrapper.

IMPORTANT: Suno has copyright filters — use "inspired by" style
descriptions, not actual song names.

Usage:
    python3 generate_music_suno.py --api-key YOUR_KEY
"""

import os
import sys
import time
import json
import argparse
import requests
from pathlib import Path

# Unofficial Suno API base (self-hosted wrapper or suno-api.vercel.app)
SUNO_API_BASE = os.environ.get("SUNO_API_BASE", "https://suno-api.vercel.app")

# Same styles as generate_music.py but formatted for Suno's prompt style
# Suno works better with shorter, punchy prompts
DISNEY_STYLES_SUNO = [
    {
        "id": "enchanted_kingdom",
        "prompt": "romantic orchestral waltz, ballroom, fairy tale, sweeping strings, magical, cinematic",
        "style": "orchestral, classical, cinematic",
        "title": "Enchanted Kingdom",
    },
    {
        "id": "frozen_tundra",
        "prompt": "epic orchestral ballad, icy, Nordic, powerful piano, soaring strings, dramatic build",
        "style": "orchestral, epic, cinematic",
        "title": "Frozen Tundra",
    },
    {
        "id": "circle_of_life",
        "prompt": "African orchestral, tribal drums, savanna sunrise, majestic brass fanfare, epic cinematic",
        "style": "world, orchestral, epic",
        "title": "Circle of Life",
    },
    {
        "id": "arabian_nights",
        "prompt": "Middle Eastern orchestral, magic carpet, exotic scales, shimmering strings, adventure",
        "style": "world, orchestral, exotic",
        "title": "Arabian Nights",
    },
    {
        "id": "under_the_sea",
        "prompt": "calypso steel drums, underwater carnival, bouncy brass, tropical, joyful, reggae rhythm",
        "style": "calypso, world, upbeat",
        "title": "Under the Sea",
    },
    {
        "id": "hakuna_matata",
        "prompt": "carefree tropical, acoustic guitar, ukulele, bouncy brass, sunny jungle, lighthearted",
        "style": "folk, tropical, happy",
        "title": "Hakuna Matata",
    },
    {
        "id": "starlight_dream",
        "prompt": "nostalgic orchestral lullaby, celesta, dreamy harp, gentle strings, golden age Hollywood",
        "style": "orchestral, lullaby, nostalgic",
        "title": "Starlight Dream",
    },
    {
        "id": "friendship_adventure",
        "prompt": "warm Americana, acoustic guitar, gentle banjo, nostalgic folk, childhood warmth, tender",
        "style": "folk, Americana, warm",
        "title": "Friendship Adventure",
    },
    {
        "id": "enchanted_forest",
        "prompt": "lush orchestral fairy tale, ballet strings, flute bird calls, Tchaikovsky, woodland magic",
        "style": "orchestral, classical, romantic",
        "title": "Enchanted Forest",
    },
    {
        "id": "oceanic_voyage",
        "prompt": "Polynesian orchestral, ocean drums, ukulele, open sea adventure, brave and hopeful",
        "style": "world, folk, adventurous",
        "title": "Oceanic Voyage",
    },
    {
        "id": "ballroom_magic",
        "prompt": "elegant classical waltz, grand ballroom, French horn romance, fairy tale, shimmering harp",
        "style": "classical, waltz, elegant",
        "title": "Ballroom Magic",
    },
    {
        "id": "winter_wonder",
        "prompt": "mystical orchestral journey, Celtic-Nordic, ethereal choir, forest spirits, ancient magic",
        "style": "Celtic, orchestral, mystical",
        "title": "Winter Wonder",
    },
]


def generate_with_suno(style: dict, api_key: str, duration: int = 240) -> dict | None:
    """Generate a track using Suno API."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "prompt": style["prompt"],
        "tags": style["style"],
        "title": f"Disney Stream - {style['title']}",
        "make_instrumental": True,  # NO vocals — instrumental only
        "wait_audio": False,
    }

    print(f"\n🎵 Requesting: {style['title']}")
    print(f"   Style: {style['style']}")

    try:
        resp = requests.post(
            f"{SUNO_API_BASE}/api/custom_generate",
            json=payload,
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return data
    except requests.RequestException as e:
        print(f"   ❌ API error: {e}")
        return None


def poll_for_audio(task_id: str, api_key: str, max_wait: int = 300) -> str | None:
    """Poll until audio is ready, return audio URL."""
    headers = {"Authorization": f"Bearer {api_key}"}
    start = time.time()

    while time.time() - start < max_wait:
        try:
            resp = requests.get(
                f"{SUNO_API_BASE}/api/get?ids={task_id}",
                headers=headers,
                timeout=15,
            )
            data = resp.json()
            if isinstance(data, list) and len(data) > 0:
                item = data[0]
                status = item.get("status", "")
                if status == "complete":
                    return item.get("audio_url")
                elif status == "error":
                    print(f"   ❌ Generation failed: {item.get('error')}")
                    return None
            print(f"   ⏳ Status: {status or 'pending'}...")
            time.sleep(15)
        except Exception as e:
            print(f"   ⚠️  Poll error: {e}")
            time.sleep(10)

    print(f"   ❌ Timeout after {max_wait}s")
    return None


def download_audio(url: str, output_path: str) -> bool:
    """Download audio file from URL."""
    try:
        resp = requests.get(url, stream=True, timeout=60)
        resp.raise_for_status()
        with open(output_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        size_mb = os.path.getsize(output_path) / 1024 / 1024
        print(f"   ✅ Downloaded: {output_path} ({size_mb:.1f} MB)")
        return True
    except Exception as e:
        print(f"   ❌ Download error: {e}")
        return False


def main():
    global SUNO_API_BASE
    parser = argparse.ArgumentParser(description="Generate Disney music with Suno API")
    parser.add_argument("--api-key", default=os.environ.get("SUNO_API_KEY"), help="Suno API key")
    parser.add_argument("--output-dir", default="assets/audio")
    parser.add_argument("--tracks", type=int, default=12)
    parser.add_argument("--api-base", default=SUNO_API_BASE)
    args = parser.parse_args()

    if not args.api_key:
        print("❌ Suno API key required. Set SUNO_API_KEY env var or pass --api-key")
        print("   Get key at: https://suno.ai or use self-hosted wrapper")
        sys.exit(1)

    SUNO_API_BASE = args.api_base

    os.makedirs(args.output_dir, exist_ok=True)

    styles = DISNEY_STYLES_SUNO[:args.tracks]
    print(f"\n🏰 Disney Stream — Suno Music Generator")
    print(f"   API: {SUNO_API_BASE}")
    print(f"   Generating {len(styles)} instrumental tracks\n")

    generated = []

    for style in styles:
        output_path = os.path.join(args.output_dir, f"{style['id']}.mp3")
        if os.path.exists(output_path):
            print(f"⏭️  Skip (exists): {style['title']}")
            generated.append(output_path)
            continue

        result = generate_with_suno(style, args.api_key)
        if not result:
            continue

        # Handle both single task and list responses
        tasks = result if isinstance(result, list) else [result]
        for task in tasks[:1]:  # take first variant
            task_id = task.get("id") or task.get("clip_id")
            if not task_id:
                continue

            audio_url = poll_for_audio(task_id, args.api_key)
            if audio_url:
                if download_audio(audio_url, output_path):
                    generated.append(output_path)

                    # Save metadata
                    with open(output_path.replace(".mp3", ".json"), "w") as f:
                        json.dump({
                            "style_id": style["id"],
                            "title": style["title"],
                            "prompt": style["prompt"],
                            "suno_id": task_id,
                            "file": output_path,
                        }, f, indent=2)

    # Rebuild audio list
    list_path = os.path.join(args.output_dir, "audio_list.txt")
    with open(list_path, "w") as f:
        for path in generated:
            f.write(f"file '{path}'\n")

    print(f"\n✅ Generated {len(generated)} tracks")
    print(f"📋 Updated {list_path}")
    print(f"🎉 Ready! Run: ./stream.sh")


if __name__ == "__main__":
    main()
