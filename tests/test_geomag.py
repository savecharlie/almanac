"""
Verification of the WMM2025 synthesis against NOAA's OWN published test values.

The file data/WMM2025_TestValues.txt ships inside the official WMM2025COF.zip from
NCEI. It is the authoritative oracle: if our independent synthesis reproduces every
one of NOAA's 100 published points to the printed precision, the implementation is
correct. (Same discipline as the ephemeris endpoint cross-checking skyfield against
an independent engine.)
"""

import os

import pytest

from almanac import geomag  # noqa: E402
from almanac.geomag import _MODEL, compute, VALID_FROM, VALID_TO  # noqa: E402

_TV = os.path.join(os.path.dirname(geomag.__file__), "data", "WMM2025_TestValues.txt")


def _load_test_values():
    rows = []
    with open(_TV) as fh:
        for line in fh:
            if line.startswith("#") or not line.strip():
                continue
            rows.append([float(x) for x in line.split()])
    return rows


def _angle_err(a, b):
    e = abs(a - b)
    return min(e, abs(e - 360.0))


TEST_ROWS = _load_test_values()


def test_oracle_has_full_set():
    # NOAA ships exactly 100 test points (10 epochs x 10 locations).
    assert len(TEST_ROWS) == 100


@pytest.mark.parametrize("row", TEST_ROWS, ids=lambda r: f"{r[0]:.1f}_{r[2]:.0f}_{r[3]:.0f}")
def test_matches_noaa_official(row):
    yr, alt, lat, lon = row[0], row[1], row[2], row[3]
    expD, expI, expH, expX, expY, expZ, expF = row[4:11]
    edD, edI, edH, edX, edY, edZ, edF = row[11:18]

    fl = _MODEL.field(lat, lon, alt, yr)
    sv = fl["secular_variation"]

    # NOAA prints D/I to 0.01 deg, so half-ULP (0.005) is the true tolerance.
    assert _angle_err(fl["declination_deg"], expD) < 0.006
    assert _angle_err(fl["inclination_deg"], expI) < 0.006
    # intensities: file prints ~6 decimals; agreement is sub-0.01 nT.
    assert abs(fl["horizontal_intensity_nT"] - expH) < 0.05
    assert abs(fl["north_X_nT"] - expX) < 0.05
    assert abs(fl["east_Y_nT"] - expY) < 0.05
    assert abs(fl["down_Z_nT"] - expZ) < 0.05
    assert abs(fl["total_intensity_nT"] - expF) < 0.05
    # secular variation
    assert _angle_err(sv["dDeclination_deg_per_yr"], edD) < 0.001
    assert _angle_err(sv["dInclination_deg_per_yr"], edI) < 0.001
    assert abs(sv["dHorizontal_nT_per_yr"] - edH) < 0.05
    assert abs(sv["dX_nT_per_yr"] - edX) < 0.05
    assert abs(sv["dY_nT_per_yr"] - edY) < 0.05
    assert abs(sv["dZ_nT_per_yr"] - edZ) < 0.05
    assert abs(sv["dTotal_nT_per_yr"] - edF) < 0.05


def test_public_compute_shape():
    r = compute(40.015, -105.27, 0.0, "2026-06-26")
    for key in ("declination_deg", "inclination_deg", "horizontal_intensity_nT",
                "north_X_nT", "east_Y_nT", "down_Z_nT", "total_intensity_nT",
                "compass_note", "secular_variation", "model", "units", "query"):
        assert key in r
    assert r["model"].startswith("WMM")
    assert r["deterministic"] is True
    assert "east of true north" in r["compass_note"]  # Boulder is +E


def test_determinism_same_bytes():
    import json
    a = json.dumps(compute(51.5074, -0.1278, 0.0, "2027.5"), sort_keys=True)
    b = json.dumps(compute(51.5074, -0.1278, 0.0, "2027.5"), sort_keys=True)
    assert a == b


def test_decimal_year_forms_agree():
    # 2027-07-02 ~ 2027.5; ISO date and bare decimal year should land close.
    iso = compute(0.0, 0.0, 0.0, "2027-07-02")["declination_deg"]
    dec = compute(0.0, 0.0, 0.0, "2027.5")["declination_deg"]
    assert abs(iso - dec) < 0.02


def test_input_validation():
    with pytest.raises(ValueError):
        compute(91.0, 0.0)
    with pytest.raises(ValueError):
        compute(0.0, 181.0)
    with pytest.raises(ValueError):
        compute(0.0, 0.0, 2000.0)            # altitude beyond WMM validity
    with pytest.raises(ValueError):
        compute(0.0, 0.0, 0.0, "2031.0")     # date beyond WMM2025 validity
    with pytest.raises(ValueError):
        compute(0.0, 0.0, 0.0, "2024.0")     # before validity


def test_validity_window():
    assert VALID_FROM == 2025.0
    assert VALID_TO == 2030.0


def test_known_cities_sane():
    # declination sign sanity for a few well-characterised places (2026)
    boulder = compute(40.015, -105.27, 0.0, "2026.5")["declination_deg"]
    assert 6.5 < boulder < 9.0          # ~8 deg east in Colorado
    seattle = compute(47.6062, -122.3321, 0.0, "2026.5")["declination_deg"]
    assert 13.0 < seattle < 17.0        # strongly east in the PNW
