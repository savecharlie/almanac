"""
Deterministic ephemeris compute from the public-domain JPL DE421 kernel.

Given a location (lat, lon, optional elevation) and an instant (UTC), return a
clean, machine-readable snapshot of the sky: Sun, Moon and planets (alt/az +
distance + above-horizon), rise/set/transit times, the four twilight phases,
moon phase + illumination, the ecliptic ("zodiac") longitude of Sun and Moon,
day length, and the next new/full moon and next equinox/solstice.

Why an agent would pay a sliver for this instead of computing it itself:
accurate positions require a multi-MB JPL ephemeris kernel and the skyfield
machinery, and getting refraction / rise-set / twilight right is genuinely
error-prone. An LLM agent will hallucinate these. This module does not: it is
deterministic, reproducible, and built on the public-domain JPL DE421 kernel
(no Swiss-Ephemeris licensing friction). Zero marginal cost to serve.

Pure compute. No network, no LLM, no state. Same inputs -> same bytes.
"""

from __future__ import annotations

import math
import os
from datetime import datetime, timedelta, timezone

from skyfield.api import load, load_file, wgs84
from skyfield import almanac

# --- Load kernel + timescale ONCE (module import). A server reuses these. ---
_HERE = os.path.dirname(os.path.abspath(__file__))
_KERNEL = os.path.join(_HERE, "data", "de421.bsp")

_ts = load.timescale()
_eph = load_file(_KERNEL) if os.path.exists(_KERNEL) else load("de421.bsp")

_EARTH = _eph["earth"]
_SUN = _eph["sun"]
_MOON = _eph["moon"]

# de421 target names. Outer planets are only present as barycenters; for the
# distances/directions we report that difference is far below our precision.
_PLANETS = {
    "mercury": "mercury",
    "venus": "venus",
    "mars": "mars barycenter",
    "jupiter": "jupiter barycenter",
    "saturn": "saturn barycenter",
    "uranus": "uranus barycenter",
    "neptune": "neptune barycenter",
}

_ZODIAC = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]

_AU_KM = 149_597_870.7


def _iso(t) -> str:
    """skyfield Time -> ISO-8601 UTC string, seconds precision."""
    return t.utc_datetime().replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _zodiac_of(lon_deg: float) -> dict:
    lon_deg = lon_deg % 360.0
    idx = int(lon_deg // 30)
    return {
        "sign": _ZODIAC[idx],
        "degree_in_sign": round(lon_deg - idx * 30, 4),
        "ecliptic_longitude": round(lon_deg, 4),
    }


def _parse_when(when: str | None):
    """when: ISO-8601 (UTC assumed if naive) or None/'now'. -> skyfield Time."""
    if when is None or str(when).lower() == "now":
        dt = datetime.now(timezone.utc)
    else:
        s = str(when).strip().replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(timezone.utc)
    return _ts.from_datetime(dt), dt


def _body_state(observer, t, target):
    """Apparent alt/az/distance of a body as seen from observer at time t."""
    app = observer.at(t).observe(target).apparent()
    alt, az, dist = app.altaz("standard")  # standard atmospheric refraction
    # ecliptic longitude (geocentric apparent) for zodiac
    return {
        "altitude_deg": round(alt.degrees, 4),
        "azimuth_deg": round(az.degrees, 4),
        "above_horizon": bool(alt.degrees > 0),
        "distance_km": round(dist.km, 1),
        "distance_au": round(dist.au, 8),
    }


def _ecliptic_longitude(t, target) -> float:
    """Geocentric apparent ecliptic longitude (deg) — for zodiac sign."""
    lat, lon, _ = _EARTH.at(t).observe(target).apparent().frame_latlon(almanac.ecliptic_frame)
    return lon.degrees % 360.0


def _as_time_list(t):
    """Normalize a skyfield Time (scalar OR array) to a list of scalar Times."""
    shape = getattr(t, "shape", ())
    if shape == ():
        return [t]
    return [t[i] for i in range(len(t))]


def _flags(y, n):
    """Normalize a bool / bool-array companion to a length-n list."""
    if y is None:
        return [True] * n
    try:
        return [bool(y[i]) for i in range(n)]
    except (TypeError, IndexError):
        return [bool(y)] * n


def _events_in_window(observer, target, t0, t1):
    """Rise / set / transit (culmination) times within [t0, t1]."""
    out = {"rises": [], "sets": [], "transits": []}

    rt, ry = almanac.find_risings(observer, target, t0, t1)
    rt = _as_time_list(rt)
    for ti, up in zip(rt, _flags(ry, len(rt))):
        if up:
            out["rises"].append(_iso(ti))

    st, sy = almanac.find_settings(observer, target, t0, t1)
    st = _as_time_list(st)
    for ti, dn in zip(st, _flags(sy, len(st))):
        if dn:
            out["sets"].append(_iso(ti))

    for ti in _as_time_list(almanac.find_transits(observer, target, t0, t1)):
        out["transits"].append(_iso(ti))
    return out


def compute(lat: float, lon: float, elevation_m: float = 0.0, when: str | None = None) -> dict:
    """The full deterministic sky snapshot. Returns a JSON-serializable dict."""
    if not (-90.0 <= lat <= 90.0):
        raise ValueError("lat must be in [-90, 90]")
    if not (-180.0 <= lon <= 180.0):
        raise ValueError("lon must be in [-180, 180]")

    t, dt = _parse_when(when)
    topos = wgs84.latlon(lat, lon, elevation_m)
    observer = _EARTH + topos

    # Day window: local civil day approximated as [t-? , ...]. Use a 24h window
    # centered so "today's" rise/set/twilight are captured regardless of tz.
    day_start = datetime(dt.year, dt.month, dt.day, tzinfo=timezone.utc) - timedelta(hours=14)
    t0 = _ts.from_datetime(day_start)
    t1 = _ts.from_datetime(day_start + timedelta(hours=48))

    # --- bodies ---
    bodies = {"sun": _body_state(observer, t, _SUN), "moon": _body_state(observer, t, _MOON)}
    for name, key in _PLANETS.items():
        bodies[name] = _body_state(observer, t, _eph[key])

    # zodiac (ecliptic longitude) for sun & moon
    bodies["sun"]["zodiac"] = _zodiac_of(_ecliptic_longitude(t, _SUN))
    bodies["moon"]["zodiac"] = _zodiac_of(_ecliptic_longitude(t, _MOON))

    # --- sun rise/set/transit + day length ---
    sun_events = _events_in_window(observer, _SUN, t0, t1)
    moon_events = _events_in_window(observer, _MOON, t0, t1)

    # --- twilight phases (find the segments around the query instant) ---
    tw_f = almanac.dark_twilight_day(_eph, topos)
    tw_times, tw_codes = almanac.find_discrete(t0, t1, tw_f)
    twilight = []
    for ti, code in zip(tw_times, tw_codes):
        twilight.append({"time": _iso(ti), "entering": almanac.TWILIGHTS[int(code)]})

    # --- moon phase + illumination ---
    phase_angle = float(almanac.moon_phase(_eph, t).degrees)  # 0=new,90=FQ,180=full,270=LQ
    illum = float(almanac.fraction_illuminated(_eph, "moon", t))
    phase_name = _moon_phase_name(phase_angle)

    # next new & full moon (within ~40 days)
    mp_t0 = t
    mp_t1 = _ts.from_datetime(dt + timedelta(days=40))
    mp_times, mp_codes = almanac.find_discrete(mp_t0, mp_t1, almanac.moon_phases(_eph))
    next_phases = [{"phase": almanac.MOON_PHASES[int(c)], "time": _iso(ti)}
                   for ti, c in zip(mp_times, mp_codes)]

    # next equinox/solstice (within ~400 days)
    se_t1 = _ts.from_datetime(dt + timedelta(days=400))
    se_times, se_codes = almanac.find_discrete(t, se_t1, almanac.seasons(_eph))
    next_season = None
    if len(se_times):
        next_season = {"event": almanac.SEASONS[int(se_codes[0])], "time": _iso(se_times[0])}

    # day length from today's sun rise/set if both present
    day_length = _day_length(sun_events)

    return {
        "query": {
            "lat": lat, "lon": lon, "elevation_m": elevation_m,
            "time_utc": _iso(t), "input_when": when or "now",
        },
        "bodies": bodies,
        "sun": {**sun_events, "day_length_hours": day_length},
        "moon": {
            **moon_events,
            "phase_angle_deg": round(phase_angle, 3),
            "illuminated_fraction": round(illum, 5),
            "phase_name": phase_name,
            "next_phases": next_phases,
        },
        "twilight": twilight,
        "next_season_event": next_season,
        "kernel": "JPL DE421 (public domain)",
        "engine": "skyfield",
        "deterministic": True,
    }


def _moon_phase_name(angle: float) -> str:
    a = angle % 360.0
    names = [
        (0, "New Moon"), (45, "Waxing Crescent"), (90, "First Quarter"),
        (135, "Waxing Gibbous"), (180, "Full Moon"), (225, "Waning Gibbous"),
        (270, "Last Quarter"), (315, "Waning Crescent"), (360, "New Moon"),
    ]
    # nearest named boundary within 22.5deg, else the intermediate name
    for center, name in [(0, "New Moon"), (90, "First Quarter"),
                         (180, "Full Moon"), (270, "Last Quarter"), (360, "New Moon")]:
        if abs(a - center) <= 11.25:
            return name
    if a < 90:
        return "Waxing Crescent"
    if a < 180:
        return "Waxing Gibbous"
    if a < 270:
        return "Waning Gibbous"
    return "Waning Crescent"


def _day_length(sun_events: dict):
    rises, sets = sun_events["rises"], sun_events["sets"]
    if not rises or not sets:
        return None
    # pair the first rise with the next set after it
    r = datetime.fromisoformat(rises[0].replace("Z", "+00:00"))
    later_sets = [datetime.fromisoformat(s.replace("Z", "+00:00")) for s in sets]
    later_sets = [s for s in later_sets if s > r]
    if not later_sets:
        return None
    return round((later_sets[0] - r).total_seconds() / 3600.0, 3)


if __name__ == "__main__":
    import json
    # quick manual smoke
    print(json.dumps(compute(40.7128, -74.0060, 10, "2026-06-25T18:00:00Z"), indent=2))
