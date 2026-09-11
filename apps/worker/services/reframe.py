from __future__ import annotations

from dataclasses import asdict, dataclass
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
        )


def save_reframe_plan(plan: ReframePlan, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(plan.to_dict(), indent=2), encoding="utf-8")


def load_reframe_plan(path: str | Path) -> ReframePlan:
    return ReframePlan.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def plan_smart_reframe(
    media_path: str,
    start: float,
    end: float,
    *,
    target_width: int = 720,
    target_height: int = 1280,
    speech_intervals: list[tuple[float, float]] | None = None,
) -> ReframePlan:
    """Create a low-cost horizontal framing track.

    v18 adds conservative active-speaker tracking for multi-person scenes. It uses
    transcript speech timing plus relative lower-face motion as a lightweight proxy
    for who is talking. If confidence is weak, it frames the group instead of making
    a risky switch. Sampling is capped for an 8 GB development machine.
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

    target_ratio = target_width / target_height
    source_ratio = source_width / source_height

    # If the source is already roughly 9:16 (or narrower), preserve the whole frame
    # instead of trying to chase a subject and cropping vertically.
    if source_ratio <= target_ratio * 1.05:
        capture.release()
        return ReframePlan("portrait", [(0.0, 0.5)], source_width, source_height)

    duration = max(0.01, end - start)
    # Speaker inference benefits from slightly denser samples than the older face-only
    # tracker. Cap around 120 samples so CPU/RAM use remains reasonable locally.
    sample_interval = max(0.45, duration / 120.0)
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
    prev_gray = None
    smoothed_center = 0.5
    previous_face_center: float | None = None
    samples_since_face = 999
    face_samples = 0
    motion_samples = 0
    multi_face_samples = 0
    scene_cut_samples = 0
    face_upper_samples = 0
    face_middle_samples = 0
    face_lower_samples = 0
    active_speaker_samples = 0
    active_speaker_switches = 0
    group_fallback_samples = 0
    speaker_hold_samples = 0
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
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)

        raw_center: float | None = None
        source_kind = "center"

        faces = ()
        if not face_detector.empty():
            faces = face_detector.detectMultiScale(
                gray,
                scaleFactor=1.15,
                minNeighbors=4,
                minSize=(28, 28),
            )

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

            # Keep a lightweight vertical occupancy summary. Caption rendering can use
            # this later to avoid sitting directly over the dominant face region.
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

                # Only infer an active speaker while Whisper says speech is happening.
                # Relative lower-face motion is compared with upper-face motion so a
                # simple head turn is less likely to be mistaken for speech.
                source_time = start + local_t
                speech_now = _speech_active(source_time, speech_intervals)
                activity = []
                if speech_now and prev_gray is not None and prev_gray.shape == gray.shape:
                    for item in important:
                        x, y, fw, fh, center, _cy, area = item
                        score = _relative_mouth_activity(gray, prev_gray, x, y, fw, fh)
                        activity.append((score, center, area))

                chosen_center: float | None = None
                if activity:
                    activity.sort(key=lambda item: item[0], reverse=True)
                    top_score, top_center, _top_area = activity[0]
                    second_score = activity[1][0] if len(activity) > 1 else 0.0
                    # Conservative threshold + margin. Uncertain frames stay on the group.
                    confident = top_score >= 0.010 and top_score >= second_score + 0.0035
                    if confident:
                        active_visible_now = (
                            active_face_center is not None
                            and any(abs(item[4] - active_face_center) <= 0.18 for item in important)
                        )
                        if active_face_center is None:
                            active_face_center = top_center
                            pending_face_center = None
                            pending_face_count = 0
                            chosen_center = active_face_center
                        elif not active_visible_now:
                            # The previous speaker disappeared (shot change / camera cut).
                            # Move to the clear new candidate immediately instead of
                            # spending a sample framed on an empty part of the shot.
                            active_face_center = top_center
                            active_speaker_switches += 1
                            pending_face_center = None
                            pending_face_count = 0
                            chosen_center = active_face_center
                        elif abs(top_center - active_face_center) <= 0.17:
                            active_face_center = active_face_center * 0.68 + top_center * 0.32
                            pending_face_center = None
                            pending_face_count = 0
                            chosen_center = active_face_center
                        else:
                            if pending_face_center is not None and abs(top_center - pending_face_center) <= 0.12:
                                pending_face_count += 1
                                pending_face_center = pending_face_center * 0.5 + top_center * 0.5
                            else:
                                pending_face_center = top_center
                                pending_face_count = 1
                            # Two consecutive samples are required before a hard speaker switch.
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
                    # Briefly hold the prior speaker during uncertain samples, but do not
                    # chase them forever. This avoids twitchy back-and-forth framing.
                    visible_active = (
                        active_face_center is not None
                        and any(abs(item[4] - active_face_center) <= 0.18 for item in important)
                    )
                    if speech_now and visible_active and samples_since_active <= 2:
                        raw_center = active_face_center
                        speaker_hold_samples += 1
                        source_kind = "speaker_hold"
                    else:
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
            # Avoid the crop jumping away just because Haar misses the face for a frame or two.
            if previous_face_center is not None and samples_since_face <= 2:
                raw_center = previous_face_center
                source_kind = "face_hold"
            elif prev_gray is not None and prev_gray.shape == gray.shape:
                diff = cv2.absdiff(gray, prev_gray)
                diff = cv2.GaussianBlur(diff, (9, 9), 0)
                _, mask = cv2.threshold(diff, 24, 255, cv2.THRESH_BINARY)
                kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
                mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
                changed_fraction = float(cv2.countNonZero(mask)) / float(mask.size)

                # Tiny changes are usually codec noise. Very large full-frame changes
                # are useful evidence of an edit/scene cut, which makes Auto preserve
                # more composition instead of treating everything as gameplay motion.
                if changed_fraction > 0.72:
                    scene_cut_samples += 1
                elif 0.004 <= changed_fraction <= 0.72:
                    moments = cv2.moments(mask, binaryImage=True)
                    if moments["m00"] > 0:
                        raw_center = (moments["m10"] / moments["m00"]) / mask.shape[1]
                        motion_samples += 1
                        source_kind = "motion"

        if raw_center is None or not math.isfinite(raw_center):
            raw_center = 0.5
            source_kind = "center"

        # Keep the crop from hugging the extreme edge and smooth hard jumps.
        raw_center = min(0.90, max(0.10, raw_center))
        delta = raw_center - smoothed_center
        max_step = 0.095 if source_kind.startswith("speaker") else (0.11 if source_kind.startswith("face") else 0.08)
        delta = min(max_step, max(-max_step, delta))
        alpha = 0.56 if source_kind.startswith("speaker") else (0.62 if source_kind.startswith("face") else 0.42)
        smoothed_center += delta * alpha
        smoothed_center = min(0.90, max(0.10, smoothed_center))
        keyframes.append((local_t, smoothed_center))
        prev_gray = gray

    capture.release()

    if not keyframes:
        return ReframePlan("center", [(0.0, 0.5)], source_width, source_height)

    # Guarantee an anchor at the beginning and the end for smooth interpolation.
    if keyframes[0][0] > 0.01:
        keyframes.insert(0, (0.0, keyframes[0][1]))
    if keyframes[-1][0] < duration:
        keyframes.append((duration, keyframes[-1][1]))

    # v19.1: treat detected subject motion as a *target*, not a command to move the
    # camera every sample. A generous dead zone keeps the crop locked while a face
    # naturally shifts, nods, or the detector wobbles. Only sustained/large movement
    # causes a correction, and the correction moves just enough to restore headroom.
    keyframes = _stabilize_camera_track(keyframes)

    meaningful_speaker = active_speaker_samples >= max(2, math.ceil(successful_samples * 0.06))
    meaningful_face = face_samples >= max(2, math.ceil(successful_samples * 0.12))
    meaningful_motion = motion_samples >= max(2, math.ceil(successful_samples * 0.12))
    if meaningful_speaker:
        mode = "speaker"
    elif meaningful_face:
        mode = "face"
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
