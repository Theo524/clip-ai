from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import math
from pathlib import Path


@dataclass
class ReframePlan:
    mode: str
    keyframes: list[tuple[float, float]]
    source_width: int
    source_height: int
    sample_count: int = 0
    face_samples: int = 0
    motion_samples: int = 0
    multi_face_samples: int = 0
    scene_cut_samples: int = 0
    face_upper_samples: int = 0
    face_middle_samples: int = 0
    face_lower_samples: int = 0
    active_speaker_samples: int = 0
    active_speaker_switches: int = 0
    group_fallback_samples: int = 0
    speaker_hold_samples: int = 0
    saliency_samples: int = 0
    subtitle_samples: int = 0
    subtitle_lower_samples: int = 0
    scene_cut_times: list[float] = field(default_factory=list)
    visual_profile: str = "standard"

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["keyframes"] = [[round(t, 3), round(x, 5)] for t, x in self.keyframes]
        return payload

    @classmethod
    def from_dict(cls, payload: dict) -> "ReframePlan":
        return cls(
            mode=str(payload.get("mode", "center")),
            keyframes=[(float(item[0]), float(item[1])) for item in payload.get("keyframes", [])],
            source_width=int(payload.get("source_width", 0)),
            source_height=int(payload.get("source_height", 0)),
            sample_count=int(payload.get("sample_count", 0)),
            face_samples=int(payload.get("face_samples", 0)),
            motion_samples=int(payload.get("motion_samples", 0)),
            multi_face_samples=int(payload.get("multi_face_samples", 0)),
            scene_cut_samples=int(payload.get("scene_cut_samples", 0)),
            face_upper_samples=int(payload.get("face_upper_samples", 0)),
            face_middle_samples=int(payload.get("face_middle_samples", 0)),
            face_lower_samples=int(payload.get("face_lower_samples", 0)),
            active_speaker_samples=int(payload.get("active_speaker_samples", 0)),
            active_speaker_switches=int(payload.get("active_speaker_switches", 0)),
            group_fallback_samples=int(payload.get("group_fallback_samples", 0)),
            speaker_hold_samples=int(payload.get("speaker_hold_samples", 0)),
            saliency_samples=int(payload.get("saliency_samples", 0)),
            subtitle_samples=int(payload.get("subtitle_samples", 0)),
            subtitle_lower_samples=int(payload.get("subtitle_lower_samples", 0)),
            scene_cut_times=[float(value) for value in payload.get("scene_cut_times", [])],
            visual_profile=str(payload.get("visual_profile", "standard")),
        )


def save_reframe_plan(plan: ReframePlan, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(plan.to_dict(), indent=2), encoding="utf-8")


def load_reframe_plan(path: str | Path) -> ReframePlan:
    return ReframePlan.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def _normalize_visual_content(value: str | None) -> str:
    value = (value or "auto").lower().strip()
    aliases = {
        "anime-animation": "anime",
        "film": "film-tv",
        "tv": "film-tv",
        "documentary-educational": "documentary",
        "gameplay-commentary": "gameplay",
    }
    return aliases.get(value, value)


def _saliency_center(gray) -> tuple[float, float]:
    """Return a cheap visual-interest centre and confidence from a low-res gray frame.

    This deliberately avoids a heavyweight ML detector. Gradient energy finds visually
    busy/important regions while a gentle centre prior prevents the virtual camera from
    chasing every bright edge in animation or gameplay.
    """
    import cv2
    import numpy as np

    if gray is None or getattr(gray, "size", 0) == 0:
        return 0.5, 0.0
    gx = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)
    energy = cv2.magnitude(gx, gy)
    h, w = energy.shape[:2]
    if h <= 1 or w <= 1:
        return 0.5, 0.0

    # Ignore the lowest strip where burned-in subtitles / app watermarks often live.
    usable_h = max(1, int(h * 0.84))
    energy = energy[:usable_h, :]
    x = np.linspace(0.0, 1.0, w, dtype=np.float32)
    center_prior = 0.72 + 0.28 * (1.0 - np.minimum(1.0, np.abs(x - 0.5) / 0.5))
    column_energy = energy.sum(axis=0) * center_prior
    total = float(column_energy.sum())
    if total <= 1e-5:
        return 0.5, 0.0
    center = float((column_energy * x).sum() / total)
    mean_energy = float(energy.mean()) / 255.0
    confidence = min(1.0, mean_energy * 2.2)
    return min(0.9, max(0.1, center)), confidence


def _burned_subtitle_likelihood(gray) -> float:
    """Conservative no-OCR heuristic for persistent subtitle-like lower text.

    We look for several small high-contrast components spread horizontally through the
    lower picture band. A single detailed frame can still fool this, so callers require
    the signal on multiple sampled frames before moving Clip AI captions.
    """
    import cv2

    if gray is None or getattr(gray, "size", 0) == 0:
        return 0.0
    h, w = gray.shape[:2]
    if h < 40 or w < 80:
        return 0.0
    y0 = int(h * 0.60)
    y1 = max(y0 + 1, int(h * 0.94))
    band = gray[y0:y1, :]
    # Bright glyph interiors plus Canny edges catches common white/yellow outlined subs.
    _, bright = cv2.threshold(band, 178, 255, cv2.THRESH_BINARY)
    edges = cv2.Canny(band, 70, 150)
    mask = cv2.bitwise_and(bright, cv2.dilate(edges, cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 2)))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    boxes = []
    band_h = band.shape[0]
    for contour in contours:
        x, y, cw, ch = cv2.boundingRect(contour)
        area = cw * ch
        if area < 7 or ch < 3 or ch > max(34, int(band_h * 0.42)):
            continue
        if cw < 2 or cw > int(w * 0.22):
            continue
        boxes.append((x, y, cw, ch))

    if len(boxes) < 4:
        return min(0.35, len(boxes) / 12.0)
    left = min(x for x, _y, _cw, _ch in boxes)
    right = max(x + cw for x, _y, cw, _ch in boxes)
    span = (right - left) / max(1.0, float(w))
    count_score = min(1.0, len(boxes) / 12.0)
    span_score = min(1.0, span / 0.48)
    return min(1.0, count_score * 0.58 + span_score * 0.42)


def _stabilize_track_by_scenes(
    points: list[tuple[float, float]],
    scene_cut_times: list[float],
    **kwargs,
) -> list[tuple[float, float]]:
    """Stabilize each shot independently so a new shot never inherits the old crop."""
    if not points or not scene_cut_times:
        return _stabilize_camera_track(points, **kwargs)
    ordered = sorted(points, key=lambda item: item[0])
    cuts = sorted(cut for cut in scene_cut_times if ordered[0][0] < cut < ordered[-1][0])
    if not cuts:
        return _stabilize_camera_track(ordered, **kwargs)

    result: list[tuple[float, float]] = []
    segment_start = 0
    for cut in [*cuts, float("inf")]:
        segment = []
        while segment_start < len(ordered) and ordered[segment_start][0] < cut:
            segment.append(ordered[segment_start])
            segment_start += 1
        if segment:
            stabilized = _stabilize_camera_track(segment, **kwargs)
            if result and stabilized and stabilized[0][0] <= result[-1][0]:
                stabilized = stabilized[1:]
            result.extend(stabilized)
    return result or _stabilize_camera_track(ordered, **kwargs)


def plan_smart_reframe(
    media_path: str,
    start: float,
    end: float,
    *,
    target_width: int = 720,
    target_height: int = 1280,
    speech_intervals: list[tuple[float, float]] | None = None,
    content_type: str | None = None,
) -> ReframePlan:
    """Create a low-cost, content-aware horizontal framing track.

    M4 makes the camera calmer, resets tracking on shot cuts, and adds a saliency
    fallback for anime/gameplay/documentary footage. All analysis runs only on the
    chosen clip range and on a <=480px proxy, keeping the local workflow lightweight.
    """
    try:
        import cv2
    except Exception:
        return ReframePlan("center", [(0.0, 0.5)], 0, 0)

    capture = cv2.VideoCapture(media_path)
    if not capture.isOpened():
        return ReframePlan("center", [(0.0, 0.5)], 0, 0)

    source_width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    source_height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    if source_width <= 0 or source_height <= 0:
        capture.release()
        return ReframePlan("center", [(0.0, 0.5)], 0, 0)

    content = _normalize_visual_content(content_type)
    visual_profile = "cinematic" if content in {"anime", "film-tv"} else ("visual" if content in {"gameplay", "documentary"} else "standard")

    target_ratio = target_width / target_height
    source_ratio = source_width / source_height
    if source_ratio <= target_ratio * 1.05:
        capture.release()
        return ReframePlan("portrait", [(0.0, 0.5)], source_width, source_height, visual_profile=visual_profile)

    duration = max(0.01, end - start)
    sample_cap = 72 if visual_profile == "cinematic" else (90 if visual_profile == "visual" else 120)
    min_interval = 0.72 if visual_profile == "cinematic" else (0.58 if visual_profile == "visual" else 0.45)
    sample_interval = max(min_interval, duration / float(sample_cap))
    sample_times: list[float] = []
    t = 0.0
    while t < duration:
        sample_times.append(t)
        t += sample_interval
    if not sample_times or sample_times[-1] < duration - 0.2:
        sample_times.append(max(0.0, duration - 0.05))

    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    face_detector = cv2.CascadeClassifier(cascade_path)

    keyframes: list[tuple[float, float]] = []
    scene_cut_times: list[float] = []
    prev_gray = None
    prev_scene_gray = None
    smoothed_center = 0.5
    previous_face_center: float | None = None
    samples_since_face = 999
    face_samples = motion_samples = multi_face_samples = scene_cut_samples = 0
    face_upper_samples = face_middle_samples = face_lower_samples = 0
    active_speaker_samples = active_speaker_switches = 0
    group_fallback_samples = speaker_hold_samples = 0
    saliency_samples = subtitle_samples = subtitle_lower_samples = 0
    active_face_center: float | None = None
    pending_face_center: float | None = None
    pending_face_count = 0
    samples_since_active = 999
    successful_samples = 0

    for local_t in sample_times:
        capture.set(cv2.CAP_PROP_POS_MSEC, (start + local_t) * 1000.0)
        ok, frame = capture.read()
        if not ok or frame is None:
            continue

        successful_samples += 1
        h, w = frame.shape[:2]
        resize_width = min(480, w)
        scale = resize_width / w
        resized = cv2.resize(frame, (resize_width, max(2, int(h * scale))))
        raw_gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(raw_gray)

        saliency_center, saliency_conf = _saliency_center(gray)
        if saliency_conf >= 0.035:
            saliency_samples += 1

        subtitle_score = _burned_subtitle_likelihood(gray)
        if subtitle_score >= 0.54:
            subtitle_samples += 1
            subtitle_lower_samples += 1

        changed_fraction = 0.0
        motion_mask = None
        cut_detected = False
        if prev_scene_gray is not None and prev_scene_gray.shape == raw_gray.shape:
            diff = cv2.absdiff(raw_gray, prev_scene_gray)
            mean_change = float(diff.mean()) / 255.0
            diff_blur = cv2.GaussianBlur(diff, (9, 9), 0)
            _, motion_mask = cv2.threshold(diff_blur, 24, 255, cv2.THRESH_BINARY)
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
            motion_mask = cv2.morphologyEx(motion_mask, cv2.MORPH_OPEN, kernel)
            changed_fraction = float(cv2.countNonZero(motion_mask)) / float(motion_mask.size)
            cut_detected = changed_fraction > 0.64 and mean_change > 0.10

        if cut_detected:
            scene_cut_samples += 1
            scene_cut_times.append(local_t)
            if keyframes:
                keyframes.append((max(keyframes[-1][0], local_t - 0.012), smoothed_center))
            # New shot = new framing decision. Do not inherit a face/speaker target.
            smoothed_center = 0.5
            previous_face_center = None
            active_face_center = None
            pending_face_center = None
            pending_face_count = 0
            samples_since_face = 999
            samples_since_active = 999

        raw_center: float | None = None
        source_kind = "center"
        faces = ()
        if not face_detector.empty():
            faces = face_detector.detectMultiScale(gray, scaleFactor=1.15, minNeighbors=4, minSize=(28, 28))

        if len(faces):
            face_samples += 1
            face_data = []
            for x, y, fw, fh in faces:
                center = (x + fw / 2.0) / resized.shape[1]
                center_y = (y + fh / 2.0) / resized.shape[0]
                area = float(fw * fh)
                face_data.append((x, y, fw, fh, center, center_y, area))

            largest_area = max(item[6] for item in face_data)
            important = [item for item in face_data if item[6] >= largest_area * 0.35]
            weighted_y = sum(item[5] * item[6] for item in important) / max(1.0, sum(item[6] for item in important))
            if weighted_y < 0.38:
                face_upper_samples += 1
            elif weighted_y < 0.68:
                face_middle_samples += 1
            else:
                face_lower_samples += 1

            if len(important) >= 2:
                multi_face_samples += 1
                left = min(item[0] for item in important)
                right = max(item[0] + item[2] for item in important)
                group_center = ((left + right) / 2.0) / resized.shape[1]
                source_time = start + local_t
                speech_now = _speech_active(source_time, speech_intervals)
                activity = []
                # Active-speaker chasing is intentionally disabled for cinematic media.
                if visual_profile == "standard" and speech_now and prev_gray is not None and prev_gray.shape == gray.shape and not cut_detected:
                    for item in important:
                        x, y, fw, fh, center, _cy, area = item
                        activity.append((_relative_mouth_activity(gray, prev_gray, x, y, fw, fh), center, area))

                chosen_center: float | None = None
                if activity:
                    activity.sort(key=lambda item: item[0], reverse=True)
                    top_score, top_center, _top_area = activity[0]
                    second_score = activity[1][0] if len(activity) > 1 else 0.0
                    confident = top_score >= 0.010 and top_score >= second_score + 0.0035
                    if confident:
                        active_visible_now = active_face_center is not None and any(abs(item[4] - active_face_center) <= 0.18 for item in important)
                        if active_face_center is None or not active_visible_now:
                            if active_face_center is not None:
                                active_speaker_switches += 1
                            active_face_center = top_center
                            pending_face_center = None
                            pending_face_count = 0
                        elif abs(top_center - active_face_center) <= 0.17:
                            active_face_center = active_face_center * 0.72 + top_center * 0.28
                            pending_face_center = None
                            pending_face_count = 0
                        else:
                            if pending_face_center is not None and abs(top_center - pending_face_center) <= 0.12:
                                pending_face_count += 1
                                pending_face_center = pending_face_center * 0.5 + top_center * 0.5
                            else:
                                pending_face_center = top_center
                                pending_face_count = 1
                            if pending_face_count >= 2:
                                active_face_center = pending_face_center
                                active_speaker_switches += 1
                                pending_face_center = None
                                pending_face_count = 0
                        chosen_center = active_face_center

                if chosen_center is not None:
                    raw_center = chosen_center
                    active_speaker_samples += 1
                    samples_since_active = 0
                    source_kind = "speaker"
                else:
                    samples_since_active += 1
                    if visual_profile == "standard" and speech_now and active_face_center is not None and samples_since_active <= 2:
                        visible_active = any(abs(item[4] - active_face_center) <= 0.18 for item in important)
                        if visible_active:
                            raw_center = active_face_center
                            speaker_hold_samples += 1
                            source_kind = "speaker_hold"
                    if raw_center is None:
                        raw_center = group_center
                        group_fallback_samples += 1
                        source_kind = "face_group"
            else:
                candidates = []
                for _x, _y, _fw, _fh, center, _center_y, area in face_data:
                    proximity = 1.0 if previous_face_center is None else max(0.15, 1.0 - abs(center - previous_face_center))
                    candidates.append((area * proximity, center))
                _score, raw_center = max(candidates, key=lambda item: item[0])
                source_kind = "face"
                active_face_center = raw_center
                samples_since_active = 0

            previous_face_center = raw_center
            samples_since_face = 0
        else:
            samples_since_face += 1
            if previous_face_center is not None and samples_since_face <= (1 if visual_profile == "cinematic" else 2) and not cut_detected:
                raw_center = previous_face_center
                source_kind = "face_hold"
            elif not cut_detected and motion_mask is not None and 0.004 <= changed_fraction <= 0.64:
                moments = cv2.moments(motion_mask, binaryImage=True)
                if moments["m00"] > 0:
                    raw_center = (moments["m10"] / moments["m00"]) / motion_mask.shape[1]
                    motion_samples += 1
                    source_kind = "motion"

        # For visual media, use saliency as a stable fallback and damp face chasing.
        if visual_profile == "cinematic":
            visual_target = saliency_center if saliency_conf >= 0.035 else 0.5
            if raw_center is None:
                raw_center = visual_target
                source_kind = "saliency"
            else:
                raw_center = 0.52 * 0.5 + 0.28 * raw_center + 0.20 * visual_target
                source_kind = "saliency"
        elif visual_profile == "visual" and (raw_center is None or source_kind == "motion") and saliency_conf >= 0.035:
            if raw_center is None:
                raw_center = saliency_center
            else:
                raw_center = raw_center * 0.45 + saliency_center * 0.55
            source_kind = "saliency"

        if raw_center is None or not math.isfinite(raw_center):
            raw_center = 0.5
            source_kind = "center"

        raw_center = min(0.90, max(0.10, raw_center))
        if cut_detected and visual_profile == "cinematic":
            # Start a new anime/film shot centered; only sustained evidence may move it.
            raw_center = 0.5

        delta = raw_center - smoothed_center
        if visual_profile == "cinematic":
            max_step = 0.050
            alpha = 0.30
        elif visual_profile == "visual":
            max_step = 0.070
            alpha = 0.38
        else:
            max_step = 0.095 if source_kind.startswith("speaker") else (0.11 if source_kind.startswith("face") else 0.08)
            alpha = 0.56 if source_kind.startswith("speaker") else (0.62 if source_kind.startswith("face") else 0.42)
        delta = min(max_step, max(-max_step, delta))
        smoothed_center += delta * alpha
        smoothed_center = min(0.90, max(0.10, smoothed_center))
        keyframes.append((local_t, smoothed_center))
        prev_gray = gray
        prev_scene_gray = raw_gray

    capture.release()
    if not keyframes:
        return ReframePlan("center", [(0.0, 0.5)], source_width, source_height, visual_profile=visual_profile)

    if keyframes[0][0] > 0.01:
        keyframes.insert(0, (0.0, keyframes[0][1]))
    if keyframes[-1][0] < duration:
        keyframes.append((duration, keyframes[-1][1]))

    stabilize_kwargs = {}
    if visual_profile == "cinematic":
        stabilize_kwargs = dict(dead_zone=0.11, settle_zone=0.075, trigger_samples=3, immediate_distance=0.22, min_move=0.022, max_speed_per_second=0.09)
    elif visual_profile == "visual":
        stabilize_kwargs = dict(dead_zone=0.09, settle_zone=0.06, trigger_samples=2, immediate_distance=0.19, min_move=0.020, max_speed_per_second=0.12)
    keyframes = _stabilize_track_by_scenes(keyframes, scene_cut_times, **stabilize_kwargs)

    meaningful_speaker = active_speaker_samples >= max(2, math.ceil(successful_samples * 0.06))
    meaningful_face = face_samples >= max(2, math.ceil(successful_samples * 0.12))
    meaningful_motion = motion_samples >= max(2, math.ceil(successful_samples * 0.12))
    meaningful_saliency = saliency_samples >= max(2, math.ceil(successful_samples * 0.18))
    if visual_profile == "cinematic" and meaningful_saliency:
        mode = "saliency"
    elif meaningful_speaker:
        mode = "speaker"
    elif meaningful_face:
        mode = "face"
    elif meaningful_saliency and visual_profile == "visual":
        mode = "saliency"
    elif meaningful_motion:
        mode = "motion"
    else:
        mode = "center"
        keyframes = [(0.0, 0.5), (duration, 0.5)]

    return ReframePlan(
        mode=mode,
        keyframes=keyframes,
        source_width=source_width,
        source_height=source_height,
        sample_count=successful_samples,
        face_samples=face_samples,
        motion_samples=motion_samples,
        multi_face_samples=multi_face_samples,
        scene_cut_samples=scene_cut_samples,
        face_upper_samples=face_upper_samples,
        face_middle_samples=face_middle_samples,
        face_lower_samples=face_lower_samples,
        active_speaker_samples=active_speaker_samples,
        active_speaker_switches=active_speaker_switches,
        group_fallback_samples=group_fallback_samples,
        speaker_hold_samples=speaker_hold_samples,
        saliency_samples=saliency_samples,
        subtitle_samples=subtitle_samples,
        subtitle_lower_samples=subtitle_lower_samples,
        scene_cut_times=scene_cut_times,
        visual_profile=visual_profile,
    )


def _stabilize_camera_track(
    points: list[tuple[float, float]],
    *,
    dead_zone: float = 0.075,
    settle_zone: float = 0.050,
    trigger_samples: int = 2,
    immediate_distance: float = 0.155,
    min_move: float = 0.018,
    max_speed_per_second: float = 0.16,
) -> list[tuple[float, float]]:
    """Turn a face/speaker target path into a conservative virtual-camera path.

    Face detectors move a few pixels on almost every sample. Following that signal
    literally makes the crop look like a nervous gimbal. This filter keeps the camera
    locked while the target remains within a central comfort zone. A movement must be
    sustained for multiple samples (or be obviously large) before the camera moves.
    The camera then corrects only enough to bring the target back inside a tighter
    settle zone, rather than recentering the face on every frame.
    """
    if not points:
        return []
    ordered = sorted((float(t), float(c)) for t, c in points)
    if len(ordered) == 1:
        return ordered

    camera = min(0.90, max(0.10, ordered[0][1]))
    result: list[tuple[float, float]] = [(ordered[0][0], camera)]
    outside_count = 0

    for index in range(1, len(ordered)):
        t, target = ordered[index]
        target = min(0.90, max(0.10, target))
        previous_t = result[-1][0]
        dt = max(0.001, t - previous_t)
        distance = target - camera
        abs_distance = abs(distance)

        if abs_distance <= dead_zone:
            outside_count = 0
            result.append((t, camera))
            continue

        outside_count += 1
        immediate = abs_distance >= immediate_distance
        if outside_count < max(1, trigger_samples) and not immediate:
            result.append((t, camera))
            continue

        direction = 1.0 if distance > 0 else -1.0
        desired = target - direction * settle_zone
        desired = min(0.90, max(0.10, desired))
        requested = desired - camera

        if abs(requested) < min_move:
            result.append((t, camera))
            continue

        max_step = max_speed_per_second * dt
        step = min(max_step, max(-max_step, requested))
        camera = min(0.90, max(0.10, camera + step))
        result.append((t, camera))

        # If the subject is now comfortably inside the frame, require fresh evidence
        # before another correction. This produces deliberate moves separated by holds.
        if abs(target - camera) <= dead_zone:
            outside_count = 0

    # Remove redundant hold samples so FFmpeg sees long static sections rather than
    # dozens of identical keyframes. Keep endpoints and actual camera movements.
    compact: list[tuple[float, float]] = [result[0]]
    for index in range(1, len(result) - 1):
        prev_center = result[index - 1][1]
        center = result[index][1]
        next_center = result[index + 1][1]
        if abs(center - prev_center) > 0.0005 or abs(next_center - center) > 0.0005:
            compact.append(result[index])
    if result[-1] != compact[-1]:
        compact.append(result[-1])
    return compact

def _speech_active(at_seconds: float, intervals: list[tuple[float, float]] | None) -> bool:
    if not intervals:
        return True
    return any(start - 0.12 <= at_seconds <= end + 0.12 for start, end in intervals)


def _relative_mouth_activity(gray, prev_gray, x: int, y: int, fw: int, fh: int) -> float:
    """Estimate speech-like lower-face motion while discounting head/eye motion."""
    h, w = gray.shape[:2]
    x0 = max(0, min(w - 1, int(x + fw * 0.12)))
    x1 = max(x0 + 1, min(w, int(x + fw * 0.88)))

    upper_y0 = max(0, min(h - 1, int(y + fh * 0.20)))
    upper_y1 = max(upper_y0 + 1, min(h, int(y + fh * 0.50)))
    mouth_y0 = max(0, min(h - 1, int(y + fh * 0.56)))
    mouth_y1 = max(mouth_y0 + 1, min(h, int(y + fh * 0.93)))

    if x1 <= x0 or upper_y1 <= upper_y0 or mouth_y1 <= mouth_y0:
        return 0.0

    import cv2
    upper_diff = cv2.absdiff(gray[upper_y0:upper_y1, x0:x1], prev_gray[upper_y0:upper_y1, x0:x1])
    mouth_diff = cv2.absdiff(gray[mouth_y0:mouth_y1, x0:x1], prev_gray[mouth_y0:mouth_y1, x0:x1])
    upper = float(upper_diff.mean()) / 255.0 if upper_diff.size else 0.0
    mouth = float(mouth_diff.mean()) / 255.0 if mouth_diff.size else 0.0
    return max(0.0, mouth - upper * 0.72)


def build_crop_x_expression(plan: ReframePlan) -> str:
    """Build a piecewise-linear FFmpeg crop x expression from normalized centers.

    FFmpeg's expression parser has a practical nesting limit. v18 can sample up to
    ~120 tracking points, which is enough to overflow that parser on longer clips.
    Compress the path first while preserving its bends/speaker switches, then build
    the nested expression from a safe number of points.
    """
    points = _compress_keyframes(
        sorted(plan.keyframes, key=lambda item: item[0]),
        max_points=72,
    )
    if not points:
        return "(iw-ow)/2"
    if len(points) == 1:
        center = points[0][1]
        return _center_to_x(center)

    # Build nested if(lt(t,next_t), interpolated_x, ...). Quoting in media.py
    # keeps expression commas from being interpreted as filter separators.
    tail = _center_to_x(points[-1][1])
    for index in range(len(points) - 2, -1, -1):
        t0, c0 = points[index]
        t1, c1 = points[index + 1]
        span = max(0.001, t1 - t0)
        center_expr = f"({c0:.6f}+({c1 - c0:.6f})*(t-{t0:.3f})/{span:.3f})"
        x_expr = f"clip({center_expr}*iw-ow/2,0,iw-ow)"
        tail = f"if(lt(t,{t1:.3f}),{x_expr},{tail})"
    return tail


def _compress_keyframes(
    points: list[tuple[float, float]],
    *,
    max_points: int = 72,
) -> list[tuple[float, float]]:
    """Simplify a tracking curve without feeding FFmpeg an enormous expression.

    We use a time-aware Ramer-Douglas-Peucker simplification on the normalized
    horizontal center. That preferentially keeps turns and speaker-switch movement
    rather than blindly dropping every Nth sample. A final even cap is only a safety
    net for extremely jagged tracks.
    """
    if not points:
        return []

    # Drop duplicate/near-duplicate timestamps; they create zero-length spans and
    # add expression depth without adding useful tracking information.
    deduped: list[tuple[float, float]] = []
    for t, center in points:
        t = float(t)
        center = float(center)
        if deduped and abs(t - deduped[-1][0]) < 0.0005:
            deduped[-1] = (t, center)
        else:
            deduped.append((t, center))

    if len(deduped) <= max_points:
        return deduped

    def simplify(tolerance: float) -> list[tuple[float, float]]:
        def recurse(chunk: list[tuple[float, float]]) -> list[tuple[float, float]]:
            if len(chunk) <= 2:
                return chunk
            t0, c0 = chunk[0]
            t1, c1 = chunk[-1]
            span = max(1e-9, t1 - t0)
            best_index = -1
            best_error = -1.0
            for idx in range(1, len(chunk) - 1):
                t, center = chunk[idx]
                ratio = min(1.0, max(0.0, (t - t0) / span))
                expected = c0 + (c1 - c0) * ratio
                error = abs(center - expected)
                if error > best_error:
                    best_error = error
                    best_index = idx
            if best_error <= tolerance or best_index < 0:
                return [chunk[0], chunk[-1]]
            left = recurse(chunk[: best_index + 1])
            right = recurse(chunk[best_index:])
            return left[:-1] + right

        return recurse(deduped)

    # ~0.004 is less than 3 pixels on a 720px output. Increase only as much as
    # necessary to stay below FFmpeg's safe nesting depth.
    tolerance = 0.004
    simplified = simplify(tolerance)
    while len(simplified) > max_points and tolerance < 0.08:
        tolerance *= 1.45
        simplified = simplify(tolerance)

    if len(simplified) <= max_points:
        return simplified

    # Pathological/noisy track: keep endpoints plus evenly spread samples.
    last = len(simplified) - 1
    indices = sorted({round(i * last / (max_points - 1)) for i in range(max_points)})
    return [simplified[i] for i in indices]


def _center_to_x(center: float) -> str:
    return f"clip({center:.6f}*iw-ow/2,0,iw-ow)"
