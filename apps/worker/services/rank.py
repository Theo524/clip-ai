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
- starts on a clean sentence/thought boundary, ideally with a hook
- does NOT begin with context-dependent fragments such as "and...", "but...", "because..." unless that wording is clearly an intentional hook
- contains a complete idea, mini-story, argument, reveal, joke, or takeaway
- ends on the payoff/conclusion rather than continuing into unrelated chatter
- is usually 20-60 seconds long, with roughly 25-50 seconds preferred when the idea is complete
- is surprising, useful, emotional, funny, contrarian, specific, or highly shareable
- makes sense to a viewer who has not seen the surrounding video

Editing rules:
- choose the tightest complete version of a moment; trim setup that is not needed
- do not cut off the first or last thought mid-sentence
- if a payoff lands, do not keep extra filler after it merely to make the clip longer
- start/end must align reasonably with the supplied timestamps
- do not invent dialogue
- avoid overlapping or near-duplicate candidates unless both are unusually strong
- score 0-100 for short-form potential; boundary cleanliness and completeness matter as much as excitement
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
