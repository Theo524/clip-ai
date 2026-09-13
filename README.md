# Clip AI v22 M5 · Editing & Workflow

Clip AI turns long English-language videos into ranked, reframed, captioned, ready-to-post vertical Shorts. M5 keeps the v22 intelligence work and makes the editing loop much faster and safer.

## M5 highlights

- Anime Auto keeps the M4.2 black-canvas central frame, but Cinematic captions are now explicitly locked low inside that frame instead of drifting into the middle because of face-band scoring.
- Quick Preview renders only the first 9 seconds at 540×960 so framing/caption placement can be checked before a full render.
- Clip length preference: Auto, Short, Balanced, Longer story. These are soft ranking guides; natural sentence/story endings still win over arbitrary cutoffs.
- Render #1 only or Render all 3 from the Best 3 panel.
- "Not good · replace" can store a reason such as bad moment, too short, bad ending, wrong crop or duplicate before moving to the next suggestion.
- Private per-project notes are saved locally.
- Caption sync has ±100 ms nudge buttons plus reset.
- Preview renders do not appear in Saved renders.
- M2.1 memory-safe Whisper, M3 metadata, M4 visual intelligence and v21 recovery/checkpointing remain intact.

## Update on Windows

Keep the existing project at:

`C:\Users\PC\Downloads\clip-ai-starter`

Put the M5 ZIP in Downloads, extract it, then run the included updater from the extracted temporary folder. It preserves `.git`, `.venv`, saved projects/work media, local `.env` files and frontend `node_modules` while replacing application code and tests.

```bat
cd /d C:\Users\PC\Downloads
if exist "clip-ai-starter-v22-m5" rmdir /s /q "clip-ai-starter-v22-m5"
tar -xf "clip-ai-v22-m5-editing-workflow.zip"
call "C:\Users\PC\Downloads\clip-ai-starter-v22-m5\UPDATE_CLIP_AI_M5.bat"
```

## Git checkpoint

After testing one real project:

```bat
cd /d C:\Users\PC\Downloads\clip-ai-starter
git status
git add .
git commit -m "Complete Clip AI v22 M5 editing workflow"
git push
```

## Validation

Packaged backend suite: **85 passed**. Python source compiles. The edited TSX parses cleanly; the Windows updater runs the real `npm install` and `npm run build` before starting Clip AI.
