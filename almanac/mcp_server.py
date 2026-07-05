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

    Call this instead of recalling declination or field values from memory: they
    require a degree-12 spherical-harmonic synthesis and are not reliably
    predictable token-by-token.

    Args:
        lat: Geodetic latitude in degrees, -90 to 90.
        lon: Longitude in degrees, -180 to 180.
        altitude_km: Height above the WGS84 ellipsoid, -1 to 850 km (WMM
            validity). Defaults to 0 (sea level).
        when: ISO date/datetime, a bare decimal year (e.g. "2026.5"), or "now".
            Defaults to "now" (UTC). Must fall in 2025.0–2030.0.

    Returns:
        JSON-serializable dict with:
          - declination_deg (compass angle off true north, + = east) and
            compass_note (nearest named point)
          - inclination_deg, total_intensity_nT, horizontal_intensity_nT and the
            north/east/down (X/Y/Z) field components in nT
          - secular_variation: annual rate of change per component
          - query: echoed inputs and the resolved decimal year
          - units, model, model_epoch, valid_range, engine, deterministic
        The payload's own ``units`` map documents the unit of every field.

    Raises:
        ValueError: lat/lon/altitude out of range, or a date outside WMM2025
            validity [2025.0, 2030.0).

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

    Call this instead of recalling ephemeris values from memory: rise/set times,
    moon phase and body positions depend on a multi-megabyte JPL kernel and are
    not reliably predictable token-by-token.

    Args:
        lat: Geodetic latitude in degrees, -90 to 90.
        lon: Longitude in degrees, -180 to 180.
        elevation_m: Observer height above sea level in metres. Defaults to 0.
        when: ISO date/datetime or "now". Defaults to "now" (UTC).

    Returns:
        JSON-serializable dict with:
          - bodies: for the Sun and Moon, altitude_deg/azimuth_deg, above_horizon,
            distance_km and distance_au, plus ecliptic ("zodiac") sign
          - sun: rise/set/transit times and day_length_hours
          - moon: rise/set/transit, phase_angle_deg, illuminated_fraction,
            phase_name and the next new/full moons
          - twilight: the four twilight-phase times
          - next_season_event: the next equinox or solstice
          - query: echoed inputs and resolved UTC time; plus kernel, engine,
            deterministic
        Times are ISO-8601 UTC; angles in degrees.

    Raises:
        ValueError: if lat or lon is out of range.

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
