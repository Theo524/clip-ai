# Architecture notes

## Product boundary

The first valuable unit is **clip selection**, not rendering. If the model consistently chooses strong timestamps, rendering is deterministic engineering layered on top.

## Processing state machine (next iteration)

```text
created
  -> importing
  -> transcribing
  -> ranking
  -> cutting
  -> reframing
  -> captioning
  -> rendering
  -> ready
  -> failed
```

## Core data model

```text
Project
- id
- user_id
- source_url
- source_asset_id
- title
- status

TranscriptSegment
- project_id
- start_ms
- end_ms
- text
- speaker_id (optional)

ClipCandidate
- project_id
- start_ms
- end_ms
- score
- title
- hook
- reasons[]
- status

RenderedClip
- clip_candidate_id
- aspect_ratio
- caption_preset
- crop_strategy
- output_asset_id
```

## Import abstraction

Production should not couple the product to a scraping command. Use a provider interface:

```python
class MediaImporter:
    def can_handle(self, source_url: str) -> bool: ...
    def import_media(self, source_url: str, user_context: dict) -> ImportedAsset: ...
```

Possible implementations:
- authorised creator-platform import
- direct upload
- Google Drive / Dropbox import
- object-storage URL import

The rest of the pipeline only receives a normalized media asset.
