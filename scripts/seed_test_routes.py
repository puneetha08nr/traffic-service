from __future__ import annotations

import asyncio
import os

import httpx


ROUTES = [
    (
        {"latitude": 37.7749, "longitude": -122.4194},
        {"latitude": 37.3382, "longitude": -121.8863},
        "sf_to_sj",
    ),
    (
        {"latitude": 40.7128, "longitude": -74.0060},
        {"latitude": 40.7580, "longitude": -73.9855},
        "nyc_midtown",
    ),
]


async def main() -> None:
    base_url = os.getenv("TRAFFIC_SERVICE_URL", "http://localhost:8000")
    async with httpx.AsyncClient(timeout=30.0) as client:
        for origin, dest, label in ROUTES:
            resp = await client.post(
                f"{base_url}/api/v1/traffic/query",
                json={"origin": origin, "destination": dest, "label": label},
            )
            resp.raise_for_status()
            print(resp.json())


if __name__ == "__main__":
    asyncio.run(main())

