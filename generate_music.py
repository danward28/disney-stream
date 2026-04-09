#!/usr/bin/env python3
"""
Disney Stream - AI Music Generator
===================================
Generates Disney-inspired instrumental tracks using ACE-Step 1.5.
Each track is ~6 minutes and evokes a different Disney song style
WITHOUT copying any copyrighted music — purely style/mood-based prompts.

Usage:
    python3 generate_music.py
    python3 generate_music.py --tracks 5 --duration 360
    python3 generate_music.py --style "frozen"   # generate only that style
"""

import os
import sys
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

# ============================================================
# Disney Style Prompts
# Each entry evokes a well-known Disney film's musical world
# without referencing any specific copyrighted song or lyrics.
# ============================================================

DISNEY_STYLES = [
    {
        "id": "enchanted_kingdom",
        "label": "Enchanted Kingdom (Beauty and the Beast style)",
        "prompt": (
            "romantic orchestral waltz, lush strings and French horn, golden ballroom grandeur, "
            "candlelit warmth, sweeping cinematic melody, fairy tale elegance, harpsichord accents, "
            "rising orchestral swell, emotional piano countermelody, magical realism, 3/4 time, "
            "instrumental only, no vocals, high quality studio recording"
        ),
        "tags": "fairy tale, orchestral, waltz, romantic, magical",
    },
    {
        "id": "frozen_tundra",
        "label": "Frozen Tundra (Frozen style)",
        "prompt": (
            "epic orchestral ballad, powerful emotional piano, icy crystalline textures, "
            "soaring strings, Nordic choir pads, dramatic cinematic build, cold majestic atmosphere, "
            "crescendo to triumphant resolution, Scandinavian folk influence, snowflake delicate motifs, "
            "instrumental only, no vocals, high quality orchestral recording"
        ),
        "tags": "epic, orchestral, icy, powerful, Nordic",
    },
    {
        "id": "circle_of_life",
        "label": "Circle of Life (Lion King style)",
        "prompt": (
            "African-inspired orchestral, sweeping savanna sunrise, tribal percussion and talking drums, "
            "Zulu choir atmosphere, soaring brass fanfare, warm cello melody, Hans Zimmer cinematic style, "
            "sunrise over the plains, majestic and uplifting, natural world grandeur, "
            "instrumental only, no vocals, high quality epic orchestral"
        ),
        "tags": "African, orchestral, epic, tribal, cinematic",
    },
    {
        "id": "arabian_nights",
        "label": "Arabian Nights (Aladdin style)",
        "prompt": (
            "Middle Eastern orchestral adventure, shimmering strings, oud-inspired melody, "
            "magic carpet soaring, Persian scales, finger cymbals and doumbek rhythms, "
            "whimsical adventure theme, glittering bazaar atmosphere, moonlit desert magic, "
            "playful and sweeping cinematic, instrumental only, no vocals, studio quality"
        ),
        "tags": "Middle Eastern, orchestral, adventure, exotic, magical",
    },
    {
        "id": "under_the_sea",
        "label": "Under the Sea (Little Mermaid style)",
        "prompt": (
            "calypso-infused orchestral, steel pan drums, underwater carnival atmosphere, "
            "bouncy brass section, bubbly woodwinds, reggae-tinged rhythm, playful and joyful, "
            "ocean shimmer in strings, carefree tropical energy, bioluminescent wonder, "
            "instrumental only, no vocals, bright and lively studio recording"
        ),
        "tags": "calypso, tropical, bouncy, underwater, joyful",
    },
    {
        "id": "hakuna_matata",
        "label": "Hakuna Matata (Lion King style)",
        "prompt": (
            "carefree African-Caribbean fusion, bouncy acoustic guitar, laid-back tropical percussion, "
            "happy-go-lucky brass, ukulele strumming, sunny jungle afternoon, joyful woodwind melody, "
            "feel-good lighthearted groove, no worries atmosphere, warm and playful, "
            "instrumental only, no vocals, warm summer recording"
        ),
        "tags": "carefree, tropical, acoustic, happy, bouncy",
    },
    {
        "id": "starlight_dream",
        "label": "Upon a Starlight Dream (Pinocchio/Cinderella style)",
        "prompt": (
            "nostalgic golden-age orchestral lullaby, gentle celesta and glockenspiel, "
            "warm string quartet, dreamy harp arpeggios, soft pizzicato, twinkling night sky, "
            "innocent childlike wonder, bedtime storybook warmth, 1940s Hollywood magic, "
            "lullaby tempo, tender and hopeful, instrumental only, no vocals, intimate recording"
        ),
        "tags": "lullaby, nostalgic, gentle, dreamy, golden age",
    },
    {
        "id": "friendship_adventure",
        "label": "Friendship Adventure (Toy Story style)",
        "prompt": (
            "warm Americana nostalgia, acoustic guitar fingerpicking, gentle banjo, "
            "Randy Newman inspired orchestral folk, childhood memory warmth, "
            "sunny day in the backyard, trust and loyalty theme, gentle strings, "
            "tender heartfelt melody, ragtime piano accents, roots music warmth, "
            "instrumental only, no vocals, homespun recording quality"
        ),
        "tags": "Americana, nostalgic, acoustic, warm, folk",
    },
    {
        "id": "enchanted_forest",
        "label": "Enchanted Forest (Snow White / Sleeping Beauty style)",
        "prompt": (
            "lush orchestral fairy tale, sweeping romantic strings, flute bird calls, "
            "Tchaikovsky-inspired ballet music, forest spirits and woodland creatures, "
            "dappled sunlight through trees, magical transformation moment, "
            "grand classical Hollywood orchestra, innocent wonder, "
            "instrumental only, no vocals, lush studio orchestral"
        ),
        "tags": "classical, orchestral, fairy tale, lush, romantic",
    },
    {
        "id": "oceanic_voyage",
        "label": "Oceanic Voyage (Moana style)",
        "prompt": (
            "Polynesian orchestral, oceanic drums and log percussion, "
            "ukulele and guitar interplay, open sea adventure, island wind and wave, "
            "Lin-Manuel Miranda inspired cinematic folk, ancestral spirit calling, "
            "soaring strings over the horizon, Pacific Islander musical scales, "
            "brave and hopeful, instrumental only, no vocals, cinematic studio quality"
        ),
        "tags": "Polynesian, oceanic, adventure, folk, cinematic",
    },
    {
        "id": "ballroom_magic",
        "label": "Ballroom Magic (Cinderella style)",
        "prompt": (
            "elegant classical waltz, full orchestral ballroom, glittering chandelier, "
            "sweeping violin melody, French horn romance, pumpkin carriage magic, "
            "fairy godmother wonder, midnight clock tension builds, glass slipper delicacy, "
            "shimmering strings and harp, timeless fairytale romance, "
            "instrumental only, no vocals, grand orchestral recording"
        ),
        "tags": "waltz, elegant, classical, ballroom, fairytale",
    },
    {
        "id": "winter_wonder",
        "label": "Winter Wonder (Frozen 2 style)",
        "prompt": (
            "mystical orchestral journey, ancient forest spirits, haunting female choir textures, "
            "ethereal woodwinds, Celtic-Nordic fusion, dark forest discovery, "
            "memory and mystery, elemental spirits calling, water and earth themes, "
            "building orchestral revelation, emotional transformation, "
            "instrumental only, no vocals, cinematic epic quality"
        ),
        "tags": "mystical, Celtic, Norse, ethereal, epic",
    },
]


def check_ace_step():
    """Check if ACE-Step is available."""
    ace_step_path = Path("ace-step")
    if not ace_step_path.exists():
        print("❌ ACE-Step not found. Run setup.sh first.")
        print("   Or: git clone https://github.com/ace-step/ACE-Step.git ace-step && cd ace-step && pip install -e .")
        return False
    return True


def generate_track_ace_step(style: dict, output_path: str, duration: int = 360):
    """Generate a single track using ACE-Step."""
    print(f"\n🎵 Generating: {style['label']}")
    print(f"   Prompt: {style['prompt'][:80]}...")
    print(f"   Output: {output_path}")

    cmd = [
        "python3", "ace-step/inference.py",
        "--prompt", style["prompt"],
        "--duration", str(duration),
        "--output", output_path,
        "--format", "wav",
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            # Try alternate entry point
            cmd[1] = "ace-step/acestep/inference.py"
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)

        if result.returncode == 0:
            print(f"   ✅ Done")
            return True
        else:
            print(f"   ❌ Error: {result.stderr[-500:]}")
            return False
    except subprocess.TimeoutExpired:
        print("   ❌ Timeout after 10 minutes")
        return False
    except FileNotFoundError:
        # Try the gradio/Python import approach
        return generate_track_ace_step_python(style, output_path, duration)


def generate_track_ace_step_python(style: dict, output_path: str, duration: int = 360):
    """Fallback: generate using ACE-Step Python API."""
    prompt_escaped = style['prompt'].replace('"', '\\"')
    script = (
        "import sys\n"
        "sys.path.insert(0, 'ace-step')\n"
        "try:\n"
        "    from acestep.pipeline import ACEStepPipeline\n"
        "except ImportError:\n"
        "    from ace_step.pipeline import ACEStepPipeline\n"
        "import soundfile as sf\n"
        "pipeline = ACEStepPipeline(\n"
        "    checkpoint_dir='ace-step/checkpoints',\n"
        "    device='auto',\n"
        ")\n"
        f"audio, sr = pipeline(\n"
        f'    prompt="{prompt_escaped}",\n'
        f"    duration={duration},\n"
        "    seed=-1,\n"
        ")\n"
        f"sf.write('{output_path}', audio, sr)\n"
        f"print('Saved to {output_path}')\n"
    )
    try:
        result = subprocess.run(
            ["python3", "-c", script],
            capture_output=True, text=True, timeout=600
        )
        if result.returncode == 0:
            print(f"   ✅ Done (Python API)")
            return True
        else:
            print(f"   ❌ Python API error: {result.stderr[-300:]}")
            return False
    except Exception as e:
        print(f"   ❌ Exception: {e}")
        return False


def convert_to_aac(wav_path: str) -> str:
    """Convert WAV to AAC for smaller file size and FFmpeg compatibility."""
    aac_path = wav_path.replace(".wav", ".aac")
    cmd = [
        "ffmpeg", "-y", "-i", wav_path,
        "-c:a", "aac", "-b:a", "128k",
        aac_path
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode == 0:
        os.remove(wav_path)
        return aac_path
    return wav_path


def update_audio_list(audio_dir: str):
    """Rebuild audio_list.txt from all audio files in the directory."""
    audio_files = sorted(
        list(Path(audio_dir).glob("*.aac")) +
        list(Path(audio_dir).glob("*.wav")) +
        list(Path(audio_dir).glob("*.mp3"))
    )

    list_path = os.path.join(audio_dir, "audio_list.txt")
    with open(list_path, "w") as f:
        for af in audio_files:
            if af.name != "audio_list.txt":
                f.write(f"file '{af}'\n")

    print(f"\n📋 Updated {list_path} with {len(audio_files)} tracks")
    return list_path


def main():
    parser = argparse.ArgumentParser(description="Generate Disney-style music for streaming")
    parser.add_argument("--tracks", type=int, default=12, help="Number of tracks to generate")
    parser.add_argument("--duration", type=int, default=360, help="Duration per track in seconds")
    parser.add_argument("--output-dir", default="assets/audio", help="Output directory")
    parser.add_argument("--style", type=str, help="Generate only this style ID (see list below)")
    parser.add_argument("--list-styles", action="store_true", help="List all available styles")
    parser.add_argument("--skip-existing", action="store_true", default=True,
                        help="Skip styles that already have an output file")
    args = parser.parse_args()

    if args.list_styles:
        print("\n🎭 Available Disney Styles:\n")
        for s in DISNEY_STYLES:
            print(f"  {s['id']:25s} → {s['label']}")
        return

    if not check_ace_step():
        sys.exit(1)

    os.makedirs(args.output_dir, exist_ok=True)

    # Select which styles to generate
    styles_to_gen = DISNEY_STYLES
    if args.style:
        styles_to_gen = [s for s in DISNEY_STYLES if s["id"] == args.style]
        if not styles_to_gen:
            print(f"❌ Unknown style: {args.style}. Use --list-styles to see options.")
            sys.exit(1)
    else:
        styles_to_gen = DISNEY_STYLES[:args.tracks]

    print(f"\n🏰 Disney Stream Music Generator")
    print(f"   Generating {len(styles_to_gen)} tracks × {args.duration}s each")
    print(f"   Total audio: ~{len(styles_to_gen) * args.duration // 60} minutes")
    print(f"   Output: {args.output_dir}/\n")

    generated = []
    skipped = []
    failed = []

    for style in styles_to_gen:
        output_wav = os.path.join(args.output_dir, f"{style['id']}.wav")
        output_aac = os.path.join(args.output_dir, f"{style['id']}.aac")

        # Skip if already exists
        if args.skip_existing and (os.path.exists(output_wav) or os.path.exists(output_aac)):
            print(f"⏭️  Skipping (exists): {style['label']}")
            skipped.append(style["id"])
            continue

        success = generate_track_ace_step(style, output_wav, args.duration)

        if success:
            # Convert to AAC
            final_path = convert_to_aac(output_wav)
            generated.append(final_path)

            # Save metadata
            meta = {
                "style_id": style["id"],
                "label": style["label"],
                "prompt": style["prompt"],
                "tags": style["tags"],
                "duration_seconds": args.duration,
                "file": final_path,
            }
            meta_path = output_wav.replace(".wav", ".json").replace(".aac", ".json")
            with open(meta_path, "w") as f:
                json.dump(meta, f, indent=2)
        else:
            failed.append(style["id"])

    # Update playlist
    update_audio_list(args.output_dir)

    # Summary
    print(f"\n{'='*50}")
    print(f"✅ Generated: {len(generated)} tracks")
    print(f"⏭️  Skipped:   {len(skipped)} tracks (already exist)")
    print(f"❌ Failed:    {len(failed)} tracks")
    if failed:
        print(f"   Failed: {', '.join(failed)}")
    print(f"\n🎉 Ready to stream! Run: ./stream.sh")


if __name__ == "__main__":
    main()
