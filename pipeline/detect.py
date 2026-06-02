"""
Detection Pipeline — detect.py
Main CCTV processing script using YOLOv8n + ByteTrack.

Usage:
    python pipeline/detect.py \\
        --clips-dir ./data/cctv \\
        --store-id ST1008 \\
        --layout ./data/store_layout.json \\
        --output ./data/events.jsonl \\
        --api http://localhost:8000

Processes all .mp4 files in clips-dir and emits structured events.
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO

# Add pipeline dir to path for sibling imports
sys.path.insert(0, str(Path(__file__).parent))
from tracker import (
    SessionRegistry, DirectionTracker, ZoneClassifier,
    detect_staff, extract_embedding, bbox_center,
)
from emit import EventEmitter, build_event

import structlog
structlog.configure()
log = structlog.get_logger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Camera role mapping — adjust based on actual footage inspection
# ─────────────────────────────────────────────────────────────────────────────
CAMERA_ROLES = {
    "CAM 1.mp4": "CAM_ENTRY_01",
    "CAM 2.mp4": "CAM_FLOOR_01",
    "CAM 3.mp4": "CAM_BILLING_01",
    "CAM 4.mp4": "CAM_FLOOR_02",
    "CAM 5.mp4": "CAM_ENTRY_02",
}

# Clip start time (IST → UTC): Brigade store opens ~10am IST = 4:30am UTC
# Adjust to actual recording time from metadata if available
CLIP_START_IST = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc) - timedelta(hours=5, minutes=30)
FPS_EXPECTED = 15
DWELL_EMIT_INTERVAL_FRAMES = 450  # 30 seconds at 15fps → emit ZONE_DWELL
MIN_CONF = 0.35  # Low threshold — never suppress, just flag


def load_store_layout(layout_path: str, store_id: str) -> list[dict]:
    """Load zone polygons from store_layout.json."""
    with open(layout_path) as f:
        layout = json.load(f)

    # Handle both dict-of-stores and flat list formats
    if isinstance(layout, dict):
        store_data = layout.get(store_id, layout.get("zones", layout))
    else:
        store_data = layout

    if isinstance(store_data, dict):
        zones = store_data.get("zones", [])
    else:
        zones = store_data

    log.info("layout_loaded", store_id=store_id, zone_count=len(zones))
    return zones


def process_clip(
    video_path: str,
    store_id: str,
    camera_id: str,
    zones: list[dict],
    emitter: EventEmitter,
    model: YOLO,
    clip_start: datetime,
    entry_y_ratio: float = 0.3,  # Entry line at 30% of frame height
):
    """
    Process a single CCTV clip and emit events.
    Returns total events emitted.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        log.error("video_open_failed", path=video_path)
        return 0

    fps = cap.get(cv2.CAP_PROP_FPS) or FPS_EXPECTED
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    width  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    cap.release()

    entry_y = height * entry_y_ratio

    registry  = SessionRegistry()
    direction = DirectionTracker(entry_y=entry_y, margin=int(height * 0.05))
    zone_cls  = ZoneClassifier(zones)

    # Zone dwell tracking: visitor_id → {zone_id, frame_entered, last_dwell_frame}
    dwell_tracker: dict[str, dict] = {}
    # Billing queue: track current depth
    billing_zone_visitors: set[str] = set()

    emitted_entries = set()
    events_emitted = 0
    frame_idx = 0

    log.info("processing_clip",
             camera_id=camera_id, fps=fps, frames=total_frames,
             size=f"{width}x{height}")

    for result in model.track(
        source=video_path,
        tracker="bytetrack.yaml",
        persist=True,
        conf=MIN_CONF,
        classes=[0],   # Person class only
        stream=True,
        verbose=False,
    ):
        timestamp = clip_start + timedelta(seconds=frame_idx / fps)
        ts_str = timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")
        frame = result.orig_img
        active_ids = set()

        if result.boxes is None or result.boxes.id is None:
            frame_idx += 1
            continue

        current_billing_visitors = set()

        for box in result.boxes:
            if box.id is None:
                continue

            track_id   = int(box.id.item())
            bbox       = box.xyxy[0].tolist()
            confidence = float(box.conf[0].item())
            active_ids.add(track_id)

            # Extract appearance embedding for Re-ID
            embedding = extract_embedding(frame, bbox)

            # Get or assign visitor_id
            visitor_id, event_hint = registry.get_or_assign(
                track_id, embedding, camera_id
            )

            # Ghost detection filter
            if not registry.is_valid_track(track_id):
                continue

            is_staff = detect_staff(frame, bbox)
            zone_id  = zone_cls.classify(bbox)

            # ── Entry/Exit events ────────────────────────────────────────────
            crossing = direction.update(track_id, bbox)
            if crossing == "ENTRY" or visitor_id not in emitted_entries:
                event_type = "REENTRY" if event_hint == "reentry" else "ENTRY"
                emitted_entries.add(visitor_id)
                seq = emitter.next_seq(visitor_id)
                emitter.emit(build_event(
                    store_id=store_id, camera_id=camera_id,
                    visitor_id=visitor_id, event_type=event_type,
                    timestamp=ts_str, zone_id=None,
                    dwell_ms=0, is_staff=is_staff,
                    confidence=confidence, session_seq=seq,
                ))
                events_emitted += 1

            elif crossing == "EXIT":
                registry.on_exit(track_id)
                if visitor_id in dwell_tracker:
                    del dwell_tracker[visitor_id]
                seq = emitter.next_seq(visitor_id)
                emitter.emit(build_event(
                    store_id=store_id, camera_id=camera_id,
                    visitor_id=visitor_id, event_type="EXIT",
                    timestamp=ts_str, zone_id=None,
                    dwell_ms=0, is_staff=is_staff,
                    confidence=confidence, session_seq=seq,
                ))
                events_emitted += 1
                continue

            # ── Zone events ──────────────────────────────────────────────────
            if zone_id:
                prev = dwell_tracker.get(visitor_id)

                if prev is None:
                    # Zone enter
                    dwell_tracker[visitor_id] = {
                        "zone_id": zone_id,
                        "frame_entered": frame_idx,
                        "last_dwell_frame": frame_idx,
                    }
                    seq = emitter.next_seq(visitor_id)
                    emitter.emit(build_event(
                        store_id=store_id, camera_id=camera_id,
                        visitor_id=visitor_id, event_type="ZONE_ENTER",
                        timestamp=ts_str, zone_id=zone_id,
                        dwell_ms=0, is_staff=is_staff,
                        confidence=confidence, session_seq=seq,
                        sku_zone=zone_id,
                    ))
                    events_emitted += 1

                elif prev["zone_id"] != zone_id:
                    # Zone change → emit EXIT from old, ENTER into new
                    old_dwell = int((frame_idx - prev["frame_entered"]) / fps * 1000)
                    seq = emitter.next_seq(visitor_id)
                    emitter.emit(build_event(
                        store_id=store_id, camera_id=camera_id,
                        visitor_id=visitor_id, event_type="ZONE_EXIT",
                        timestamp=ts_str, zone_id=prev["zone_id"],
                        dwell_ms=old_dwell, is_staff=is_staff,
                        confidence=confidence, session_seq=seq,
                    ))
                    seq = emitter.next_seq(visitor_id)
                    emitter.emit(build_event(
                        store_id=store_id, camera_id=camera_id,
                        visitor_id=visitor_id, event_type="ZONE_ENTER",
                        timestamp=ts_str, zone_id=zone_id,
                        dwell_ms=0, is_staff=is_staff,
                        confidence=confidence, session_seq=seq,
                        sku_zone=zone_id,
                    ))
                    dwell_tracker[visitor_id] = {
                        "zone_id": zone_id,
                        "frame_entered": frame_idx,
                        "last_dwell_frame": frame_idx,
                    }
                    events_emitted += 2

                else:
                    # Same zone — check for 30-second dwell event
                    frames_since_dwell = frame_idx - prev["last_dwell_frame"]
                    if frames_since_dwell >= DWELL_EMIT_INTERVAL_FRAMES:
                        dwell_ms = int((frame_idx - prev["frame_entered"]) / fps * 1000)
                        seq = emitter.next_seq(visitor_id)
                        emitter.emit(build_event(
                            store_id=store_id, camera_id=camera_id,
                            visitor_id=visitor_id, event_type="ZONE_DWELL",
                            timestamp=ts_str, zone_id=zone_id,
                            dwell_ms=dwell_ms, is_staff=is_staff,
                            confidence=confidence, session_seq=seq,
                            sku_zone=zone_id,
                        ))
                        dwell_tracker[visitor_id]["last_dwell_frame"] = frame_idx
                        events_emitted += 1

                # ── Billing queue events ─────────────────────────────────────
                BILLING_ZONES = {"BILLING", "BILLING_COUNTER", "CHECKOUT", "CASHIER"}
                if zone_id.upper() in BILLING_ZONES and not is_staff:
                    current_billing_visitors.add(visitor_id)

        # Update billing queue state
        newly_joined = current_billing_visitors - billing_zone_visitors
        for vid in newly_joined:
            queue_depth = len(current_billing_visitors)
            if queue_depth > 0:
                seq = emitter.next_seq(vid)
                emitter.emit(build_event(
                    store_id=store_id, camera_id=camera_id,
                    visitor_id=vid, event_type="BILLING_QUEUE_JOIN",
                    timestamp=ts_str, zone_id="BILLING",
                    dwell_ms=0, is_staff=False,
                    confidence=0.9, session_seq=seq,
                    queue_depth=queue_depth,
                ))
                events_emitted += 1

        billing_zone_visitors = current_billing_visitors
        direction.cleanup(active_ids)
        frame_idx += 1

        if frame_idx % (fps * 60) == 0:
            log.info("clip_progress",
                     camera_id=camera_id,
                     minutes_processed=int(frame_idx / fps / 60),
                     events_emitted=events_emitted)

    emitter.flush()
    log.info("clip_done",
             camera_id=camera_id,
             total_frames=frame_idx,
             events_emitted=events_emitted)
    return events_emitted


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Store Intelligence Detection Pipeline")
    parser.add_argument("--clips-dir", required=True, help="Directory with .mp4 clips")
    parser.add_argument("--store-id", default="ST1008", help="Store ID (default: ST1008)")
    parser.add_argument("--layout", required=True, help="Path to store_layout.json")
    parser.add_argument("--output", default="events.jsonl", help="Output JSONL file")
    parser.add_argument("--api", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--model", default="yolov8n.pt", help="YOLO model weights")
    parser.add_argument("--entry-y-ratio", type=float, default=0.3,
                        help="Entry line position as ratio of frame height (default 0.3)")
    args = parser.parse_args()

    log.info("pipeline_start",
             clips_dir=args.clips_dir,
             store_id=args.store_id,
             output=args.output)

    # Load YOLO model
    model = YOLO(args.model)
    log.info("model_loaded", model=args.model)

    # Load zones
    zones = load_store_layout(args.layout, args.store_id)

    # Set up emitter
    emitter = EventEmitter(
        api_url=f"{args.api}/events/ingest",
        output_path=args.output,
    )

    # Process all clips
    clips_dir = Path(args.clips_dir)
    mp4_files = sorted(clips_dir.glob("*.mp4"))

    if not mp4_files:
        log.error("no_clips_found", clips_dir=str(clips_dir))
        sys.exit(1)

    total_events = 0
    for clip_path in mp4_files:
        camera_id = CAMERA_ROLES.get(clip_path.name, f"CAM_{clip_path.stem}")
        log.info("starting_clip", clip=clip_path.name, camera_id=camera_id)

        events = process_clip(
            video_path=str(clip_path),
            store_id=args.store_id,
            camera_id=camera_id,
            zones=zones,
            emitter=emitter,
            model=model,
            clip_start=CLIP_START_IST,
            entry_y_ratio=args.entry_y_ratio,
        )
        total_events += events

    emitter.close()
    log.info("pipeline_complete",
             total_clips=len(mp4_files),
             total_events=total_events,
             output=args.output)


if __name__ == "__main__":
    main()
