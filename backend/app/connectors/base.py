import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
import httpx
from ..schemas import Area, ObservationIn


class AccessBlocked(Exception):
    pass


class RateLimited(Exception):
    def __init__(self, seconds=60):
        self.seconds = seconds
        super().__init__(f"Provider rate limit; retry after {seconds}s")


@dataclass
class Batch:
    observations: list[ObservationIn] = field(default_factory=list)
    scenes: list[dict] = field(default_factory=list)
    quality: str = "Provider response; measurement accuracy not independently validated"
    details: dict = field(default_factory=dict)


class Connector:
    id = ""
    interval = 60
    credential = None

    async def poll(self, client: httpx.AsyncClient, area: Area) -> Batch:
        raise NotImplementedError


async def request(client, url, params=None, headers=None):
    for attempt in range(3):
        try:
            response = await client.get(url, params=params, headers=headers, follow_redirects=False)
        except httpx.RequestError:
            if attempt == 2:
                raise RuntimeError("Provider connection or timeout failure") from None
            await asyncio.sleep(0.3 * 2**attempt)
            continue
        if response.status_code == 429:
            try:
                delay = max(1, min(86400, int(response.headers.get("Retry-After", "60"))))
            except ValueError:
                delay = 60
            raise RateLimited(delay)
        if response.status_code in (401, 403):
            raise AccessBlocked(f"Provider returned HTTP {response.status_code}; check account and access conditions")
        if response.status_code >= 500 and attempt < 2:
            await asyncio.sleep(0.3 * 2**attempt)
            continue
        if response.status_code != 200:
            raise RuntimeError(f"Provider returned HTTP {response.status_code}")
        return response


def parse_time(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Provider timestamp has no timezone")
    return parsed.astimezone(timezone.utc)
