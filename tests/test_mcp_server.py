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
    """Call a tool and return the parsed JSON payload.

    mcp 1.x returns a bare list of content blocks; mcp 2.x returns a
    CallToolResult wrapping .content. Both carry the same JSON text, which is
    the only part the protocol actually specifies.
    """
    out = asyncio.run(mcp.call_tool(name, args))
    blocks = getattr(out, "content", None) or out
    if isinstance(blocks, tuple):          # 1.x returns (blocks, structured)
        blocks = blocks[0]
    text = getattr(blocks[0], "text", None)
    assert text is not None, "tool returned no text content"
    return json.loads(text)


def _wire_tools():
    """Every tool as a CLIENT sees it: serialised by alias, the way it goes
    down the pipe.

    ASSERT ON THE PROTOCOL, NOT ON THE SDK'S PYTHON SURFACE (Iris, Sep 11
    2026). The first draft of the annotation tests read `a.readOnlyHint`, which
    is correct under mcp 1.x and an AttributeError under 2.x, where the field is
    `read_only_hint` -- while the constructor accepts the camelCase alias and
    the WIRE form is `readOnlyHint` in both. The Python names were renamed; the
    protocol was not. Testing the attribute tested the SDK; testing the wire
    tests what an agent receives.
    """
    return [json.loads(t.model_dump_json(by_alias=True, exclude_none=True))
            for t in asyncio.run(mcp.list_tools())]


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


# ── safety annotations ──────────────────────────────────────────────────────
# WHY (Iris, Sep 11 2026, out of arXiv:2609.10962 -- a 24,135-server MCP
# registry census with an unrepaired probability sample).  Of 2,766 tools
# advertised by real deployed servers, 1,626 (58.8%) carry NO safety
# annotations, and the split is essentially bimodal at the server level: 72
# servers annotate every tool, 122 annotate none, and not one partial server
# was observed.  almanac was in the none half.
#
# These four hints are how an agent decides whether a tool is safe to call
# BEFORE calling it.  For a pair of pure computations that is free information
# and I was withholding it.  This test exists because the bimodality is the
# real risk: the day I add a third tool is the day almanac silently rejoins
# the 58.8%.

def test_every_tool_carries_all_four_safety_annotations():
    for t in _wire_tools():
        a = t.get("annotations")
        assert a, f"{t['name']} advertises no annotations at all"
        for hint in ("readOnlyHint", "destructiveHint",
                     "idempotentHint", "openWorldHint"):
            assert a.get(hint) is not None, f"{t['name']} omits {hint}"


def test_the_annotations_tell_the_truth_about_these_tools():
    """Both tools are pure functions over a bundled model and a bundled
    ephemeris kernel: no writes, no network, no external state.  An annotation
    that flattered the tool would be worse than none, so pin the values."""
    for t in _wire_tools():
        a = t["annotations"]
        assert a["readOnlyHint"] is True, t["name"]
        assert a["destructiveHint"] is False, t["name"]
        assert a["idempotentHint"] is True, t["name"]
        # Closed world: WMM2025 coefficients and DE421 ship in the package.
        # Nothing is fetched, so the answer does not depend on anything outside.
        assert a["openWorldHint"] is False, t["name"]


def test_annotations_survive_the_wire_encoding():
    """A hint the client never sees is not a hint.  Serialise the way the
    protocol does and read it back out of the JSON."""
    for wire in _wire_tools():
        assert "annotations" in wire, wire["name"]
        assert wire["annotations"]["readOnlyHint"] is True
        assert wire["annotations"]["destructiveHint"] is False
        assert wire["annotations"]["idempotentHint"] is True
        assert wire["annotations"]["openWorldHint"] is False
