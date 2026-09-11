from services.reframe import ReframePlan


VALID_LAYOUTS = {"auto", "fill", "focus", "backdrop", "preserve"}
VALID_CAPTION_STYLES = {"auto", "viral", "cinematic", "clean", "meme"}
VALID_FRAME_SIZES = {"auto", "compact", "balanced", "immersive"}


def _ratios(plan: ReframePlan) -> tuple[float, float, float]:
    sample_count = max(1, plan.sample_count)
    return (
        plan.face_samples / sample_count,
        plan.multi_face_samples / sample_count,
        getattr(plan, "scene_cut_samples", 0) / sample_count,
    )


def choose_layout(requested: str, plan: ReframePlan) -> str:
    requested = (requested or "auto").lower().strip()
    if requested not in VALID_LAYOUTS:
        requested = "auto"
    if requested != "auto":
        if requested == "preserve" and plan.mode != "portrait":
            return "focus"
        return requested

    if plan.mode == "portrait":
        return "preserve"

    face_ratio, multi_face_ratio, cut_ratio = _ratios(plan)
    source_ratio = (plan.source_width / plan.source_height) if plan.source_height else 16 / 9

    # Stable, mostly-single-person footage is exactly what a full 9:16 crop is good at.
    if plan.mode == "face" and face_ratio >= 0.42 and multi_face_ratio < 0.14 and cut_ratio < 0.10:
        return "fill"

    # Dialogue scenes / films / multi-person shots need context. Focus keeps a large
    # central video window without shrinking all the way to a full 16:9 letterbox.
    if multi_face_ratio >= 0.10 or cut_ratio >= 0.10:
        return "focus"

    # Sustained visual motion (gameplay, demonstrations, screen content) benefits from
    # keeping a little more context and using the spare canvas as a subdued backdrop.
    if plan.mode == "motion":
        return "backdrop"

    if source_ratio >= 1.20:
        return "focus"

    return "focus"


def choose_caption_style(requested: str, layout: str, plan: ReframePlan) -> str:
    requested = (requested or "auto").lower().strip()
    if requested not in VALID_CAPTION_STYLES:
        requested = "auto"
    if requested != "auto":
        return requested

    face_ratio, multi_face_ratio, cut_ratio = _ratios(plan)

    if layout == "fill" and plan.mode == "face":
        return "viral"
    if layout == "backdrop" and plan.mode == "motion":
        return "meme"
    if layout == "preserve":
        return "clean"
    if layout == "focus":
        # Focus exists primarily to preserve wider composition (films, dialogue, wide
        # scenes), so restrained cinematic captions remain the safest automatic style.
        return "cinematic"
    return "clean"


def choose_frame_size(requested: str | None, layout: str, plan: ReframePlan) -> str:
    value = (requested or "auto").lower().strip()
    if value not in VALID_FRAME_SIZES:
        value = "auto"
    if value != "auto":
        return value

    if layout not in {"focus", "backdrop"}:
        return "balanced"

    _face_ratio, multi_face_ratio, cut_ratio = _ratios(plan)
    # Compact preserves more horizontal context, useful for groups and fast scene cuts.
    if multi_face_ratio >= 0.16 or cut_ratio >= 0.14:
        return "compact"
    return "balanced"


def auto_profile(layout: str, caption_style: str, plan: ReframePlan) -> str:
    if layout == "preserve":
        return "Already vertical"
    if layout == "fill" and plan.mode == "face":
        return "Talking head"
    if layout == "focus" and (plan.multi_face_samples > 0 or getattr(plan, "scene_cut_samples", 0) > 0):
        return "Cinematic / group scene"
    if layout == "backdrop" and plan.mode == "motion":
        return "Motion / gameplay"
    if caption_style == "cinematic":
        return "Wide dialogue scene"
    return "Wide / contextual footage"


def normalize_frame_size(value: str | None) -> str:
    value = (value or "balanced").lower().strip()
    return value if value in {"compact", "balanced", "immersive"} else "balanced"


def content_window(frame_size: str, width: int = 720, height: int = 1280) -> tuple[int, int, int, int]:
    """Return x, y, width, height for the central video window.

    Balanced is intentionally 720x900: a 4:5 content window centered inside the
    9:16 output, close to the user's 'middle four of six sections' mental model.
    """
    size = normalize_frame_size(frame_size)
    heights = {
        "compact": 800,
        "balanced": 900,
        "immersive": 1040,
    }
    window_h = min(height, heights[size])
    window_w = width
    x = (width - window_w) // 2
    y = (height - window_h) // 2
    return x, y, window_w, window_h


def choose_caption_zone(style: str, layout: str, plan: ReframePlan) -> str:
    """Choose an in-picture caption band while trying not to cover faces."""
    style = (style or "clean").lower().strip()
    layout = (layout or "fill").lower().strip()

    if style == "cinematic":
        preferences = ["lower", "middle", "upper"]
    elif style in {"viral", "meme"}:
        preferences = ["middle", "lower", "upper"]
    else:
        preferences = ["lower", "middle", "upper"]

    counts = {
        "upper": max(0, plan.face_upper_samples),
        "middle": max(0, plan.face_middle_samples),
        "lower": max(0, plan.face_lower_samples),
    }

    total_face_bands = sum(counts.values())
    if total_face_bands == 0:
        return preferences[0]

    preference_penalty = {zone: index * 0.18 for index, zone in enumerate(preferences)}
    scores = {
        zone: (counts[zone] / total_face_bands) + preference_penalty.get(zone, 0.5)
        for zone in counts
    }
    return min(preferences, key=lambda zone: scores[zone])
