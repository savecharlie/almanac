"""Proofs for the MCP wrapper: the tools register, return the verified cores'
output, are deterministic byte-for-byte, and fail cleanly on bad input.

The wrapper adds no math, so these guard the *surface*: that an agent calling
`magnetic_field` / `sky_positions` gets exactly what the cores compute, that
identical inputs give identical bytes (the whole pitch — re-executable truth),
and that invalid input raises rather than returning a plausible wrong number.

Skipped entirely if the optional `mcp` extra isn't installed, so the core
package's zero-dependency story is never coupled to this.
"""

import asyncio
import json

import pytest

pytest.importorskip("mcp", reason="install with: pip install 'almanac-compute[mcp]'")

from almanac.mcp_server import mcp  # noqa: E402


def _call(name, args):
    """Call a FastMCP tool and return the parsed JSON payload."""
    blocks = asyncio.run(mcp.call_tool(name, args))
    # FastMCP returns a list of content blocks; the structured result is JSON text.
    text = getattr(blocks[0], "text", None)
    assert text is not None, "tool returned no text content"
    return json.loads(text)


def test_tools_registered():
    tools = asyncio.run(mcp.list_tools())
    names = {t.name for t in tools}
    assert names == {"magnetic_field", "sky_positions"}
    # every tool description leads with what it is, not marketing fluff
    for t in tools:
        assert t.description and len(t.description) > 40


def test_magnetic_field_matches_core_and_is_deterministic():
    args = {"lat": 40.0, "lon": -105.0, "altitude_km": 0.0, "when": "2026.0"}
    a = _call("magnetic_field", args)
    b = _call("magnetic_field", args)
    # Boulder, CO 2026: declination ~7.6 deg east — sane and matches the core.
    assert abs(a["declination_deg"] - 7.5868) < 1e-6
    assert a["deterministic"] is True
    # the whole pitch: identical inputs -> identical bytes
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_sky_positions_shape_and_determinism():
    args = {"lat": 35.68, "lon": 139.69, "when": "2026-06-27T12:00:00Z"}
    a = _call("sky_positions", args)
    b = _call("sky_positions", args)
    assert "bodies" in a and "sun" in a["bodies"] and "moon" in a["bodies"]
    assert "altitude_deg" in a["bodies"]["sun"]
    assert a["deterministic"] is True
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_bad_input_errors_not_lies():
    # A stranger-agent must get an error, never a confident wrong number.
    with pytest.raises(Exception):
        _call("magnetic_field", {"lat": 999.0, "lon": 0.0})
