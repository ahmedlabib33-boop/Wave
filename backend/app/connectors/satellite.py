from datetime import timedelta
from .base import Batch, Connector, parse_time, request
from ..db import utcnow
from ..geo import intersects_area, ring


class ASFConnector(Connector):
    id = "asf"
    interval = 21600

    async def poll(self, client, area, start=None, end=None):
        poly = ring(area.latitude, area.longitude, area.radius_m, 32)["coordinates"][0]
        wkt = "POLYGON((" + ",".join(f"{lon:.7f} {lat:.7f}" for lon, lat in poly) + "))"
        r = await request(
            client,
            "https://api.daac.asf.alaska.edu/services/search/param",
            params={
                "platform": "SENTINEL-1",
                "intersectsWith": wkt,
                "processingLevel": "GRD_HD",
                "output": "geojson",
                "maxResults": 30,
                "start": (start or utcnow() - timedelta(days=90)).isoformat(),
                "end": (end or utcnow()).isoformat(),
            },
        )
        data = r.json()
        if not isinstance(data.get("features"), list):
            raise ValueError("ASF response is not a GeoJSON FeatureCollection")
        batch = Batch(quality="Historical scene footprints; no live object detection")
        for feature in data["features"]:
            p = feature["properties"]
            if not intersects_area(feature["geometry"], area):
                continue
            acquired = parse_time(p["startTime"])
            if acquired > utcnow():
                continue
            preview = p.get("browse") or []
            batch.scenes.append(
                {
                    "id": "asf:" + p["fileID"],
                    "source_id": self.id,
                    "name": p["sceneName"],
                    "platform": p.get("platform"),
                    "acquired_at": acquired,
                    "footprint": feature["geometry"],
                    "product_type": p.get("processingLevel"),
                    "resolution_m": None,
                    "preview_url": preview[0] if preview else None,
                    "download_url": p.get("url"),
                    "details": {
                        **p,
                        "resolution_note": "Catalogue does not supply spatial resolution; pixel spacing is not resolution",
                        "download_auth": "NASA Earthdata account/token may be required",
                    },
                }
            )
        return batch


class CopernicusConnector(Connector):
    id = "copernicus"
    interval = 21600

    async def poll(self, client, area):
        coords = ring(area.latitude, area.longitude, area.radius_m, 32)["coordinates"][0]
        wkt = "POLYGON((" + ",".join(f"{lon:.7f} {lat:.7f}" for lon, lat in coords) + "))"
        r = await request(
            client,
            "https://catalogue.dataspace.copernicus.eu/odata/v1/Products",
            params={
                "$filter": f"Collection/Name eq 'SENTINEL-1' and OData.CSC.Intersects(area=geography'SRID=4326;{wkt}') and ContentDate/Start le {utcnow().isoformat()}",
                "$top": 20,
                "$orderby": "ContentDate/Start desc",
            },
        )
        products = r.json()["value"]
        batch = Batch(quality="Historical Sentinel-1 metadata; imagery downloads need CDSE authentication")
        for p in products:
            footprint = p.get("GeoFootprint")
            if not footprint or not intersects_area(footprint, area):
                continue
            batch.scenes.append(
                {
                    "id": "cdse:" + p["Id"],
                    "source_id": self.id,
                    "name": p["Name"],
                    "platform": p["Name"].split("_")[0],
                    "acquired_at": parse_time(p["ContentDate"]["Start"]),
                    "footprint": footprint,
                    "product_type": "Sentinel-1",
                    "resolution_m": None,
                    "preview_url": None,
                    "download_url": f"https://download.dataspace.copernicus.eu/odata/v1/Products({p['Id']})/$value",
                    "details": {
                        "online": p.get("Online"),
                        "size_bytes": p.get("ContentLength"),
                        "content_date": p["ContentDate"],
                        "download_auth": "Copernicus access token required",
                    },
                }
            )
        return batch
