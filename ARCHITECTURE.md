# Clip AI Architecture — Milestone 10

## Pipeline

```text
video upload
  ↓
FFmpeg audio extraction/chunking
  ↓
faster-whisper
  ├─ segment timestamps
  └─ word timestamps
  ↓
transcript.json
  ↓
M10 moment selector
  ├─ candidate window generation
  ├─ opening / hook scoring
  ├─ completeness + payoff scoring
  ├─ clean-boundary scoring
  ├─ filler / repetition penalties
  ├─ payoff-tail trimming preference
  └─ overlap / semantic-near-duplicate suppression
  ↓
ranked clip candidates
  ↓
selected clip
  ├─ lightweight visual sampling
  │    ├─ horizontal subject/group reframe plan
  │    └─ coarse vertical face occupancy
  └─ word timings
       ↓
caption phrase builder
  ├─ stable phrase event
  └─ active-word overlay events
       ↓
caption-safe zone selection
       ↓
ASS caption track
       ↓
FFmpeg adaptive 720×1280 render
```

## Candidate generation

The local selector evaluates transcript windows of roughly **18–65 seconds**. It does not simply split the transcript into fixed intervals.

Candidate starts and ends are based on Whisper transcript segments, with preference for:

- complete sentence endings
- speech pauses between segments
- clean standalone openings
- 24–48 second finished ideas

A tiny pre/post-roll is added to the chosen timestamp so the final MP4 does not clip a phoneme at an exact speech boundary.

## Selection score

The local score combines several signals:

### Opening quality

Strong positive signals:

- direct hook language
- a question-led opener
- concrete numbers/details
- a clean standalone first thought

Negative signals:

- context-dependent starts such as “and…”, “but…”, “because…”, “then…”
- pronoun-heavy starts that obviously rely on unseen context

### Narrative / idea completeness

The selector rewards:

- contrast/pivot language
- a takeaway, reveal, lesson or conclusion
- endings that actually land on that payoff

If a payoff has already landed and the candidate continues into unrelated or low-value chatter, the longer version receives a substantial penalty so the tighter edit wins.

### Speech quality

Additional signals include:

- useful speaking density
- enough substance for a standalone Short
- low filler density
- lower repetition
- specific/high-interest language

## Deduplication

Candidates are sorted by quality and tighter duration. A candidate is rejected if it heavily overlaps a stronger selected moment or if its opening is nearly identical to an already selected candidate.

This reduces the common failure mode where the top five “clips” are just slightly shifted versions of one good 40-second section.

## OpenAI ranking path

`services/rank.py` remains the optional hosted selector. Its prompt now mirrors Milestone 10's editorial rules: choose the tightest complete version, avoid mid-thought boundaries, stop after the payoff, and value standalone context as highly as excitement.

## Rendering system

Milestone 9 rendering remains unchanged:

- **Fill** — full 9:16 smart crop.
- **Focus** — large central portrait-friendly crop on a quiet dark canvas.
- **Backdrop** — Focus crop with a blurred canvas.
- **Preserve** — already-vertical source.

Captions remain inside the actual picture area, with word-level timing and stable active-word emphasis for Viral/Meme presets.
