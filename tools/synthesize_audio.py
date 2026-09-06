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

def encode_wave(source: Path, destination: Path) -> None:
    import lameenc

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


def concatenate_mp3_sources(
    source_names: list[str], audio_directory: Path, destination: Path
) -> None:
    """Join compatible source MP3 streams without changing the narrator."""
    payloads = []
    for source_name in source_names:
        source = audio_directory / source_name
        if not source.is_file():
            raise FileNotFoundError(f"Missing source narration: {source}")
        payload = source.read_bytes()
        if len(payload) < 500:
            raise RuntimeError(f"Source MP3 is unexpectedly small: {source}")
        payloads.append(payload)
    destination.write_bytes(b"".join(payloads))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=Path, default=Path("tools/audio_jobs.json"))
    parser.add_argument("--output", type=Path, default=Path("content/i18n/en/audio"))
    parser.add_argument("--temp", type=Path, default=Path("tmp/audio-wave"))
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        help="Generate only the named text ID (repeat for multiple IDs).",
    )
    args = parser.parse_args()

    jobs = json.loads(args.jobs.read_text(encoding="utf-8"))
    if args.only:
        missing = sorted(set(args.only) - set(jobs))
        if missing:
            raise KeyError(f"Unknown audio job IDs: {', '.join(missing)}")
        jobs = {text_id: jobs[text_id] for text_id in args.only}
    args.output.mkdir(parents=True, exist_ok=True)
    concatenated_jobs = {
        text_id: job for text_id, job in jobs.items() if job.get("source_filenames")
    }
    speech_jobs = {
        text_id: job for text_id, job in jobs.items() if not job.get("source_filenames")
    }

    for job in concatenated_jobs.values():
        concatenate_mp3_sources(
            job["source_filenames"], args.output, args.output / job["filename"]
        )

    if speech_jobs:
        args.temp.mkdir(parents=True, exist_ok=True)
        helper = Path(__file__).resolve().parent / "synthesize_wave.ps1"
        speech_jobs_path = args.temp / "speech_jobs.json"
        speech_jobs_path.write_text(
            json.dumps(speech_jobs, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(helper),
                "-JobsPath",
                str(speech_jobs_path.resolve()),
                "-OutputDirectory",
                str(args.temp.resolve()),
            ],
            check=True,
        )

    for text_id, job in speech_jobs.items():
        wave_path = args.temp / f"{text_id}.wav"
        destination = args.output / job["filename"]
        encode_wave(wave_path, destination)
        wave_path.unlink()
    if args.temp.exists():
        shutil.rmtree(args.temp)
    print(
        f"Generated {len(speech_jobs)} local TTS segments and assembled "
        f"{len(concatenated_jobs)} segments from the original narration."
    )


if __name__ == "__main__":
    main()
