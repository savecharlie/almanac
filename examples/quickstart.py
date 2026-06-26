"""almanac quickstart — the sky and the field for one place and time.

    python examples/quickstart.py

geomag runs instantly (pure stdlib). ephemeris fetches the public-domain JPL
DE421 kernel on first run via skyfield, then is fast and offline thereafter.
"""

import os
import sys

# Run straight from a fresh clone without installing: put the repo root on the
# path. (After `pip install -e .` this is a no-op and the import just works.)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from almanac.geomag import compute as field
from almanac.ephemeris import compute as sky

PLACES = [
    ("Boulder, CO", 40.015, -105.27),
    ("London",      51.5074, -0.1278),
    ("Sydney",     -33.8688, 151.2093),
]
WHEN = "2026-06-26T12:00:00Z"

print(f"=== Magnetic field (WMM2025) @ {WHEN} ===")
for name, lat, lon in PLACES:
    f = field(lat, lon, when=WHEN)
    print(f"{name:14s} declination {f['declination_deg']:+7.2f} deg   "
          f"inclination {f['inclination_deg']:+6.2f} deg   "
          f"|F| {f['total_intensity_nT']:.0f} nT")
    print(f"{'':14s} -> {f['compass_note']}")

print(f"\n=== Sky over New York @ {WHEN} ===")
s = sky(40.7128, -74.0060, when=WHEN)
sun, moon = s["bodies"]["sun"], s["bodies"]["moon"]
print(f"Sun   alt {sun['altitude_deg']:+6.2f} deg  az {sun['azimuth_deg']:6.2f} deg  "
      f"(in {sun['zodiac']['sign']})")
print(f"Moon  alt {moon['altitude_deg']:+6.2f} deg  az {moon['azimuth_deg']:6.2f} deg  "
      f"{s['moon']['phase_name']} ({s['moon']['illuminated_fraction']*100:.0f}% lit)")
if s["sun"]["day_length_hours"]:
    print(f"Day length: {s['sun']['day_length_hours']:.2f} hours")
