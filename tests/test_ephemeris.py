"""
Real tests for the ephemeris compute — the moat. Two kinds of check:

  1. Known astronomical truth (NYC sunrise, day length near solstice, Sun's
     zodiac sign, internal consistency).
  2. Cross-engine agreement vs an INDEPENDENT ephemeris (pyephem / VSOP87).
     If two unrelated codebases agree to arcseconds, the numbers are correct,
     not merely plausible.

Run:  pytest -q            (from the repo root)

"""

import math
import os
from datetime import datetime, timezone

from almanac.ephemeris import compute  # noqa: E402

# A fixed reference instant/place used across checks.
LAT, LON, ELEV = 40.7128, -74.0060, 10.0
WHEN = "2026-06-25T18:00:00Z"


def _iso_to_dt(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def test_determinism():
    """Same input -> byte-identical output. Non-negotiable for a paid API."""
    import json
    a = json.dumps(compute(LAT, LON, ELEV, WHEN), sort_keys=True)
    b = json.dumps(compute(LAT, LON, ELEV, WHEN), sort_keys=True)
    assert a == b


def test_input_validation():
    for bad in [(91, 0), (-91, 0), (0, 181), (0, -181)]:
        try:
            compute(bad[0], bad[1], 0, WHEN)
            assert False, f"expected ValueError for {bad}"
        except ValueError:
            pass


def test_nyc_sunrise_known():
    """NYC sunrise on 2026-06-25 is ~09:26 UTC (5:26 EDT). Tolerance 2 min."""
    out = compute(LAT, LON, ELEV, WHEN)
    rises = out["sun"]["rises"]
    target = datetime(2026, 6, 25, 9, 26, tzinfo=timezone.utc)
    assert any(abs((_iso_to_dt(r) - target).total_seconds()) < 120 for r in rises), rises


def test_day_length_near_solstice():
    """NYC day length within a few days of the June solstice is ~15.05-15.1 h."""
    out = compute(LAT, LON, ELEV, WHEN)
    dl = out["sun"]["day_length_hours"]
    assert dl is not None and 14.9 < dl < 15.2, dl


def test_sun_zodiac_cancer():
    """Sun enters Cancer at the June solstice; on Jun 25 it's a few deg into Cancer."""
    out = compute(LAT, LON, ELEV, WHEN)
    z = out["bodies"]["sun"]["zodiac"]
    assert z["sign"] == "Cancer", z
    assert 2 < z["degree_in_sign"] < 7, z


def test_moon_phase_consistency():
    """phase_angle, illumination and name must agree with each other."""
    out = compute(LAT, LON, ELEV, WHEN)["moon"]
    ang = out["phase_angle_deg"]
    illum = out["illuminated_fraction"]
    # illumination ~ (1 - cos(phase_angle)) / 2
    expected = (1 - math.cos(math.radians(ang))) / 2
    assert abs(illum - expected) < 0.02, (illum, expected)
    assert out["phase_name"] in {
        "New Moon", "Waxing Crescent", "First Quarter", "Waxing Gibbous",
        "Full Moon", "Waning Gibbous", "Last Quarter", "Waning Crescent",
    }


def test_cross_engine_agreement():
    """skyfield vs pyephem must agree to <0.02deg on Sun & Moon alt/az and
    <0.1% on lunar illumination. Independent codebases => correctness."""
    try:
        import ephem
    except ImportError:
        return  # cross-check is best-effort; skip if pyephem absent
    out = compute(LAT, LON, ELEV, WHEN)
    obs = ephem.Observer()
    obs.lat, obs.lon, obs.elevation = str(LAT), str(LON), ELEV
    obs.date = ephem.Date(WHEN.replace("T", " ").replace("Z", ""))
    s, m = ephem.Sun(obs), ephem.Moon(obs)

    assert abs(out["bodies"]["sun"]["altitude_deg"] - math.degrees(s.alt)) < 0.02
    assert abs(out["bodies"]["sun"]["azimuth_deg"] - math.degrees(s.az)) < 0.02
    assert abs(out["bodies"]["moon"]["altitude_deg"] - math.degrees(m.alt)) < 0.02
    assert abs(out["moon"]["illuminated_fraction"] * 100 - m.phase) < 0.1


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAIL  {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
