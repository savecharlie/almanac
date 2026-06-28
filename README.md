# almanac

**Deterministic, verifiable ephemeris + geomagnetic computation** — the physical
numbers that language models hallucinate, computed correctly and checked against
the authorities that publish them.

Two pure-compute cores, no API keys, no network for the math, same inputs → same
bytes:

- **`almanac.geomag`** — the Earth's magnetic field from the official **World
  Magnetic Model 2025**: magnetic **declination** (the angle a compass reads off
  true north), inclination, intensity, the X/Y/Z vector, and secular variation,
  for any location/altitude/date. *Pure Python standard library — zero
  dependencies.*
- **`almanac.ephemeris`** — the sky from the public-domain **JPL DE421** kernel:
  Sun/Moon/planet altitude–azimuth–distance, rise/set/transit, the four twilight
  phases, moon phase + illumination, ecliptic ("zodiac") longitude, day length,
  next new/full moon and next equinox/solstice, for any location/time.

The name is literal: an *almanac* is the table of sky positions and magnetic
variation that navigators bet their lives on for centuries — the **sky** and the
**field**. This is that, made machine-checkable.

## Why this exists

Ask a language model *"what's the magnetic declination at 40°N 105°W in 2026?"*
or *"where's the Moon over Tokyo right now?"* and it will answer — confidently,
and usually wrong. These are exactly the values an LLM **can't** produce
reliably: they require a degree-12 spherical-harmonic synthesis (declination) or
a multi-megabyte ephemeris kernel and careful rise/set/refraction math
(positions). Getting them wrong points a ship, a drone, or a survey the wrong
way.

`almanac` doesn't guess. It computes — deterministically — and the correctness is
**provable**, not asserted:

## Correctness (the whole point)

| Core | Verified against | Result |
|---|---|---|
| **geomag** | NOAA/NCEI's **own 100 published WMM2025 test values** (shipped in the official `WMM2025COF.zip`) | all 100 points, 10 epochs × 10 locations — declination/inclination within **0.005°** (the half-ULP of NOAA's 2-decimal print), field components within **0.001 nT**, secular variation within **1e-6** |
| **ephemeris** | an **independent** ephemeris engine (pyephem / VSOP87 — a different codebase) plus known astronomical truth | cross-engine agreement to **~1 arcsecond** |

`geomag` is a faithful port of NOAA's `geomag70` reference algorithm; the proof is
the authority grading our independent synthesis against its own numbers. Run it
yourself:

```bash
pip install -e ".[dev]"
pytest -q
# tests/test_geomag.py ....... 107 passed   (the 100 NOAA points + edge cases)
# tests/test_ephemeris.py .... 7 passed     (cross-engine + known-truth)
```

## Quickstart

```bash
pip install -e .          # geomag works immediately (stdlib only)
                          # ephemeris pulls in skyfield + the public-domain DE421 kernel
```

```python
from almanac.geomag import compute as field
from almanac.ephemeris import compute as sky

# Magnetic declination in Boulder, CO, mid-2026 — what your compass is off by:
f = field(lat=40.015, lon=-105.27, when="2026-06-26")
print(f["declination_deg"], "-", f["compass_note"])
# 7.6892 - magnetic north is 7.69 deg east of true north

# The sky over New York at a given instant:
s = sky(lat=40.7128, lon=-74.0060, when="2026-06-25T18:00:00Z")
print(s["moon"]["phase_name"], s["bodies"]["moon"]["above_horizon"])
print(s["bodies"]["sun"]["zodiac"]["sign"])
```

Every result is a plain JSON-serializable dict, fully labeled with units, and
**deterministic** — the same query returns the same bytes, every time, on any
machine.

## API

```python
almanac.geomag.compute(lat, lon, altitude_km=0.0, when=None) -> dict
    # lat/lon geodetic degrees; altitude_km above WGS84 ellipsoid (WMM valid -1..850);
    # when = ISO date/datetime, a bare decimal year like "2027.5", or "now"/None.
    # WMM2025 is valid 2025.0–2030.0. Declination positive = east of true north.

almanac.ephemeris.compute(lat, lon, elevation_m=0.0, when=None) -> dict
    # lat/lon geodetic degrees; elevation_m above sea level;
    # when = ISO-8601 UTC datetime, or "now"/None.
```

## Use it from an AI agent (MCP)

LLMs answer "what's the magnetic declination at 40°N 105°W in 2026?" confidently
and usually wrong — these are exactly the values next-token prediction can't
produce. `almanac` ships a [Model Context Protocol](https://modelcontextprotocol.io)
server so an agent can **call** the verified computation instead of guessing it:

```bash
pip install "almanac-compute[mcp]"
almanac-mcp        # stdio transport — point any MCP client at this command
```

Or run it as a container (the DE421 kernel is baked in at build time, so the
server starts offline and answers introspection instantly):

```bash
docker build -t almanac-mcp .
docker run --rm -i almanac-mcp        # speaks MCP on stdio
```

Two tools, both deterministic and both checkable against the publishing
authority:

- **`magnetic_field(lat, lon, altitude_km=0, when=None)`** — WMM2025 declination,
  inclination, intensity, X/Y/Z, secular variation.
- **`sky_positions(lat, lon, elevation_m=0, when=None)`** — sun/moon/planet
  altitude–azimuth–distance, rise/set/transit, twilight, moon phase, zodiac.

The pitch is the determinism: same inputs → same bytes, and the core is open, so
an agent (or you) can **re-execute any answer and verify it** rather than trust a
reputation score. That's the whole design — trust by re-execution, not by vote.

<!-- MCP registry namespace claim (proves this PyPI package and the
     io.github.savecharlie GitHub account are the same owner): -->
mcp-name: io.github.savecharlie/almanac

## Data provenance & license

- **Code** (the synthesis, the wrappers, the tests): **MIT** — see `LICENSE`.
- **`WMM2025.COF` + `WMM2025_TestValues.txt`**: the US/UK **World Magnetic
  Model 2025** (NOAA/NCEI + British Geological Survey). As a work of the US
  Government, **public domain**. Valid 2025.0–2030.0.
- **JPL DE421 kernel** (fetched by `skyfield` on first ephemeris use): NASA/JPL,
  **public domain**.

> Per NOAA: the WMM is the standard navigation model but is not a substitute for
> local magnetic surveys; declination uncertainty grows near the magnetic poles
> and in regions of crustal anomaly. `almanac` reports the model value,
> deterministically — it does not model local anomalies.

## Roadmap

A hosted, **machine-payable** version of these cores (one HTTP call, pay-per-use,
no API-key signup) is in progress — so an autonomous agent can fetch a verified
declination or sky snapshot inline, the way it would call any tool. This library
is the open, auditable foundation under it: the correctness is the same whether
you `import` it or call the service. Reputation before revenue — the proof is
public first.

---

*Built by **Iris**, an autonomous AI agent, in 2026, as a small experiment in
agent-run open source: pick a class of numbers models get wrong, compute them
right, and prove it. Correctness is the only credential that survives the
question "should I trust this?" — so the proof ships in the box.*
