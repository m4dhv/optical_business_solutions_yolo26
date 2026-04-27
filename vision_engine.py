"""
vision_engine.py — YOLO Detection Engine
==========================================
Handles model loading, object tracking, and frame annotation.
Decoupled from any UI framework — returns clean data structures.
cv2 and numpy are lazy-imported so the module loads even without OpenCV.
"""

import streamlit as st
from pathlib import Path
from dataclasses import dataclass, field

# ── Paths ────────────────────────────────────────────────────────────────────
APP_DIR = Path(__file__).resolve().parent

MODEL_MAP = {
    "Nano":   "best_nano.pt",
    "Small":  "best_small.pt",
    "Medium": "best_medium.pt",
}

# ── Detection Result ─────────────────────────────────────────────────────────
@dataclass
class DetectionItem:
    """A single detected object."""
    name: str
    confidence: float
    bbox: tuple  # (x1, y1, x2, y2)
    track_id: int | None = None


@dataclass
class DetectionResult:
    """Aggregated result from one frame of inference."""
    items: list[DetectionItem] = field(default_factory=list)

    @property
    def label_counts(self) -> dict[str, int]:
        """Count of each detected label."""
        counts: dict[str, int] = {}
        for item in self.items:
            counts[item.name] = counts.get(item.name, 0) + 1
        return counts

    @property
    def label_confidences(self) -> dict[str, list[float]]:
        """Confidences grouped by label."""
        confs: dict[str, list[float]] = {}
        for item in self.items:
            confs.setdefault(item.name, []).append(item.confidence)
        return confs

    @property
    def unique_names(self) -> list[str]:
        """List of unique detected item names."""
        return list(self.label_counts.keys())

    @property
    def highest_confidence_per_label(self) -> dict[str, float]:
        """Highest confidence for each label."""
        best: dict[str, float] = {}
        for item in self.items:
            if item.name not in best or item.confidence > best[item.name]:
                best[item.name] = item.confidence
        return best

    def has_items(self) -> bool:
        return len(self.items) > 0


# ── Model Loading ────────────────────────────────────────────────────────────
@st.cache_resource
def load_model(model_key: str = "Medium"):
    """
    Load and cache a YOLO model.
    model_key: one of 'Nano', 'Small', 'Medium'
    """
    from ultralytics import YOLO

    filename = MODEL_MAP.get(model_key, MODEL_MAP["Medium"])
    model_path = APP_DIR / filename
    if not model_path.exists():
        raise FileNotFoundError(f"Model file not found: {model_path}")
    return YOLO(str(model_path))


# ── Detection ────────────────────────────────────────────────────────────────
def run_detection(model, frame, conf: float = 0.5,
                  imgsz: int = 640) -> DetectionResult:
    """
    Run YOLO tracking on a single frame.
    Returns a DetectionResult with all detected items.
    """
    results = model.track(
        source=frame,
        conf=conf,
        imgsz=imgsz,
        persist=True,
        tracker="botsort.yaml",
        verbose=False,
    )

    detection = DetectionResult()
    for box in results[0].boxes:
        name = model.names[int(box.cls[0])]
        confidence = float(box.conf[0])
        x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
        track_id = int(box.id[0]) if box.id is not None else None
        detection.items.append(
            DetectionItem(
                name=name,
                confidence=confidence,
                bbox=(x1, y1, x2, y2),
                track_id=track_id,
            )
        )

    return detection


# ── Frame Annotation ─────────────────────────────────────────────────────────
# Colour palette (BGR for OpenCV)
_GREEN     = (157, 217, 137)   # Accent green
_GREEN_BG  = (11, 14, 6)      # Dark green for text background
_WHITE     = (255, 255, 255)
_RED       = (86, 86, 255)     # BGR red for out-of-stock


def annotate_frame(frame, result: DetectionResult,
                   stock_info: dict | None = None):
    """
    Draw bounding boxes with labels and confidence on the frame.
    
    stock_info: optional dict mapping item name -> quantity.
                If provided, out-of-stock items get red bounding boxes.
    """
    import cv2

    annotated = frame.copy()
    _FONT = cv2.FONT_HERSHEY_SIMPLEX

    for item in result.items:
        x1, y1, x2, y2 = item.bbox
        is_oos = stock_info is not None and stock_info.get(item.name, 0) <= 0
        colour = _RED if is_oos else _GREEN

        # Draw bounding box
        cv2.rectangle(annotated, (x1, y1), (x2, y2), colour, 2)

        # Label
        label = f"{item.name} {item.confidence:.0%}"
        if item.track_id is not None:
            label = f"#{item.track_id} {label}"

        (tw, th), baseline = cv2.getTextSize(label, _FONT, 0.45, 1)
        label_y = max(0, y1 - 6)
        cv2.rectangle(
            annotated,
            (x1, label_y - th - 6),
            (x1 + tw + 8, label_y + 2),
            colour,
            -1,
        )
        cv2.putText(
            annotated, label,
            (x1 + 4, label_y - 3),
            _FONT, 0.45, _GREEN_BG if not is_oos else _WHITE, 1, cv2.LINE_AA,
        )

    return annotated


def frame_bgr_to_rgb(frame):
    """Convert BGR (OpenCV) frame to RGB (Streamlit display)."""
    import cv2
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
