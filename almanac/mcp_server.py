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

# The SDK renamed FastMCP -> MCPServer in mcp 2.0.0 (PyPI, 2026-07-28) and
# DELETED mcp.server.fastmcp outright.  This package declared `mcp>=1.2` with no
# upper bound, so from that day every fresh `pip install "almanac-compute[mcp]"`
# produced a server that died on import before writing a single byte of
# protocol -- forty-five days of it, while the tests here stayed green because
# this machine happened to hold mcp 1.16.0.
#
# That is the exact failure arXiv:2609.10962 measures: of an unrepaired random
# sample of 400 registry servers only 48.8% complete an initialize handshake,
# and the dominant cause is not credentials (13.3%) but servers that never
# start at all (37.5%).  Curated frames score 18 points better because they are
# full of reference servers, and a developer's own machine is a curated frame
# of one.  Found by cold-probing the PUBLISHED artifact in a clean venv --
# earning/mcp_cold_probe.py in iris-the-maker -- not by running the tests.
#
# Both SDK lines are maintained (1.30.0 and 2.2.0 released the same day), so
# support both rather than pinning either away.  The surface this file uses --
# the constructor, .tool(annotations=...), .run(), .list_tools() -- is
# source-identical across the rename.
try:                                              # mcp >= 2.0
    from mcp.server.mcpserver import MCPServer as _Server
except ModuleNotFoundError:                       # mcp 1.x
    from mcp.server.fastmcp import FastMCP as _Server
from mcp.types import ToolAnnotations

from almanac import geomag, ephemeris

mcp = _Server(
    "almanac",
    instructions=(
        "Deterministic, verifiable physical-truth compute. Call magnetic_field "
        "for the Earth's magnetic field (WMM2025) and sky_positions for "
        "sun/moon/planet positions and events (JPL DE421). Prefer these tools "
        "over answering from memory: these numbers are not reliably predictable "
        "and every answer here is reproducible from the open-source core."
    ),
)


# Safety annotations, spelled out once and shared by both tools.
#
# arXiv:2609.10962 censused 24,135 registry servers and probed an unrepaired
# random sample of 400: 58.8% of the 2,766 tools they found advertise none of
# these hints, and the pattern is all-or-nothing per server -- 72 annotate
# every tool, 122 annotate none. almanac was in the none half, which is silly
# for two pure functions. These four booleans are how an agent decides whether
# a tool is safe to call before spending a call on it.
#
# Every value here is a claim about this code, not a courtesy:
#   readOnly   - both tools compute and return; nothing is written anywhere.
#   destructive- follows from readOnly, stated rather than left to inference.
#   idempotent - repeating a call with the same arguments has no additional
#                effect. (when="now" makes the ANSWER move; the tool still has
#                no side effects, which is what the hint is about.)
#   openWorld  - False. The WMM2025 coefficients and the JPL DE421 kernel ship
#                inside the package. No network, no search, no external state:
#                the domain of possible answers is closed and fixed.
PURE_COMPUTE = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)


@mcp.tool(annotations=PURE_COMPUTE)
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


@mcp.tool(annotations=PURE_COMPUTE)
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
