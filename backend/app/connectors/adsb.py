from datetime import datetime, timedelta, timezone
from math import ceil, isfinite
from .base import Batch, Connector, request
from ..geo import distance_bearing
from ..schemas import ObservationIn


class ADSBConnector(Connector):
    id = "adsb_lol"
    interval = 30

    async def poll(self, client, area):
        # API radius is nautical miles; over-query then filter exactly in WGS84 metres.
        radius_nm = ceil(area.radius_m / 1852)
        r = await request(client, f"https://api.adsb.lol/v2/point/{area.latitude}/{area.longitude}/{radius_nm}")
        data = r.json()
        if not isinstance(data.get("ac"), list) or not isinstance(data.get("now"), (int, float)):
            raise ValueError("Unexpected ADS-B response schema")
        # Documented API response clock is Unix milliseconds.
        response_at = datetime.fromtimestamp(data["now"] / 1000, timezone.utc)
        batch = Batch(quality="Receiver-dependent ADS-B positions; zero returned aircraft is not proof of an empty sky")
        skipped = 0
        for ac in data["ac"]:
            lat, lon, age = ac.get("lat"), ac.get("lon"), ac.get("seen_pos")
            if not all(isinstance(x, (int, float)) and isfinite(x) for x in (lat, lon, age)) or age < 0:
                skipped += 1
                continue
            distance, _ = distance_bearing(area.latitude, area.longitude, lat, lon)
            if distance > area.radius_m:
                continue
            altitude = ac.get("alt_geom")
            altitude_basis = "geometric" if isinstance(altitude, (int, float)) else "barometric"
            if not isinstance(altitude, (int, float)):
                altitude = ac.get("alt_baro")
            altitude = (
                altitude * 0.3048 if isinstance(altitude, (int, float)) else (0 if altitude == "ground" else None)
            )
            batch.observations.append(
                ObservationIn(
                    source_id=self.id,
                    source_type="adsb",
                    object_type="aircraft",
                    track_id=ac.get("hex"),
                    latitude=lat,
                    longitude=lon,
                    altitude=altitude,
                    speed_mps=ac["gs"] * 0.514444 if isinstance(ac.get("gs"), (float, int)) else None,
                    heading_deg=ac.get("track"),
                    observed_at=response_at - timedelta(seconds=age),
                    measurement_method="third_party_reported_position",
                    raw=ac,
                    details={
                        "callsign": ac.get("flight", "").strip() or None,
                        "altitude_basis": altitude_basis,
                        "nac_p": ac.get("nac_p"),
                        "position_age_s": age,
                        "response_at": response_at.isoformat(),
                    },
                )
            )
        batch.details = {
            "returned_aircraft": len(data["ac"]),
            "skipped_without_valid_position_timestamp": skipped,
            "endpoint_radius_nm": radius_nm,
            "response_at": response_at.isoformat(),
        }
        return batch
