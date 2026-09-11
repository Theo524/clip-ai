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
) -> ReframePlan:
    """Create a low-cost horizontal framing track.

    Priority is face -> recent face hold -> motion -> center. Sampling is capped so
    this remains practical on an 8 GB development machine.
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
    # ~0.9 s samples for normal Shorts, while capping very long clips around 80 samples.
    sample_interval = max(0.9, duration / 80.0)
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
            for x, _y, fw, fh in faces:
                center = (x + fw / 2.0) / resized.shape[1]
                area = float(fw * fh)
                face_data.append((x, fw, center, area))

            largest_area = max(item[3] for item in face_data)
            important = [item for item in face_data if item[3] >= largest_area * 0.35]
            if len(important) >= 2:
                # Group-aware framing: when two or more similarly important faces are
                # present, frame their combined horizontal region rather than snapping
                # to only the largest face. This is much safer for film/dialogue scenes.
                left = min(item[0] for item in important)
                right = max(item[0] + item[1] for item in important)
                raw_center = ((left + right) / 2.0) / resized.shape[1]
                multi_face_samples += 1
                source_kind = "face_group"
            else:
                candidates = []
                for _x, _fw, center, area in face_data:
                    proximity = 1.0 if previous_face_center is None else max(0.15, 1.0 - abs(center - previous_face_center))
                    candidates.append((area * proximity, center))
                _score, raw_center = max(candidates, key=lambda item: item[0])
                source_kind = "face"

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

                # Tiny changes are usually codec noise; almost-full-frame changes are often a cut.
                if 0.004 <= changed_fraction <= 0.72:
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
        max_step = 0.11 if source_kind.startswith("face") else 0.08
        delta = min(max_step, max(-max_step, delta))
        alpha = 0.62 if source_kind.startswith("face") else 0.42
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

    meaningful_face = face_samples >= max(2, math.ceil(successful_samples * 0.12))
    meaningful_motion = motion_samples >= max(2, math.ceil(successful_samples * 0.12))
    if meaningful_face:
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
    )


def build_crop_x_expression(plan: ReframePlan) -> str:
    """Build a piecewise-linear FFmpeg crop x expression from normalized centers."""
    points = sorted(plan.keyframes, key=lambda item: item[0])
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


def _center_to_x(center: float) -> str:
    return f"clip({center:.6f}*iw-ow/2,0,iw-ow)"
