from services.reframe import ReframePlan


VALID_LAYOUTS = {"auto", "fill", "focus", "backdrop", "preserve"}
VALID_CAPTION_STYLES = {"auto", "viral", "cinematic", "clean", "meme"}
VALID_FRAME_SIZES = {"auto", "compact", "balanced", "immersive"}


def normalize_content_type(value: str | None) -> str:
    value = (value or "auto").lower().strip()
    aliases = {
        "anime-animation": "anime",
        "film": "film-tv",
        "tv": "film-tv",
        "podcast-interview": "podcast",
        "documentary-educational": "documentary",
        "meme": "meme-comedy",
        "comedy": "meme-comedy",
        "gameplay-commentary": "gameplay",
    }
    return aliases.get(value, value)


def _ratios(plan: ReframePlan) -> tuple[float, float, float]:
    sample_count = max(1, plan.sample_count)
    return (
        plan.face_samples / sample_count,
        plan.multi_face_samples / sample_count,
        getattr(plan, "scene_cut_samples", 0) / sample_count,
    )


def burned_subtitle_ratio(plan: ReframePlan) -> float:
    return max(0, getattr(plan, "subtitle_samples", 0)) / max(1, plan.sample_count)


def burned_subtitles_likely(plan: ReframePlan) -> bool:
    samples = max(0, getattr(plan, "subtitle_samples", 0))
    return samples >= 2 and burned_subtitle_ratio(plan) >= 0.24


def choose_layout(requested: str, plan: ReframePlan, content_type: str | None = None) -> str:
    requested = (requested or "auto").lower().strip()
    if requested not in VALID_LAYOUTS:
        requested = "auto"
    if requested != "auto":
        # v22 M4: Preserve is now a real full-composition choice for widescreen too,
        # not just a portrait-only special case.
        return requested

    content = normalize_content_type(content_type)
    if plan.mode == "portrait":
        return "preserve"

    # Anime uses the classic central cinematic window: black canvas, a medium-sized
    # crop in the middle, and captions inside the picture. It intentionally avoids
    # both full-height 9:16 fill and tiny full-composition preserve.
    if content == "anime":
        return "focus"

    face_ratio, multi_face_ratio, cut_ratio = _ratios(plan)
    source_ratio = (plan.source_width / plan.source_height) if plan.source_height else 16 / 9

    if content == "film-tv":
        return "focus"
    if content == "gameplay" and cut_ratio < 0.16:
        return "backdrop"

    # Stable, mostly-single-person footage is exactly what a full 9:16 crop is good at.
    if plan.mode in {"face", "speaker"} and face_ratio >= 0.42 and multi_face_ratio < 0.14 and cut_ratio < 0.10:
        return "fill"

    # Dialogue scenes / films / multi-person shots need context.
    if multi_face_ratio >= 0.10 or cut_ratio >= 0.10:
        return "focus"

    if plan.mode in {"motion", "saliency"}:
        return "backdrop"

    if source_ratio >= 1.20:
        return "focus"

    return "focus"


def choose_caption_style(
    requested: str,
    layout: str,
    plan: ReframePlan,
    content_type: str | None = None,
) -> str:
    requested = (requested or "auto").lower().strip()
    if requested not in VALID_CAPTION_STYLES:
        requested = "auto"

    # Old projects can still contain "meme". M4 deliberately merges Meme and Viral
    # Pop into one clearer Viral presentation without breaking those projects.
    if requested == "meme":
        return "viral"
    if requested != "auto":
        return requested

    content = normalize_content_type(content_type)
    if content in {"anime", "film-tv"}:
        return "cinematic"
    if content == "meme-comedy":
        return "viral"
    if content == "documentary":
        return "clean"

    if layout == "fill" and plan.mode in {"face", "speaker"}:
        return "viral"
    if layout == "backdrop" and plan.mode in {"motion", "saliency"}:
        return "viral" if content == "gameplay" else "clean"
    if layout == "preserve":
        return "cinematic" if content in {"anime", "film-tv"} else "clean"
    if layout == "focus":
        return "cinematic"
    return "clean"


def choose_frame_size(
    requested: str | None,
    layout: str,
    plan: ReframePlan,
    content_type: str | None = None,
) -> str:
    value = (requested or "auto").lower().strip()
    if value not in VALID_FRAME_SIZES:
        value = "auto"
    if value != "auto":
        return value

    if layout not in {"focus", "backdrop"}:
        return "balanced"

    content = normalize_content_type(content_type)
    if content == "anime":
        # 800 px on a 1280 px canvas = 62.5% of the vertical screen (3.75/6),
        # matching the familiar central anime framing rather than an oversized crop.
        return "compact"
    if content == "film-tv":
        return "compact"

    _face_ratio, multi_face_ratio, cut_ratio = _ratios(plan)
    if multi_face_ratio >= 0.16 or cut_ratio >= 0.14:
        return "compact"
    return "balanced"


def auto_profile(
    layout: str,
    caption_style: str,
    plan: ReframePlan,
    content_type: str | None = None,
) -> str:
    content = normalize_content_type(content_type)
    if content == "anime" and caption_style == "cinematic":
        return "Anime · cinematic"
    if content == "film-tv" and caption_style == "cinematic":
        return "Film / TV · cinematic"
    if layout == "preserve":
        return "Full composition"
    if plan.mode == "speaker" and plan.active_speaker_samples > 0:
        if plan.active_speaker_switches > 0:
            return "Active-speaker dialogue"
        return "Speaker-aware dialogue"
    if layout == "fill" and plan.mode == "face":
        return "Talking head"
    if layout == "focus" and (plan.multi_face_samples > 0 or getattr(plan, "scene_cut_samples", 0) > 0):
        return "Cinematic / group scene"
    if layout == "backdrop" and plan.mode in {"motion", "saliency"}:
        return "Visual / gameplay"
    if caption_style == "cinematic":
        return "Wide dialogue scene"
    return "Wide / contextual footage"


def normalize_frame_size(value: str | None) -> str:
    value = (value or "balanced").lower().strip()
    return value if value in {"compact", "balanced", "immersive"} else "balanced"


def content_window(frame_size: str, width: int = 720, height: int = 1280) -> tuple[int, int, int, int]:
    """Return x, y, width, height for the central video window."""
    size = normalize_frame_size(frame_size)
    # Keep the same visual proportions at preview resolutions as at 720x1280.
    height_ratios = {
        "compact": 800 / 1280,
        "balanced": 900 / 1280,
        "immersive": 1040 / 1280,
    }
    window_h = min(height, round(height * height_ratios[size]))
    window_w = width
    x = (width - window_w) // 2
    y = (height - window_h) // 2
    return x, y, window_w, window_h


def picture_window(
    layout: str,
    frame_size: str,
    source_width: int,
    source_height: int,
    width: int = 720,
    height: int = 1280,
) -> tuple[int, int, int, int]:
    """Return the visible picture bounds inside the final 9:16 canvas.

    This is especially important for M4's widescreen Preserve mode: captions need to
    sit inside the actual anime/film image rather than drifting into black bars.
    """
    layout = (layout or "fill").lower().strip()
    if layout in {"focus", "backdrop"}:
        return content_window(frame_size, width, height)
    if layout != "preserve" or source_width <= 0 or source_height <= 0:
        return (0, 0, width, height)

    scale = min(width / source_width, height / source_height)
    visible_w = max(1, min(width, round(source_width * scale)))
    visible_h = max(1, min(height, round(source_height * scale)))
    x = (width - visible_w) // 2
    y = (height - visible_h) // 2
    return x, y, visible_w, visible_h


def choose_caption_zone(
    style: str,
    layout: str,
    plan: ReframePlan,
    content_type: str | None = None,
) -> str:
    """Choose an in-picture caption band while trying not to cover faces/subtitles."""
    style = (style or "clean").lower().strip()
    layout = (layout or "fill").lower().strip()
    content = normalize_content_type(content_type)

    if style == "cinematic":
        preferences = ["lower", "middle", "upper"]
    elif style == "viral":
        preferences = ["middle", "lower", "upper"]
    else:
        preferences = ["lower", "middle", "upper"]

    # Anime Auto is a deliberate exception: cinematic text stays low inside the
    # central picture. Do not let face-band scoring or subtitle heuristics float it
    # into the middle of the screen; users can still choose another style manually.
    if content == "anime" and style == "cinematic" and layout == "focus":
        return "lower"

    # Existing lower subtitles are stronger evidence than our preferred aesthetic.
    # Move Clip AI's captions away instead of stacking two subtitle tracks.
    if burned_subtitles_likely(plan):
        preferences = ["middle", "upper", "lower"]

    counts = {
        "upper": max(0, plan.face_upper_samples),
        "middle": max(0, plan.face_middle_samples),
        "lower": max(0, plan.face_lower_samples),
    }

    total_face_bands = sum(counts.values())
    if total_face_bands == 0:
        return preferences[0]

    # Anime should remain low/clean unless existing subtitles or faces make that unsafe.
    preference_step = 0.24 if content == "anime" and not burned_subtitles_likely(plan) else 0.18
    preference_penalty = {zone: index * preference_step for index, zone in enumerate(preferences)}
    scores = {
        zone: (counts[zone] / total_face_bands) + preference_penalty.get(zone, 0.5)
        for zone in counts
    }
    return min(preferences, key=lambda zone: scores[zone])
