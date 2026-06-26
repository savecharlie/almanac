"""almanac — deterministic, verifiable ephemeris + geomagnetic computation.

Two pure-compute cores for the physical numbers language models hallucinate,
each checked against the authority that publishes it:

    from almanac.geomag import compute as field      # WMM2025 magnetic field
    from almanac.ephemeris import compute as sky      # JPL DE421 sky positions

`geomag` is pure standard library and reproduces all 100 of NOAA's own published
WMM2025 test values to the printed precision. `ephemeris` uses skyfield + the
public-domain JPL DE421 kernel and cross-checks against an independent engine to
~1 arcsecond.

Submodules are imported explicitly (importing ephemeris triggers the one-time
DE421 kernel fetch; importing geomag does not), so this package init stays inert.
"""

__version__ = "0.1.0"
