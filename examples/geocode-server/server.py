"""Geocode MCP server — lab example (Nominatim → west,south,east,north bbox)."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("geocode-mcp")

NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_USER_AGENT = "GeocodeMCPServer"
TIMEOUT = 60

_PORT = int(os.getenv("MCP_PORT", "8000"))
mcp = FastMCP("Geocode", host="127.0.0.1", port=_PORT, stateless_http=True)


async def _http_get(
    url: str,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    async with httpx.AsyncClient(timeout=100, follow_redirects=True) as client:
        resp = await client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        return resp


@mcp.tool()
async def geocode_place(
    place_name: str,
    buffer_km: float = 0.0,
    limit: int = 5,
) -> str:
    """Convert a place name to a bounding box.

    Geocodes a place name (city, region, country, landmark, etc.) into a
    bounding box string in "west,south,east,north" format — the same format
    accepted by get_effis_burnt_areas and other tools.

    Uses the OpenStreetMap Nominatim API (free, no API key required).

    Args:
        place_name: Name of the place to geocode (e.g. "Greece",
                    "Athens", "Evia island", "Peloponnese").
        buffer_km:  Optional buffer in km to expand the bbox (default 0).
        limit:      Maximum number of candidate results to return (default 5).

    Returns:
        JSON with the top result's bbox string (ready to pass to other tools)
        and all candidate matches.
    """
    logger.info("Geocoding place: %s", place_name)

    try:
        resp = await _http_get(
            NOMINATIM_SEARCH_URL,
            params={
                "q": place_name,
                "format": "json",
                "limit": str(limit),
                "addressdetails": "1",
            },
            headers={"User-Agent": NOMINATIM_USER_AGENT},
        )
        results = resp.json()
    except Exception as exc:
        return json.dumps({"error": f"Geocoding failed: {exc}"})

    if not results:
        return json.dumps(
            {
                "error": f"No results found for '{place_name}'.",
                "place_name": place_name,
            }
        )

    buf = buffer_km / 111.0

    def _parse_result(r: dict) -> dict:
        bb = r.get("boundingbox", [])
        south, north, west, east = (
            float(bb[0]) - buf,
            float(bb[1]) + buf,
            float(bb[2]) - buf,
            float(bb[3]) + buf,
        )
        return {
            "display_name": r.get("display_name", ""),
            "bbox": f"{west:.4f},{south:.4f},{east:.4f},{north:.4f}",
            "bbox_array": [
                round(west, 4),
                round(south, 4),
                round(east, 4),
                round(north, 4),
            ],
            "lat": float(r.get("lat", 0)),
            "lon": float(r.get("lon", 0)),
            "osm_type": r.get("osm_type", ""),
            "class": r.get("class", ""),
            "type": r.get("type", ""),
        }

    parsed = [_parse_result(r) for r in results]

    return json.dumps(
        {
            "place_name": place_name,
            "top_result": parsed[0],
            "all_results": parsed,
            "total_results": len(parsed),
        }
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Geocode MCP server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="stdio for MCP clients (default); http for streamable-http deployment",
    )
    parser.add_argument("--port", type=int, default=_PORT, help="HTTP port (default from MCP_PORT or 8000)")
    args = parser.parse_args()
    if args.port != mcp.settings.port:
        mcp.settings.port = args.port
    if args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(transport="streamable-http")
