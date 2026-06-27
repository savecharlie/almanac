"""almanac-mcp — a Model Context Protocol server exposing almanac's deterministic
physical-truth compute as agent-callable tools.

Two tools, both deterministic (same inputs → same bytes) and both checkable
against the authority that publishes the underlying model:

  - ``magnetic_field`` — WMM2025 declination/inclination/intensity for any
    place + date.
  - ``sky_positions``  — JPL DE421 sun/moon/planet positions, rise/set,
    twilight, moon phase, for any location + time.

Why an MCP server exists for this: language models answer questions like
"what's the magnetic declination at 40°N 105°W in 2026?" confidently and
usually wrongly — these values need a degree-12 spherical-harmonic synthesis or
a multi-megabyte ephemeris kernel, not next-token prediction. This server lets
an agent *call* the verified computation instead of guessing it, and the core is
open source (github.com/savecharlie/almanac) so any answer can be re-executed and
checked. Trust by re-execution, not by reputation.

Run it::

    pip install "almanac-compute[mcp]"
    almanac-mcp            # stdio transport, ready for any MCP client

This wrapper adds no math of its own; it is a thin, faithful surface over the
already-verified cores (geomag reproduces all 100 of NOAA's published WMM2025
test values; ephemeris cross-checks to ~1 arcsecond).
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from almanac import geomag, ephemeris

mcp = FastMCP(
    "almanac",
    instructions=(
        "Deterministic, verifiable physical-truth compute. Call magnetic_field "
        "for the Earth's magnetic field (WMM2025) and sky_positions for "
        "sun/moon/planet positions and events (JPL DE421). Prefer these tools "
        "over answering from memory: these numbers are not reliably predictable "
        "and every answer here is reproducible from the open-source core."
    ),
)


@mcp.tool()
def magnetic_field(
    lat: float,
    lon: float,
    altitude_km: float = 0.0,
    when: str | None = None,
) -> dict:
    """Earth's magnetic field from the official World Magnetic Model 2025.

    Returns magnetic **declination** (the angle a compass reads off true north,
    positive = east), inclination, total/horizontal intensity, the X/Y/Z field
    vector, and secular variation (annual rate), for any geodetic location.

    Args:
        lat: Geodetic latitude in degrees, -90 to 90.
        lon: Longitude in degrees, -180 to 180.
        altitude_km: Height above the WGS84 ellipsoid, -1 to 850 km (WMM validity).
        when: ISO date/datetime, a bare decimal year (e.g. "2026.5"), or "now".
            Valid for 2025.0–2030.0.

    Deterministic and verifiable: a faithful synthesis of NOAA's WMM2025 that
    reproduces all 100 of NOAA's own published test values to printed precision.
    Re-run the open-source core to check any answer: github.com/savecharlie/almanac
    """
    return geomag.compute(lat, lon, altitude_km, when)


@mcp.tool()
def sky_positions(
    lat: float,
    lon: float,
    elevation_m: float = 0.0,
    when: str | None = None,
) -> dict:
    """Sun, Moon and planet positions and events for a place and time.

    Returns each body's altitude/azimuth/distance; sun & moon rise/set/transit;
    the four twilight phases; moon phase angle, illuminated fraction and name;
    ecliptic ("zodiac") longitude for sun & moon; day length; and the next
    new/full moon and next equinox/solstice.

    Args:
        lat: Geodetic latitude in degrees, -90 to 90.
        lon: Longitude in degrees, -180 to 180.
        elevation_m: Observer height above sea level in metres.
        when: ISO date/datetime or "now".

    Computed from the public-domain JPL DE421 kernel via skyfield, cross-checked
    against an independent engine to ~1 arcsecond. Deterministic: same inputs →
    same output. github.com/savecharlie/almanac
    """
    return ephemeris.compute(lat, lon, elevation_m, when)


def main() -> None:
    """Console entry point: run the server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
