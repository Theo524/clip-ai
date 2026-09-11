from services.reframe import ReframePlan


VALID_LAYOUTS = {"auto", "fill", "focus", "backdrop", "preserve"}
VALID_CAPTION_STYLES = {"auto", "viral", "cinematic", "clean", "meme"}
VALID_FRAME_SIZES = {"compact", "balanced", "immersive"}


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

    sample_count = max(1, plan.sample_count)
    face_ratio = plan.face_samples / sample_count
    multi_face_ratio = plan.multi_face_samples / sample_count
    source_ratio = (plan.source_width / plan.source_height) if plan.source_height else 16 / 9

    # A stable single-person shot can use the full vertical crop confidently.
    if plan.mode == "face" and face_ratio >= 0.40 and multi_face_ratio < 0.20:
        return "fill"

    # Multi-person / film-like shots should preserve more scene context in a large
    # central 4:5-ish window rather than forcing a full 9:16 crop.
    if multi_face_ratio >= 0.12:
        return "focus"

    # Motion-led footage gets the same central content window but may use a soft
    # blurred backdrop to keep the phone canvas visually active.
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

    if layout == "focus":
        return "cinematic"
    if layout == "fill" and plan.mode == "face":
        return "viral"
    if layout == "preserve":
        return "clean"
    if layout == "backdrop" and plan.mode == "motion":
        return "meme"
    return "clean"


def normalize_frame_size(value: str | None) -> str:
    value = (value or "balanced").lower().strip()
    return value if value in VALID_FRAME_SIZES else "balanced"


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
