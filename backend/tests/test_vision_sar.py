import uuid
import numpy as np
import pytest
from app.calibration import estimate_speed, fit_calibration, ground_position, ground_to_wgs84
from app.cameras import validate_stream_url
from app.config import get_settings
from app.geo import distance_bearing
from app.sar import compare_rasters, safe_asset_url
from app.schemas import CalibrationIn
from app.vision import Tracker


def calibration_data(**changes):
    data = dict(
        image_points=[[100, 100], [500, 100], [500, 500], [100, 500]],
        ground_points_m=[[0, 0], [40, 0], [40, 40], [0, 40]],
        image_width=640,
        image_height=640,
        origin_latitude=30.0878597,
        origin_longitude=31.3413867,
        survey_error_m=0.1,
        validation_image_points=[[200, 200], [400, 400]],
        validation_ground_points_m=[[10, 10], [30, 30]],
        lens_corrected=True,
        pts_validated=True,
        timestamp_error_s=0.01,
        notes="Synthetic surveyed plane for unit tests only",
    )
    data.update(changes)
    return CalibrationIn.model_validate(data)


def test_calibration_speed_and_geolocation():
    cal = fit_calibration(calibration_data())
    xy = ground_position(cal, [200, 200])
    assert xy.tolist() == pytest.approx([10, 10], abs=1e-5)
    speed = estimate_speed((0, [0, 0]), (1, [10, 0]), cal)
    assert speed["speed_mps"] == 10 and speed["speed_kmh"] == 36
    assert speed["conditional_uncertainty_95_mps"] > 0
    lat, lon = ground_to_wgs84(cal, [0, 100])
    d, b = distance_bearing(30.0878597, 31.3413867, lat, lon)
    assert d == pytest.approx(100, abs=0.01) and b == 0
    assert ground_position(cal, [700, 700]) is None


def test_no_speed_without_calibration_and_valid_time():
    cal = fit_calibration(calibration_data(pts_validated=False))
    assert estimate_speed((0, [0, 0]), (1, [10, 0]), cal) is None
    cal["pts_validated"] = True
    assert estimate_speed((1, [0, 0]), (1, [10, 0]), cal) is None
    assert estimate_speed((1, [0, 0]), (0, [10, 0]), cal) is None


def test_independent_calibration_validation_is_enforced():
    with pytest.raises(ValueError, match="error exceeds"):
        fit_calibration(calibration_data(validation_ground_points_m=[[25, 20], [45, 45]]))
    with pytest.raises(ValueError, match="degenerate"):
        fit_calibration(calibration_data(image_points=[[100, 100], [200, 200], [300, 300], [400, 400]]))
    with pytest.raises(ValueError, match="inside"):
        fit_calibration(calibration_data(validation_image_points=[[0, 0], [400, 400]]))
    with pytest.raises(ValueError, match="timestamp uncertainty"):
        fit_calibration(calibration_data(timestamp_error_s=None))


def test_tracker_ids_are_one_to_one():
    tracker = Tracker()
    items = tracker.update(
        [
            {"bbox": [10, 10, 50, 50], "confidence": 0.9, "object_type": "car"},
            {"bbox": [11, 11, 51, 51], "confidence": 0.8, "object_type": "car"},
        ],
        0,
    )
    assert items[0]["track_id"] != items[1]["track_id"]
    next_frame = tracker.update([{"bbox": [12, 12, 52, 52], "confidence": 0.9, "object_type": "car"}], 1)
    assert next_frame[0]["track_id"] in [x["track_id"] for x in items]


@pytest.mark.parametrize(
    "url", ["file:///etc/passwd", "http://127.0.0.1/", "rtsp://private.invalid/a", "ftp://test-streams.mux.dev/a"]
)
def test_camera_network_access_is_explicit(url):
    with pytest.raises(ValueError):
        validate_stream_url(url, "test-streams.mux.dev")


def test_provider_download_host_is_allowlisted():
    assert safe_asset_url("https://datapool.asf.alaska.edu/a.zip")
    for value in [
        "http://datapool.asf.alaska.edu/a",
        "https://example.com/a",
        "https://s3.us-west-2.amazonaws.com/private/a",
    ]:
        with pytest.raises(ValueError):
            safe_asset_url(value)


def test_calibrated_same_grid_sar_change(client):
    import rasterio
    from rasterio.transform import from_origin

    paths = []
    folder = get_settings().data_dir / "rasters"
    folder.mkdir(exist_ok=True)
    for values in [
        np.ones((10, 10), dtype="float32"),
        np.pad(np.ones((8, 8), dtype="float32") * 2, 1, constant_values=1),
    ]:
        identifier = str(uuid.uuid4())
        paths.append(identifier)
        with rasterio.open(
            folder / (identifier + ".tif"),
            "w",
            driver="GTiff",
            width=10,
            height=10,
            count=1,
            dtype="float32",
            crs="EPSG:32636",
            transform=from_origin(340000, 3340000, 10, 10),
        ) as dst:
            dst.write(values, 1)
    result = compare_rasters(*paths, "linear_power", 3)
    assert result["valid_pixels"] == 100 and result["changed_pixels"] == 64
    response = client.post(
        "/api/satellite/compare",
        json={
            "before_id": paths[0],
            "after_id": paths[1],
            "units": "linear_power",
            "threshold_db": 3,
            "radiometrically_calibrated": False,
            "co_registered_and_terrain_corrected": True,
        },
    )
    assert response.status_code == 422


def test_bad_raster_rejected_and_path_traversal_blocked(client):
    result = client.post("/api/satellite/rasters", files={"file": ("invalid.tif", b"not a geotiff", "image/tiff")})
    assert result.status_code == 422
    assert client.get("/api/satellite/rasters/..%2Faccess-token").status_code == 404
