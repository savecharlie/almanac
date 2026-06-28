# syntax=docker/dockerfile:1
#
# almanac-mcp — deterministic, verifiable ephemeris + geomagnetic compute,
# served as a Model Context Protocol (MCP) server over stdio.
#
#   docker build -t almanac-mcp .
#   docker run --rm -i almanac-mcp      # speaks MCP on stdio; ready for any client
#
# Two tools, both deterministic (same inputs -> same bytes) and both checkable
# against the authority that publishes the underlying model:
#   magnetic_field  — WMM2025 declination/inclination/intensity (vs NOAA)
#   sky_positions   — JPL DE421 sun/moon/planet positions & events (~1 arcsec)
#
# Trust by re-execution: the core is open (github.com/savecharlie/almanac), so
# any answer this server gives can be reproduced and checked.

FROM python:3.12-slim

WORKDIR /app

# Install the package + the MCP extra from source — the same code in this repo,
# so the running server is exactly what's auditable here (no drift from a release).
COPY . /app
RUN pip install --no-cache-dir ".[mcp]"

# Bake the public-domain JPL DE421 kernel (~16 MB) into the image. The ephemeris
# core loads it at import; caching it here means the server starts OFFLINE and
# answers introspection (tools/list) instantly, with no network at runtime.
# (skyfield's loader resolves a bare "de421.bsp" from the working directory.)
RUN python -c "from skyfield.api import load; load('de421.bsp'); print('DE421 cached')"

# Prove the server imports with the network OFF — this fails the build loudly if
# the kernel weren't actually baked in. The build itself re-executes the claim.
RUN --network=none python -c "import almanac.mcp_server; print('offline import OK — MCP server ready')"

# stdio is the standard MCP transport; clients spawn this and speak JSON-RPC.
ENTRYPOINT ["almanac-mcp"]
