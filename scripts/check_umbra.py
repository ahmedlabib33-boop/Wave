import asyncio
import json
from pathlib import Path
import httpx
from app.connectors.umbra import UmbraConnector
from app.schemas import Area


async def main():
    async with httpx.AsyncClient(timeout=20) as client:
        batch = await UmbraConnector().poll(client, Area())
    result = {"quality": batch.quality, "details": batch.details, "scene_count": len(batch.scenes)}
    Path("research/umbra-search.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
