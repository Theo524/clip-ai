# Clip AI — Milestone 11

Milestone 11 focuses on clarity and caption polish rather than adding more controls.

## What changed

- The two source tabs remain: **Your video** and **YouTube link**.
- Post-analysis rendering is now beginner-first: press **Create Short** and Auto handles the normal choices.
- Framing, video size, caption style, and timing are hidden in an optional **Customize** panel.
- Added a plain-English **60-second guide** explaining 9:16 output, Fill, Focus, Backdrop, Preserve, Compact/Balanced/Immersive, and all caption styles.
- Clip cards are easier to scan: the transcript/hook preview is compact and selection reasons are collapsed.
- Viral Pop and Meme captions no longer use a base text layer plus a moving highlight layer. The active word is styled in a single visible phrase layer, fixing the doubled/ghost text that could show beneath a larger word.
- Existing word-level timing, smart caption-safe placement, adaptive framing, and Milestone 10 moment selection remain intact.

## YouTube tab

The YouTube tab stays in the product because it is part of the intended workflow. The current starter still treats it as a demo path; production link ingestion should use an authorised/owned-content import flow rather than depending on brittle arbitrary-video downloading.

## Local development

Backend:

```bat
cd apps\worker
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Frontend:

```bat
cd apps\web
npm run dev
```

Open `http://localhost:3000`.
