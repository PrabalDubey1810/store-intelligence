"""
Detection Pipeline — emit.py
Event schema builder + emitter to the Store Intelligence API.
"""
from __future__ import annotations
import uuid
import json
import requests
import structlog
from datetime import datetime, timezone

log = structlog.get_logger(__name__)

API_INGEST_URL = "http://localhost:8000/events/ingest"
BATCH_SIZE = 100


def build_event(
    store_id:    str,
    camera_id:   str,
    visitor_id:  str,
    event_type:  str,
    timestamp:   str,
    zone_id:     str | None,
    dwell_ms:    int,
    is_staff:    bool,
    confidence:  float,
    session_seq: int = 1,
    queue_depth: int | None = None,
    sku_zone:    str | None = None,
) -> dict:
    """Build a fully compliant event dict matching the required schema."""
    return {
        "event_id":   str(uuid.uuid4()),
        "store_id":   store_id,
        "camera_id":  camera_id,
        "visitor_id": visitor_id,
        "event_type": event_type,
        "timestamp":  timestamp,
        "zone_id":    zone_id,
        "dwell_ms":   max(0, int(dwell_ms)),
        "is_staff":   bool(is_staff),
        "confidence": round(float(confidence), 4),
        "metadata": {
            "queue_depth":  queue_depth,
            "sku_zone":     sku_zone,
            "session_seq":  session_seq,
        }
    }


class EventEmitter:
    """
    Buffers events and sends them in batches to the API.
    Also writes to a local JSONL file for replay.
    """

    def __init__(self, api_url: str = API_INGEST_URL, output_path: str = "events.jsonl"):
        self.api_url = api_url
        self.output_path = output_path
        self._buffer: list[dict] = []
        self._session_counters: dict[str, int] = {}  # visitor_id → sequence count
        self._output_file = open(output_path, "a", encoding="utf-8")

    def next_seq(self, visitor_id: str) -> int:
        self._session_counters[visitor_id] = self._session_counters.get(visitor_id, 0) + 1
        return self._session_counters[visitor_id]

    def emit(self, event: dict):
        """Add event to buffer and write to JSONL file immediately."""
        self._output_file.write(json.dumps(event) + "\n")
        self._output_file.flush()
        self._buffer.append(event)

        if len(self._buffer) >= BATCH_SIZE:
            self.flush()

    def flush(self):
        """Send buffered events to API."""
        if not self._buffer:
            return
        batch = self._buffer.copy()
        self._buffer.clear()

        try:
            resp = requests.post(
                self.api_url,
                json={"events": batch},
                timeout=10,
            )
            resp.raise_for_status()
            result = resp.json()
            log.info("events_sent",
                     accepted=result.get("accepted"),
                     rejected=result.get("rejected"),
                     batch_size=len(batch))
        except Exception as e:
            log.warning("api_send_failed", error=str(e), batch_size=len(batch))
            # Re-buffer for retry on next flush
            self._buffer = batch + self._buffer

    def close(self):
        self.flush()
        self._output_file.close()


def replay_jsonl(jsonl_path: str, api_url: str = API_INGEST_URL, batch_size: int = 500):
    """
    Replay a pre-processed events.jsonl file into the API.
    Used when running detect.py in batch mode.
    """
    batch = []
    sent = 0

    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
                batch.append(event)
            except json.JSONDecodeError:
                continue

            if len(batch) >= batch_size:
                _send_batch(batch, api_url)
                sent += len(batch)
                batch = []

    if batch:
        _send_batch(batch, api_url)
        sent += len(batch)

    log.info("replay_complete", total_sent=sent, path=jsonl_path)
    return sent


def _send_batch(events: list[dict], api_url: str):
    try:
        resp = requests.post(api_url, json={"events": events}, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        log.error("batch_send_error", error=str(e), count=len(events))
