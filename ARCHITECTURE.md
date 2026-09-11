# Clip AI architecture — Milestone 7

```text
Browser / Next.js
      |
      v
FastAPI worker
      |
      +--> FFmpeg audio extraction
      +--> local faster-whisper -> transcript.json
      +--> local/OpenAI clip ranking -> timestamp candidates
      +--> OpenCV visual sampler
      |       +--> single-face tracking
      |       +--> multi-face/group centre
      |       +--> motion centroid
      |       +--> safe centre fallback
      |
      +--> adaptive layout chooser
      |       +--> Fill      (full 9:16 subject crop)
      |       +--> Focus     (large central 4:5-ish crop, dark margins)
      |       +--> Backdrop  (same central crop + blurred canvas)
      |       +--> Preserve  (already-vertical source)
      |
      +--> caption preset chooser
      |       +--> Viral Pop
      |       +--> Cinematic
      |       +--> Clean
      |       +--> Meme
      |
      +--> caption placement constrained to the actual picture area
      v
FFmpeg 720×1280 adaptive render
```

## The hard rule in Milestone 7

The final file is always 9:16, but the source picture does not have to occupy every pixel. **Captions always live on the actual video picture**, never in the decorative black/blurred space above or below it.

## Focus layout

Focus replaces the old full-widescreen Cinema mode. It crops the source to a large central portrait-friendly window rather than shrinking the entire 16:9 composition into the phone frame.

Balanced Focus is **720×900** (4:5) centered inside the 720×1280 output. That leaves 190 px above and below as quiet dark breathing room. The crop still follows the subject/group horizontally.

Frame size presets:

- Compact: 720×800
- Balanced: 720×900 (default)
- Immersive: 720×1040

## Backdrop layout

Backdrop uses the exact same central crop/window as Focus. A subdued blurred copy fills the rest of the vertical canvas. This keeps the useful framing consistent; blur is a style choice, not a different composition.

## Caption placement

- Cinematic: lower part of the actual picture window.
- Viral/Meme: more central/lower-middle inside the picture.
- Clean: lower-middle inside the picture.

ASS `\\pos()` positioning is calculated from the content-window geometry, so text cannot drift into the black/blurred margins when Focus/Backdrop sizes change.

## Group-aware framing

When OpenCV sees multiple similarly important faces, the tracker uses the centre of the group rather than snapping to the single largest face. This reduces the chance of cutting one character out of a dialogue scene.

## Development note

This remains deliberately lightweight for an 8 GB development laptop. Production can later add shot-change detection, stronger person detectors, saliency models, true active-speaker tracking, and 1080×1920 rendering.
