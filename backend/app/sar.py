import asyncio
import uuid
from urllib.parse import urlsplit
import httpx
import numpy as np
from .config import get_settings
from .db import Download, Scene, Session


def safe_asset_url(url):
    p = urlsplit(url)
    allowed = (
        "datapool.asf.alaska.edu",
        "download.dataspace.copernicus.eu",
        "umbra-open-data-catalog.s3.amazonaws.com",
        "umbra-open-data.s3.amazonaws.com",
        "s3.us-west-2.amazonaws.com",
    )
    if p.scheme != "https" or p.hostname not in allowed or p.username or p.password:
        raise ValueError("Asset host is outside the approved provider allowlist")
    if p.hostname == "s3.us-west-2.amazonaws.com" and not p.path.startswith(
        ("/umbra-open-data/", "/umbra-open-data-catalog/")
    ):
        raise ValueError("Unexpected S3 bucket")
    return url


async def download_scene(identifier):
    cfg = get_settings()
    partial = cfg.data_dir / "downloads" / (identifier + ".part")
    partial.parent.mkdir(parents=True, exist_ok=True)
    try:
        with Session() as db:
            job = db.get(Download, identifier)
            scene = db.get(Scene, job.scene_id)
            url = safe_asset_url(scene.download_url or "")
            provider = scene.source_id
            token = cfg.asf_bearer_token if provider == "asf" else cfg.copernicus_access_token
            headers = (
                {"Authorization": "Bearer " + token.get_secret_value()}
                if provider in ("asf", "copernicus") and token.get_secret_value()
                else {}
            )
            job.status = "downloading"
            db.commit()
        async with httpx.AsyncClient(timeout=httpx.Timeout(30, read=60)) as client:
            async with client.stream("GET", url, headers=headers, follow_redirects=False) as response:
                if response.status_code != 200:
                    raise ValueError(
                        f"Download HTTP {response.status_code}; redirects/login require configured provider authentication"
                    )
                length = response.headers.get("content-length")
                if length and int(length) > cfg.max_download_bytes:
                    raise ValueError("Product exceeds MAX_DOWNLOAD_BYTES")
                received = 0
                checkpoint = 0
                with partial.open("wb") as output:
                    async for chunk in response.aiter_bytes(1024 * 1024):
                        received += len(chunk)
                        if received > cfg.max_download_bytes:
                            raise ValueError("Download exceeds byte limit")
                        output.write(chunk)
                        if received - checkpoint >= 10_000_000:
                            with Session() as db:
                                db.get(Download, identifier).bytes_received = received
                                db.commit()
                            checkpoint = received
                target = partial.with_suffix(".zip" if provider in ("asf", "copernicus") else ".tif")
                partial.rename(target)
                with Session() as db:
                    job = db.get(Download, identifier)
                    job.status, job.path, job.bytes_received = "complete", str(target), received
                    db.commit()
    except asyncio.CancelledError:
        with Session() as db:
            job = db.get(Download, identifier)
            job.status, job.error = "interrupted", "Service stopped during download; submit a new job"
            db.commit()
        partial.unlink(missing_ok=True)
        raise
    except Exception as error:
        partial.unlink(missing_ok=True)
        with Session() as db:
            job = db.get(Download, identifier)
            job.status, job.error = "failed", str(error) if isinstance(error, ValueError) else type(error).__name__
            db.commit()


def raster_path(identifier):
    # Resolve only UUID-named, previously uploaded local GeoTIFFs.
    identifier = str(uuid.UUID(identifier))
    path = get_settings().data_dir / "rasters" / (identifier + ".tif")
    if not path.is_file():
        raise ValueError("Raster not found")
    return path


def inspect_raster(path):
    import rasterio

    with rasterio.open(path, driver="GTiff") as src:
        if src.driver != "GTiff" or src.crs is None or src.width * src.height > 16_000_000:
            raise ValueError("A georeferenced GeoTIFF of at most 16 million pixels is required")
        return {
            "width": src.width,
            "height": src.height,
            "crs": str(src.crs),
            "bounds": list(src.bounds),
            "pixel_spacing": [abs(src.transform.a), abs(src.transform.e)],
            "units": "CRS units; not spatial resolution",
        }


def compare_rasters(before_id, after_id, units, threshold_db):
    import rasterio

    before, after = raster_path(before_id), raster_path(after_id)
    inspect_raster(before)
    inspect_raster(after)
    with rasterio.open(before, driver="GTiff") as a, rasterio.open(after, driver="GTiff") as b:
        if a.crs != b.crs or a.transform != b.transform or (a.width, a.height) != (b.width, b.height):
            raise ValueError("Rasters must be co-registered on the same CRS, grid, dimensions and transform")
        x, y = a.read(1, masked=True).astype(float), b.read(1, masked=True).astype(float)
        valid = ~np.ma.getmaskarray(x) & ~np.ma.getmaskarray(y) & np.isfinite(x.data) & np.isfinite(y.data)
        if units != "db":
            valid &= (x.data > 0) & (y.data > 0)
        if not valid.any():
            raise ValueError("No valid overlapping calibrated pixels")
        delta = np.full(x.shape, np.nan)
        delta[valid] = (
            y.data[valid] - x.data[valid]
            if units == "db"
            else (20 if units == "amplitude" else 10) * np.log10(y.data[valid] / x.data[valid])
        )
        change = np.full(x.shape, 255, dtype=np.uint8)
        change[valid] = (np.abs(delta[valid]) >= threshold_db).astype(np.uint8)
        identifier = str(uuid.uuid4())
        output = get_settings().data_dir / "rasters" / (identifier + ".tif")
        profile = a.profile.copy()
        profile.update(dtype="uint8", count=1, nodata=255, compress="deflate")
        with rasterio.open(output, "w", **profile) as dst:
            dst.write(change, 1)
        return {
            "raster_id": identifier,
            "valid_pixels": int(valid.sum()),
            "changed_pixels": int((change == 1).sum()),
            "changed_fraction": float((change == 1).sum() / valid.sum()),
            "threshold_db": threshold_db,
            "method": "Absolute calibrated backscatter change",
            "median_delta_db": float(np.median(delta[valid])),
            "interpretation": "Backscatter changes, not detected people, vehicles, motion or causal attribution",
        }
