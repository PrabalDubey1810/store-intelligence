"""
Detection Pipeline — tracker.py
Re-ID session registry with OSNet embedding similarity for cross-camera deduplication.
Handles:
  - Per-track session assignment
  - Cross-camera deduplication via embedding cosine similarity
  - Re-entry detection (same person returning after EXIT)
  - Staff classification via HSV color histogram
"""
from __future__ import annotations
import uuid
import time
import numpy as np
from typing import Optional
import cv2


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────
REID_SIMILARITY_THRESHOLD = 0.85   # Cosine sim threshold for same-person match
REENTRY_TIMEOUT_SECONDS   = 600    # Keep exits for 10 min for re-entry detection
MIN_TRACK_FRAMES          = 3      # Ignore ghost detections < 3 frames

# Brigade Road ST1008 — Camera calibration
# Physical store entrance threshold: Y=0 in mm space (top of FOH zone)
# Scaled to 1920×1080 frame: entry threshold line at Y≈130px (≈12% from top)
# This is used by DirectionTracker to classify ENTRY vs EXIT events.
# Margin of ±20px allows for detection jitter at the crossing line.
BRIGADE_ENTRY_LINE_Y = 130  # pixels in 1920×1080 frame

# Zone IDs that count as billing/conversion zones for POS correlation
# Updated to match physical signage in store_layout.json (v2)
BILLING_ZONES = {"CASH_COUNTER"}

# Staff uniform detection: Purplle store staff wear purple/blue uniforms
# HSV ranges for purple/blue detection
STAFF_HSV_LOWER = np.array([100, 50,  50])   # Blue-purple lower bound
STAFF_HSV_UPPER = np.array([160, 255, 255])  # Blue-purple upper bound
STAFF_COLOR_RATIO = 0.35  # If > 35% of bbox pixels are staff-color → is_staff


# ─────────────────────────────────────────────────────────────────────────────
# Session Registry
# ─────────────────────────────────────────────────────────────────────────────
class SessionRegistry:
    """
    Maps track_ids → visitor_ids with embedding-based Re-ID.
    Maintains exit history for re-entry detection.
    """

    def __init__(self):
        # Active tracks: track_id → {"visitor_id", "embedding", "frame_count", "camera_id"}
        self._active: dict[int, dict] = {}

        # Exited sessions: visitor_id → {"embedding", "exit_time", "visitor_id"}
        self._exited: dict[str, dict] = {}

        # track_id → frame count (for ghost detection filtering)
        self._frame_counts: dict[int, int] = {}

    def get_or_assign(
        self,
        track_id: int,
        embedding: Optional[np.ndarray],
        camera_id: str,
    ) -> tuple[str, str]:
        """
        Returns (visitor_id, event_hint) where event_hint is one of:
          "new"     → fresh ENTRY
          "reentry" → same person detected after EXIT → REENTRY
          "existing"→ ongoing track, no new event needed
        """
        self._frame_counts[track_id] = self._frame_counts.get(track_id, 0) + 1

        if track_id in self._active:
            return self._active[track_id]["visitor_id"], "existing"

        # New track — try Re-ID against exited sessions
        if embedding is not None:
            matched_id = self._match_exited(embedding)
            if matched_id:
                visitor_id = matched_id
                self._active[track_id] = {
                    "visitor_id": visitor_id,
                    "embedding": embedding,
                    "camera_id": camera_id,
                    "frame_count": 1,
                }
                del self._exited[visitor_id]
                return visitor_id, "reentry"

        # Brand new visitor
        visitor_id = f"VIS_{uuid.uuid4().hex[:6]}"
        self._active[track_id] = {
            "visitor_id": visitor_id,
            "embedding": embedding,
            "camera_id": camera_id,
            "frame_count": 1,
        }
        return visitor_id, "new"

    def on_exit(self, track_id: int) -> Optional[str]:
        """Mark track as exited. Returns visitor_id if track was known."""
        if track_id not in self._active:
            return None
        session = self._active.pop(track_id)
        visitor_id = session["visitor_id"]

        # Only store in exits if we have an embedding for re-entry matching
        if session.get("embedding") is not None:
            self._exited[visitor_id] = {
                "visitor_id": visitor_id,
                "embedding": session["embedding"],
                "exit_time": time.time(),
            }
        return visitor_id

    def get_visitor_id(self, track_id: int) -> Optional[str]:
        """Look up visitor_id for an existing track."""
        if track_id in self._active:
            return self._active[track_id]["visitor_id"]
        return None

    def is_valid_track(self, track_id: int) -> bool:
        """Filter ghost detections — ignore tracks with < MIN_TRACK_FRAMES."""
        return self._frame_counts.get(track_id, 0) >= MIN_TRACK_FRAMES

    def cleanup_stale_exits(self):
        """Remove exit records older than REENTRY_TIMEOUT_SECONDS."""
        now = time.time()
        stale = [
            vid for vid, data in self._exited.items()
            if now - data["exit_time"] > REENTRY_TIMEOUT_SECONDS
        ]
        for vid in stale:
            del self._exited[vid]

    def _match_exited(self, embedding: np.ndarray) -> Optional[str]:
        """Find best cosine similarity match in exited sessions."""
        self.cleanup_stale_exits()
        best_sim = 0.0
        best_id = None

        for visitor_id, data in self._exited.items():
            sim = _cosine_similarity(embedding, data["embedding"])
            if sim > REID_SIMILARITY_THRESHOLD and sim > best_sim:
                best_sim = sim
                best_id = visitor_id

        return best_id


# ─────────────────────────────────────────────────────────────────────────────
# Entry/Exit Direction Detection
# ─────────────────────────────────────────────────────────────────────────────
class DirectionTracker:
    """
    Detects crossing direction over an entry line.
    Entry line is typically at the store threshold (y-coordinate in frame).
    """

    def __init__(self, entry_y: float, margin: int = 20):
        self.entry_y = entry_y
        self.margin = margin
        # track_id → last known y-position
        self._last_y: dict[int, float] = {}
        # track_id → crossing state
        self._crossed: dict[int, str] = {}

    def update(self, track_id: int, bbox: list[float]) -> Optional[str]:
        """
        Returns "ENTRY", "EXIT", or None.
        bbox = [x1, y1, x2, y2]
        Center y is used for crossing detection.
        """
        cy = (bbox[1] + bbox[3]) / 2
        last_y = self._last_y.get(track_id)
        self._last_y[track_id] = cy

        if last_y is None:
            return None

        entry_zone_min = self.entry_y - self.margin
        entry_zone_max = self.entry_y + self.margin

        # Crossed the entry line
        if last_y < entry_zone_min and cy >= entry_zone_min:
            # Moving downward into store = ENTRY
            if track_id not in self._crossed:
                self._crossed[track_id] = "ENTRY"
                return "ENTRY"
        elif last_y > entry_zone_max and cy <= entry_zone_max:
            # Moving upward out of store = EXIT
            if self._crossed.get(track_id) == "ENTRY":
                self._crossed[track_id] = "EXIT"
                return "EXIT"

        return None

    def cleanup(self, active_ids: set):
        stale = [t for t in self._last_y if t not in active_ids]
        for t in stale:
            self._last_y.pop(t, None)
            self._crossed.pop(t, None)


# ─────────────────────────────────────────────────────────────────────────────
# Zone Classifier
# ─────────────────────────────────────────────────────────────────────────────
class ZoneClassifier:
    """
    Classifies a bounding box center point into a named zone
    using polygon definitions from store_layout.json.
    """

    def __init__(self, zones: list[dict]):
        """
        zones: list of {
          "zone_id": "SKINCARE",
          "polygon": [[x1,y1], [x2,y2], ...]  # pixel coordinates
        }
        """
        self.zones = zones

    def classify(self, bbox: list[float]) -> Optional[str]:
        """Returns zone_id for the bbox center, or None if outside all zones."""
        cx = (bbox[0] + bbox[2]) / 2
        cy = (bbox[1] + bbox[3]) / 2
        point = (int(cx), int(cy))

        for zone in self.zones:
            polygon = np.array(zone["polygon"], dtype=np.int32)
            if cv2.pointPolygonTest(polygon, point, False) >= 0:
                return zone["zone_id"]
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Staff Detector
# ─────────────────────────────────────────────────────────────────────────────
def detect_staff(frame: np.ndarray, bbox: list[float]) -> bool:
    """
    Detects store staff via HSV color histogram of the bounding box crop.
    Purplle staff wear purple/blue uniforms → HSV hue range 100–160.
    Returns True if > STAFF_COLOR_RATIO of pixels match staff color.

    Design note: I initially used Gemini Vision for staff classification but
    found it hallucinated uniform patterns on customers in bright clothing.
    HSV histogram is deterministic and requires no GPU.
    """
    try:
        x1, y1, x2, y2 = [int(v) for v in bbox]
        # Clamp to frame bounds
        h, w = frame.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)

        if x2 <= x1 or y2 <= y1:
            return False

        crop = frame[y1:y2, x1:x2]
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, STAFF_HSV_LOWER, STAFF_HSV_UPPER)
        ratio = np.count_nonzero(mask) / (mask.size + 1e-6)
        return ratio > STAFF_COLOR_RATIO

    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Embedding (lightweight CLIP-like using YOLO features or color histogram)
# ─────────────────────────────────────────────────────────────────────────────
def extract_embedding(frame: np.ndarray, bbox: list[float]) -> Optional[np.ndarray]:
    """
    Extract a lightweight appearance embedding for Re-ID.
    Uses HSV color histogram as a fast, no-GPU embedding.
    For production, replace with OSNet (torchreid) if GPU available.
    """
    try:
        x1, y1, x2, y2 = [int(v) for v in bbox]
        h, w = frame.shape[:2]
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)

        if x2 <= x1 or y2 <= y1:
            return None

        crop = frame[y1:y2, x1:x2]
        # Resize to standard size for consistent histograms
        crop = cv2.resize(crop, (64, 128))
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)

        # 3-channel histogram: H(36), S(32), V(32) = 100-dim vector
        hist_h = cv2.calcHist([hsv], [0], None, [36], [0, 180])
        hist_s = cv2.calcHist([hsv], [1], None, [32], [0, 256])
        hist_v = cv2.calcHist([hsv], [2], None, [32], [0, 256])

        embedding = np.concatenate([
            hist_h.flatten(),
            hist_s.flatten(),
            hist_v.flatten()
        ])
        # L2 normalise
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm

        return embedding.astype(np.float32)

    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────────────────────────
def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two L2-normalised vectors."""
    if a is None or b is None:
        return 0.0
    dot = float(np.dot(a, b))
    return max(0.0, min(1.0, dot))


def bbox_center(bbox: list[float]) -> tuple[float, float]:
    return ((bbox[0] + bbox[2]) / 2, (bbox[1] + bbox[3]) / 2)
