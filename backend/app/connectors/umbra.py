from collections import deque
from urllib.parse import urljoin, urlsplit
from shapely.geometry import box
from .base import Batch, Connector, parse_time, request
from ..db import utcnow
from ..geo import intersects_area


class UmbraConnector(Connector):
    id = "umbra"
    interval = 86400

    async def poll(self, client, area):
        root = "https://umbra-open-data-catalog.s3.amazonaws.com/stac/catalog.json"
        queue, seen = deque([root]), set()
        batch = Batch(
            quality="Historical open SAR STAC catalogue; bounded traversal cannot establish complete AOI coverage"
        )
        while queue and len(seen) < 60:
            url = queue.popleft()
            if url in seen:
                continue
            parsed = urlsplit(url)
            if parsed.scheme != "https" or parsed.hostname not in (
                "umbra-open-data-catalog.s3.amazonaws.com",
                "s3.us-west-2.amazonaws.com",
            ):
                continue
            if parsed.hostname == "s3.us-west-2.amazonaws.com" and not parsed.path.startswith(
                "/umbra-open-data-catalog/"
            ):
                continue
            seen.add(url)
            doc = (await request(client, url)).json()
            bbox = doc.get("bbox")
            if bbox and len(bbox) == 4 and not intersects_area(box(*bbox).__geo_interface__, area):
                continue
            if doc.get("type") == "Feature" and doc.get("geometry"):
                if not intersects_area(doc["geometry"], area):
                    continue
                p, assets = doc["properties"], doc.get("assets", {})
                acquired = parse_time(p["datetime"])
                if acquired > utcnow():
                    continue
                image = next((a.get("href") for a in assets.values() if "image/tiff" in a.get("type", "")), None)
                preview = next((a.get("href") for a in assets.values() if "thumbnail" in a.get("roles", [])), None)
                batch.scenes.append(
                    {
                        "id": "umbra:" + doc["id"],
                        "source_id": self.id,
                        "name": doc["id"],
                        "platform": p.get("platform"),
                        "acquired_at": acquired,
                        "footprint": doc["geometry"],
                        "product_type": "SAR",
                        "resolution_m": None,
                        "preview_url": urljoin(url, preview) if preview else None,
                        "download_url": urljoin(url, image) if image else None,
                        "details": {
                            "catalogue_url": url,
                            "assets": assets,
                            "properties": p,
                            "resolution_note": "Per-product resolution must be read from metadata; GSD alone is not resolution",
                        },
                    }
                )
            for link in doc.get("links", []):
                if link.get("rel") in ("child", "item"):
                    queue.append(urljoin(url, link["href"]))
        batch.details = {
            "documents_checked": len(seen),
            "truncated": bool(queue),
            "coverage_complete": not bool(queue),
            "coverage_statement": "Only catalogue contents searched; a negative result does not rule out other Umbra holdings",
        }
        return batch
