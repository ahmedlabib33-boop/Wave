import math
import uuid
import numpy as np
from shapely.geometry import MultiPoint, Point
from .geo import GEOD


def project(matrix, point):
    value = np.asarray(matrix, dtype=float) @ np.array([*point, 1.0])
    if abs(value[2]) < 1e-10:
        raise ValueError("Point projects to infinity")
    return value[:2] / value[2]


def fit_calibration(data):
    import cv2

    if len(data.image_points) != len(data.ground_points_m) or len(data.validation_image_points) != len(
        data.validation_ground_points_m
    ):
        raise ValueError("Image and ground point counts must match")
    image = np.array(data.image_points, dtype=float)
    ground = np.array(data.ground_points_m, dtype=float)
    if not np.isfinite(image).all() or not np.isfinite(ground).all():
        raise ValueError("Calibration points must be finite")
    if np.any(image < 0) or np.any(image[:, 0] > data.image_width) or np.any(image[:, 1] > data.image_height):
        raise ValueError("Calibration points outside image dimensions")
    hull = MultiPoint(data.image_points).convex_hull
    if hull.area < 100 or MultiPoint(data.ground_points_m).convex_hull.area < 1:
        raise ValueError("Calibration is degenerate or nearly collinear")
    matrix, _ = cv2.findHomography(image, ground, method=0)
    if matrix is None or not np.isfinite(matrix).all() or abs(np.linalg.det(matrix)) < 1e-12:
        raise ValueError("Cannot solve a stable homography")
    for point in data.validation_image_points:
        if not hull.covers(Point(point)):
            raise ValueError("Independent validation points must be inside the calibrated polygon")
    fit_errors = [np.linalg.norm(project(matrix, a) - b) for a, b in zip(image, ground)]
    errors = [
        np.linalg.norm(project(matrix, a) - b)
        for a, b in zip(data.validation_image_points, data.validation_ground_points_m)
    ]
    rmse = float(np.sqrt(np.mean(np.square(errors))))
    if rmse > max(1.0, data.survey_error_m * 3) or max(fit_errors) > max(1.0, data.survey_error_m * 3):
        raise ValueError("Calibration error exceeds tolerance; re-survey ground points")
    if data.pts_validated and data.timestamp_error_s is None:
        raise ValueError("Validated stream PTS requires a stated timestamp uncertainty")
    return {
        **data.model_dump(),
        "calibration_id": str(uuid.uuid4()),
        "homography": matrix.tolist(),
        "validation_rmse_m": rmse,
        "position_error_m": math.hypot(rmse, data.survey_error_m),
    }


def ground_position(calibration, point):
    if not MultiPoint(calibration["image_points"]).convex_hull.covers(Point(point)):
        return None
    return project(calibration["homography"], point)


def ground_to_wgs84(calibration, xy):
    east, north = xy
    lon, lat, _ = GEOD.fwd(
        calibration["origin_longitude"],
        calibration["origin_latitude"],
        math.degrees(math.atan2(east, north)),
        math.hypot(east, north),
    )
    return lat, lon


def estimate_speed(first, last, calibration):
    if not calibration.get("pts_validated") or calibration.get("timestamp_error_s") is None:
        return None
    t0, p0 = first
    t1, p1 = last
    elapsed = t1 - t0
    if not 0.2 <= elapsed <= 5:
        return None
    speed = math.dist(p0, p1) / elapsed
    if speed > 100:
        return None
    sigma = math.sqrt(
        2 * calibration["position_error_m"] ** 2 / elapsed**2
        + speed**2 * 2 * calibration["timestamp_error_s"] ** 2 / elapsed**2
    )
    return {
        "speed_mps": speed,
        "speed_kmh": speed * 3.6,
        "conditional_uncertainty_95_mps": sigma * 1.96,
        "uncertainty_exclusions": "Survey/validation and stated timing error only; excludes detector footpoint error, occlusion, track misassociation and model bias. Total uncertainty is unknown.",
        "elapsed_s": elapsed,
        "distance_m": math.dist(p0, p1),
        "basis": "ground-plane displacement / validated stream PTS interval",
    }
