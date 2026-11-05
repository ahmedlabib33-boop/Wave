"""Real network checks. No synthetic detections are written to the application DB."""

import os
import httpx
import pytest
from app.connectors.adsb import ADSBConnector
from app.connectors.environment import CommunityConnector
from app.connectors.satellite import ASFConnector, CopernicusConnector
from app.schemas import Area

pytestmark = pytest.mark.skipif(
    os.getenv("LIVE_TESTS") != "1", reason="Set LIVE_TESTS=1 to call public external services"
)


@pytest.mark.parametrize("connector", [ADSBConnector(), ASFConnector(), CopernicusConnector(), CommunityConnector()])
async def test_real_cairo_provider(connector):
    async with httpx.AsyncClient(timeout=30) as client:
        batch = await connector.poll(client, Area())
    assert isinstance(batch.observations, list) and isinstance(batch.scenes, list)
    if connector.id in ("asf", "copernicus"):
        assert batch.scenes
        assert all(s["acquired_at"].tzinfo is not None for s in batch.scenes)
