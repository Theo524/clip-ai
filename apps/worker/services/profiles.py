from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProcessingProfile:
    name: str
    chunk_seconds: int
    cpu_threads: int
    render_preset: str
    description: str


PROFILES = {
    "low-memory": ProcessingProfile(
        name="low-memory",
        chunk_seconds=300,
        cpu_threads=2,
        render_preset="veryfast",
        description="Small chunks and fewer CPU threads for 8 GB or busy PCs.",
    ),
    "balanced": ProcessingProfile(
        name="balanced",
        chunk_seconds=600,
        cpu_threads=4,
        render_preset="veryfast",
        description="Recommended balance of speed, memory and reliability.",
    ),
    "fast": ProcessingProfile(
        name="fast",
        chunk_seconds=1200,
        cpu_threads=6,
        render_preset="faster",
        description="Larger chunks for higher-memory desktops.",
    ),
}


def get_processing_profile(name: str | None) -> ProcessingProfile:
    return PROFILES.get((name or "balanced").strip().lower(), PROFILES["balanced"])
