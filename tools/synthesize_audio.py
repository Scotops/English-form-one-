#!/usr/bin/env python3
"""Generate new/corrected ADT MP3 segments entirely on the local computer."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import wave
from pathlib import Path

VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if VENDOR_DIR.is_dir():
    sys.path.insert(0, str(VENDOR_DIR))

import lameenc


def encode_wave(source: Path, destination: Path) -> None:
    with wave.open(str(source), "rb") as stream:
        channels = stream.getnchannels()
        sample_width = stream.getsampwidth()
        sample_rate = stream.getframerate()
        frames = stream.readframes(stream.getnframes())
    if channels != 1 or sample_width != 2:
        raise ValueError(
            f"Expected 16-bit mono WAV for {source.name}; got channels={channels}, width={sample_width}"
        )
    encoder = lameenc.Encoder()
    encoder.set_bit_rate(64)
    encoder.set_in_sample_rate(sample_rate)
    encoder.set_channels(channels)
    encoder.set_quality(2)
    payload = encoder.encode(frames) + encoder.flush()
    if len(payload) < 500:
        raise RuntimeError(f"Encoded MP3 is unexpectedly small: {destination}")
    destination.write_bytes(payload)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=Path, default=Path("tools/audio_jobs.json"))
    parser.add_argument("--output", type=Path, default=Path("content/i18n/en/audio"))
    parser.add_argument("--temp", type=Path, default=Path("tmp/audio-wave"))
    args = parser.parse_args()

    jobs = json.loads(args.jobs.read_text(encoding="utf-8"))
    args.output.mkdir(parents=True, exist_ok=True)
    args.temp.mkdir(parents=True, exist_ok=True)
    helper = Path(__file__).resolve().parent / "synthesize_wave.ps1"
    subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(helper),
            "-JobsPath",
            str(args.jobs.resolve()),
            "-OutputDirectory",
            str(args.temp.resolve()),
        ],
        check=True,
    )

    for text_id, job in jobs.items():
        wave_path = args.temp / f"{text_id}.wav"
        destination = args.output / job["filename"]
        encode_wave(wave_path, destination)
        wave_path.unlink()
    shutil.rmtree(args.temp)
    print(f"Generated {len(jobs)} local MP3 audio segments.")


if __name__ == "__main__":
    main()

