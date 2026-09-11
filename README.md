# Clip AI v16

Local-first short-form video clipping prototype.

## What v16 changes

- Smarter caption phrase grouping using punctuation, pauses, phrase duration and style-specific limits.
- Filters only very low-confidence filler/noise tokens instead of blindly showing every Whisper token.
- Rebalances tiny/dangling caption fragments so captions read more like natural English.
- Keeps word-level Viral/Meme highlighting without the ghost-text layer.
- Adds platform-aware caption safe-zones for YouTube Shorts, TikTok and Instagram Reels.
- Extracts a suggested vertical cover frame after every Short render.
- Keeps the existing adaptive framing, projects/history, smart titles and ready-to-post export flow.

## Run locally

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

## Caption quality on an 8 GB PC

The project still defaults to `tiny.en` because it is the safest low-memory Whisper model. If your machine has enough free RAM, changing this in `apps/worker/.env` can improve transcription quality:

```env
LOCAL_WHISPER_MODEL=base.en
```

If `base.en` causes memory errors, switch back to `tiny.en`. The caption phrase improvements in v16 work with either model.

## Notes

- Final Shorts render locally at 720×1280 to keep development practical on modest hardware.
- Platform presets currently adjust caption safe-zones; they do not change the 9:16 export resolution.
- YouTube projects keep the authorised-source-file workflow rather than depending on an unofficial downloader.
