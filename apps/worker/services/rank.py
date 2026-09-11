import json
from openai import OpenAI
from models import ClipCandidate, TranscriptSegment


CLIP_SCHEMA = {
    "type": "object",
    "properties": {
        "clips": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start": {"type": "number"},
                    "end": {"type": "number"},
                    "title": {"type": "string"},
                    "hook": {"type": "string"},
                    "score": {"type": "integer", "minimum": 0, "maximum": 100},
                    "reasons": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["start", "end", "title", "hook", "score", "reasons"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["clips"],
    "additionalProperties": False,
}


def rank_clip_candidates(
    segments: list[TranscriptSegment],
    api_key: str,
    model: str,
    max_clips: int,
) -> list[ClipCandidate]:
    client = OpenAI(api_key=api_key)

    transcript = "\n".join(
        f"[{s.start:.1f}-{s.end:.1f}] {s.text}" for s in segments
    )

    prompt = f"""
You are the clip-selection engine for a short-form video product.
Choose up to {max_clips} moments from the timestamped transcript below.

A strong candidate:
- starts with a hook or can begin cleanly without missing context
- contains a complete idea/story/payoff
- is usually 20-60 seconds long
- is surprising, useful, emotional, funny, contrarian, specific, or highly shareable
- does not rely heavily on content outside the selected interval

Rules:
- start/end must align reasonably with the supplied timestamps
- do not invent dialogue
- avoid overlapping candidates unless both are unusually strong
- score 0-100 for short-form potential
- sort best first
- hook should quote or closely paraphrase the opening idea, not fabricate a sensational claim

Transcript:
{transcript}
""".strip()

    response = client.responses.create(
        model=model,
        input=prompt,
        text={
            "format": {
                "type": "json_schema",
                "name": "clip_candidates",
                "schema": CLIP_SCHEMA,
                "strict": True,
            }
        },
    )

    payload = json.loads(response.output_text)
    clips = [ClipCandidate(**clip) for clip in payload["clips"]]
    return sorted(clips, key=lambda c: c.score, reverse=True)[:max_clips]
