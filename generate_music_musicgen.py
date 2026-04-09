#!/usr/bin/env python3
"""
Disney Stream — MusicGen Generator (Free Alternative)
=======================================================
Uses Meta's MusicGen model (audiocraft) as a free alternative to ACE-Step.
Runs locally on CPU or GPU. Smaller model = faster but shorter context.

Limitations:
- Max ~30 seconds per generation (for musicgen-small/medium)
- musicgen-large can do longer but needs more VRAM
- Generates in chunks and concatenates for long tracks

Install:
    pip install audiocraft

Usage:
    python3 generate_music_musicgen.py
    python3 generate_music_musicgen.py --model medium --chunks 12
"""

import os
import sys
import argparse
import json
import time
from pathlib import Path

try:
    import torch
    import torchaudio
    from audiocraft.models import MusicGen
    from audiocraft.data.audio import audio_write
    MUSICGEN_AVAILABLE = True
except ImportError:
    MUSICGEN_AVAILABLE = False

# Disney style prompts (shorter for MusicGen's context window)
DISNEY_STYLES = [
    {
        "id": "enchanted_kingdom",
        "label": "Enchanted Kingdom",
        "prompt": "romantic orchestral waltz, fairy tale ballroom, sweeping strings, French horn, magical, cinematic, 3/4 time",
    },
    {
        "id": "frozen_tundra",
        "label": "Frozen Tundra",
        "prompt": "epic orchestral ballad, icy Nordic fairy tale, powerful piano, soaring strings, dramatic, emotional build",
    },
    {
        "id": "circle_of_life",
        "label": "Circle of Life",
        "prompt": "African orchestral, tribal drums, savanna sunrise, majestic brass, epic cinematic, Zulu choir inspired",
    },
    {
        "id": "arabian_nights",
        "label": "Arabian Nights",
        "prompt": "Middle Eastern orchestral adventure, magic carpet, oud melody, Persian scales, shimmering strings",
    },
    {
        "id": "under_the_sea",
        "label": "Under the Sea",
        "prompt": "calypso steel drums, underwater world, bouncy brass, tropical reggae rhythm, joyful and playful",
    },
    {
        "id": "hakuna_matata",
        "label": "Hakuna Matata",
        "prompt": "carefree African tropical, acoustic guitar, ukulele, bouncy happy, sunshine and jungle",
    },
    {
        "id": "starlight_dream",
        "label": "Starlight Dream",
        "prompt": "nostalgic orchestral lullaby, celesta, dreamy harp arpeggios, gentle strings, golden age Hollywood",
    },
    {
        "id": "friendship_adventure",
        "label": "Friendship Adventure",
        "prompt": "warm Americana nostalgia, acoustic guitar, gentle banjo, folk, childhood memories, heartfelt",
    },
    {
        "id": "enchanted_forest",
        "label": "Enchanted Forest",
        "prompt": "lush orchestral fairy tale, ballet strings, flute, Tchaikovsky inspired, woodland creatures, magical",
    },
    {
        "id": "oceanic_voyage",
        "label": "Oceanic Voyage",
        "prompt": "Polynesian orchestral, ocean drums, ukulele, open sea, brave adventure, island spirit",
    },
    {
        "id": "ballroom_magic",
        "label": "Ballroom Magic",
        "prompt": "elegant classical waltz, grand ballroom, French horn romance, harp, fairy tale, timeless",
    },
    {
        "id": "winter_wonder",
        "label": "Winter Wonder",
        "prompt": "mystical Celtic-Nordic orchestral, ethereal, forest spirits, haunting, ancient magic, transformative",
    },
]

# Chunk duration in seconds (MusicGen handles up to 30s well)
CHUNK_SECONDS = 25


def check_musicgen():
    if not MUSICGEN_AVAILABLE:
        print("❌ audiocraft not installed.")
        print("   Run: pip install audiocraft")
        print("   Or: pip install git+https://github.com/facebookresearch/audiocraft.git")
        return False
    return True


def generate_chunk(model, prompt: str, duration: float = 25.0):
    """Generate a single audio chunk."""
    model.set_generation_params(duration=duration, top_k=250, top_p=0.0, temperature=1.0)
    with torch.no_grad():
        wav = model.generate([prompt])  # shape: [1, channels, samples]
    return wav[0]  # [channels, samples]


def concatenate_audio(chunks: list, sample_rate: int) -> "torch.Tensor":
    """Concatenate audio chunks into one tensor."""
    import torch
    return torch.cat(chunks, dim=-1)  # concat along time axis


def save_audio(tensor, sample_rate: int, output_path: str):
    """Save audio tensor to file."""
    import torchaudio
    # Ensure float32
    if tensor.dtype != torch.float32:
        tensor = tensor.float()
    # Normalize to [-1, 1]
    max_val = tensor.abs().max()
    if max_val > 1.0:
        tensor = tensor / max_val
    torchaudio.save(output_path, tensor.cpu(), sample_rate)
    print(f"   ✅ Saved: {output_path} ({tensor.shape[-1] / sample_rate:.1f}s)")


def main():
    parser = argparse.ArgumentParser(description="Generate Disney music with MusicGen")
    parser.add_argument("--model", default="medium", choices=["small", "medium", "large", "melody"],
                        help="MusicGen model size")
    parser.add_argument("--chunks", type=int, default=15,
                        help="Chunks per track (chunks × 25s = total duration). Default=15 → ~6 min")
    parser.add_argument("--output-dir", default="assets/audio")
    parser.add_argument("--tracks", type=int, default=12)
    parser.add_argument("--style", type=str, help="Generate only this style ID")
    parser.add_argument("--skip-existing", action="store_true", default=True)
    args = parser.parse_args()

    if not check_musicgen():
        sys.exit(1)

    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"\n🏰 Disney Stream — MusicGen Generator")
    print(f"   Model: musicgen-{args.model}")
    print(f"   Device: {device}")
    print(f"   Chunks per track: {args.chunks} × {CHUNK_SECONDS}s ≈ {args.chunks * CHUNK_SECONDS // 60} min")

    print(f"\n⬇️  Loading MusicGen model (this may take a minute)...")
    model = MusicGen.get_pretrained(f"facebook/musicgen-{args.model}")
    model = model.to(device)
    sample_rate = model.sample_rate
    print(f"   ✅ Model loaded. Sample rate: {sample_rate}Hz")

    os.makedirs(args.output_dir, exist_ok=True)

    styles = DISNEY_STYLES
    if args.style:
        styles = [s for s in DISNEY_STYLES if s["id"] == args.style]
        if not styles:
            print(f"❌ Unknown style: {args.style}")
            sys.exit(1)
    else:
        styles = DISNEY_STYLES[:args.tracks]

    generated = []

    for style in styles:
        output_path = os.path.join(args.output_dir, f"{style['id']}.wav")
        aac_path = output_path.replace(".wav", ".aac")

        if args.skip_existing and (os.path.exists(output_path) or os.path.exists(aac_path)):
            print(f"\n⏭️  Skip (exists): {style['label']}")
            generated.append(aac_path if os.path.exists(aac_path) else output_path)
            continue

        print(f"\n🎵 Generating: {style['label']}")
        print(f"   Prompt: {style['prompt'][:80]}...")

        chunks = []
        for i in range(args.chunks):
            print(f"   Chunk {i+1}/{args.chunks}...", end=" ", flush=True)
            t0 = time.time()
            chunk = generate_chunk(model, style["prompt"], CHUNK_SECONDS)
            elapsed = time.time() - t0
            print(f"{elapsed:.1f}s")
            chunks.append(chunk)

        print(f"   Merging {len(chunks)} chunks...")
        full_audio = concatenate_audio(chunks, sample_rate)
        save_audio(full_audio, sample_rate, output_path)

        # Convert to AAC
        import subprocess
        aac_result = subprocess.run(
            ["ffmpeg", "-y", "-i", output_path, "-c:a", "aac", "-b:a", "128k", aac_path],
            capture_output=True
        )
        if aac_result.returncode == 0:
            os.remove(output_path)
            final = aac_path
        else:
            final = output_path

        generated.append(final)

        # Save metadata
        with open(final.replace(".aac", ".json").replace(".wav", ".json"), "w") as f:
            json.dump({
                "style_id": style["id"],
                "label": style["label"],
                "prompt": style["prompt"],
                "model": f"musicgen-{args.model}",
                "chunks": args.chunks,
                "file": final,
            }, f, indent=2)

    # Update playlist
    list_path = os.path.join(args.output_dir, "audio_list.txt")
    with open(list_path, "w") as f:
        for path in sorted(Path(args.output_dir).glob("*.aac")):
            f.write(f"file '{path}'\n")
        for path in sorted(Path(args.output_dir).glob("*.wav")):
            f.write(f"file '{path}'\n")

    print(f"\n{'='*50}")
    print(f"✅ Generated {len(generated)} tracks")
    print(f"📋 Updated {list_path}")
    print(f"🎉 Ready! Run: ./stream.sh")


if __name__ == "__main__":
    main()
