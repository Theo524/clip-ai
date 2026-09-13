# Clip AI v22 · Long-Term Beta Freeze (M6)

Clip AI turns long English-language videos into ranked, reframed, captioned, ready-to-post vertical Shorts. M6 is the final v22 stabilization milestone: fewer maintenance surprises, safer disk cleanup, dual-audio handling and measurable processing performance.

## M6 highlights

- **Dual/multi-audio handling:** choose Auto or Track 1–4 before analysis. Auto follows the source default track; explicit selection is useful for dubbed anime and multilingual files.
- Multi-audio sources are normalized to one stable working track so transcription and final renders stay on the same audio.
- Transcript-cache keys include the selected audio track, preventing an English-track transcript from being reused for a Japanese track (or vice versa).
- **Free space** on the Projects page removes the original source/normalized working copy only after at least one finished render exists. Finished Shorts, covers, transcript, titles, descriptions, tags and export packages remain.
- Disposable preview/caption/reframe files are removed by project cleanup.
- The global transcript cache is bounded: entries older than 30 days are removable and cleanup caps it at roughly 512 MB. Per-project transcripts are never deleted by this cache policy.
- Project cards show analysis duration and selected audio track when useful.
- Analysis stores lightweight performance metrics for future troubleshooting without collecting anything externally.
- Project schema advances to 24 with additive migration defaults.
- M1–M5 behavior remains intact, including the classic Anime Auto framing: true-black 9:16 canvas, Compact central picture, calmer tracking and Cinematic captions locked low inside the picture.

## Update on Windows

Keep the existing project at:

`C:\Users\PC\Downloads\clip-ai-starter`

Put the M6 ZIP in Downloads, extract it, then run the included updater:

```bat
cd /d C:\Users\PC\Downloads
if exist "clip-ai-starter-v22-m6" rmdir /s /q "clip-ai-starter-v22-m6"
tar -xf "clip-ai-v22-m6-beta-freeze.zip"
call "C:\Users\PC\Downloads\clip-ai-starter-v22-m6\UPDATE_CLIP_AI_M6.bat"
```

The updater preserves `.git`, `.venv`, saved work/projects, local `.env` files and frontend `node_modules`; removes stale application code/tests and `.next`; runs backend tests; installs/builds the frontend; clears the dev cache again; then starts Clip AI.

## Git checkpoint

After one real anime/normal-video test:

```bat
cd /d C:\Users\PC\Downloads\clip-ai-starter
git status
git add .
git commit -m "Freeze Clip AI v22 long-term beta"
git push
```

## Validation

Packaged backend suite: **92 passed**. Python source compiles. TypeScript syntax parsing is clean; full React/Next type resolution is intentionally left to the Windows updater because this package does not include `node_modules`.
