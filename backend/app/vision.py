import math
import time
from datetime import datetime, timezone
import numpy as np

COCO = {0: "person", 1: "bicycle", 2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}


def iou(a, b):
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[2], b[2]), min(a[3], b[3])
    intersection = max(0, x2 - x1) * max(0, y2 - y1)
    return intersection / max(1e-9, (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - intersection)


class Tracker:
    """Conservative within-camera IoU association; IDs never fuse across sensors or sessions."""

    def __init__(self):
        self.tracks = {}
        self.next_id = 1

    def update(self, detections, frame):
        assigned = set()
        for detection in sorted(detections, key=lambda d: d["confidence"], reverse=True):
            candidates = [
                (iou(detection["bbox"], t["bbox"]), identifier)
                for identifier, t in self.tracks.items()
                if identifier not in assigned
                and frame - t["frame"] <= 5
                and t["object_type"] == detection["object_type"]
            ]
            score, identifier = max(candidates, default=(0, None))
            if score < 0.3:
                identifier = self.next_id
                self.next_id += 1
            assigned.add(identifier)
            detection["track_id"] = str(identifier)
            self.tracks[identifier] = {**detection, "frame": frame}
        self.tracks = {k: v for k, v in self.tracks.items() if frame - v["frame"] <= 5}
        return detections


class YOLOXDetector:
    def __init__(self, path):
        import onnxruntime as ort

        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        self.session = ort.InferenceSession(path, sess_options=options, providers=["CPUExecutionProvider"])
        self.input = self.session.get_inputs()[0]
        self.size = int(self.input.shape[2]) if isinstance(self.input.shape[2], int) else 416

    def detect(self, image):
        import cv2

        h, w = image.shape[:2]
        ratio = min(self.size / h, self.size / w)
        resized = cv2.resize(image, (int(w * ratio), int(h * ratio)))
        padded = np.full((self.size, self.size, 3), 114, dtype=np.uint8)
        padded[: resized.shape[0], : resized.shape[1]] = resized
        tensor = padded.transpose(2, 0, 1)[None].astype(np.float32)
        output = self.session.run(None, {self.input.name: tensor})[0][0]
        # Official YOLOX ONNX releases export raw grid offsets (decode_in_inference=False).
        grids, strides = [], []
        for stride in (8, 16, 32):
            yy, xx = np.meshgrid(np.arange(self.size // stride), np.arange(self.size // stride), indexing="ij")
            grids.append(np.stack([xx, yy], axis=2).reshape(-1, 2))
            strides.append(np.full((len(grids[-1]), 1), stride))
        if len(output) != sum(len(g) for g in grids):
            raise ValueError("Unexpected YOLOX ONNX output shape; use the documented official nano model")
        grid, stride = np.concatenate(grids), np.concatenate(strides)
        output[:, :2] = (output[:, :2] + grid) * stride
        output[:, 2:4] = np.exp(np.clip(output[:, 2:4], -20, 20)) * stride
        candidates = []
        for row in output:
            cls = int(np.argmax(row[5:]))
            score = float(row[4] * row[5 + cls])
            if cls not in COCO or score < 0.4:
                continue
            cx, cy, bw, bh = row[:4] / ratio
            box = [
                float(max(0, cx - bw / 2)),
                float(max(0, cy - bh / 2)),
                float(min(w, cx + bw / 2)),
                float(min(h, cy + bh / 2)),
            ]
            if box[2] > box[0] and box[3] > box[1]:
                candidates.append({"bbox": box, "object_type": COCO[cls], "confidence": score})
        kept = []
        for item in sorted(candidates, key=lambda d: d["confidence"], reverse=True):
            if not any(k["object_type"] == item["object_type"] and iou(k["bbox"], item["bbox"]) > 0.45 for k in kept):
                kept.append(item)
        return kept


def process_frames(cap, detector, max_frames):
    import cv2

    tracker, records, last_frame, prior_pts = Tracker(), [], None, None
    start = time.monotonic()
    pts_valid = True
    for index in range(max_frames):
        if time.monotonic() - start > 22:
            break
        ok, frame = cap.read()
        if not ok:
            break
        if frame.shape[0] * frame.shape[1] > 16_000_000:
            raise ValueError("Camera frame exceeds 16 megapixels")
        now = datetime.now(timezone.utc).isoformat()
        pts = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
        if not math.isfinite(pts) or pts < 0 or (prior_pts is not None and pts <= prior_pts):
            pts_valid = False
        prior_pts = pts
        detections = tracker.update(detector.detect(frame), index) if detector else []
        for detection in detections:
            records.append({**detection, "observed_at": now, "pts_s": pts, "frame": index})
        last_frame = frame
    if last_frame is None:
        raise RuntimeError("Stream returned no decodable frames")
    ok, jpeg = cv2.imencode(".jpg", last_frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
    if not ok:
        raise RuntimeError("Could not encode frame")
    return {
        "jpeg": jpeg.tobytes(),
        "width": last_frame.shape[1],
        "height": last_frame.shape[0],
        "detections": records,
        "pts_monotonic": pts_valid,
        "frames_read": index + 1,
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }
