"""
Deterministic geomagnetic field from the World Magnetic Model 2025.

Given a location (geodetic lat, lon, altitude above the WGS84 ellipsoid) and a
date, return the Earth's main magnetic field from the official **World Magnetic
Model 2025** (WMM2025, valid 2025.0-2030.0): magnetic **declination** (the angle
between true north and magnetic north — what a compass actually reads),
inclination (dip), horizontal intensity H, the vector components X/Y/Z, total
intensity F, and the secular variation (annual rate of change) of each.

Why an agent would pay a sliver for this instead of computing it itself:
the WMM is a degree-12 spherical-harmonic model. Getting it right means parsing
the Gauss coefficients, the Schmidt semi-normalized associated Legendre
recurrence, the geodetic->geocentric conversion, and the back-rotation of the
field vector — all of which an LLM hallucinates badly (declination is the single
most-asked-for and most-mis-stated geophysical number in navigation). This
module does not hallucinate: it is a faithful port of the NOAA `geomag70`
reference algorithm, built on the public-domain WMM2025 coefficient file, and is
**verified against NOAA's own published test values** (see tests/). Magnetic
declination is what aircraft, ships, drones, surveyors and compass apps correct
by; a wrong value points you the wrong way.

Pure compute. No network, no LLM, no state. Same inputs -> same bytes.
Zero marginal cost to serve.

Reference algorithm: NOAA/NCEI WMM `geomag70` (public domain), via Christopher
Weiss's faithful Python transcription of the same. Coefficients: WMM2025.COF
(US/UK World Magnetic Model 2025, public domain).
"""

from __future__ import annotations

import math
import os
from datetime import datetime, timezone

_HERE = os.path.dirname(os.path.abspath(__file__))
_COF = os.path.join(_HERE, "data", "WMM2025.COF")

# WGS84 ellipsoid + geomagnetic reference radius (km), per the WMM definition.
_A = 6378.137            # WGS84 semi-major axis
_B = 6356.7523142        # WGS84 semi-minor axis
_RE = 6371.2             # geomagnetic reference radius
_A2, _B2 = _A * _A, _B * _B
_C2 = _A2 - _B2
_A4, _B4 = _A2 * _A2, _B2 * _B2
_C4 = _A4 - _B4

_MAXORD = 12             # WMM is degree/order 12


class _WMM:
    """Loads a WMM .COF file and synthesizes the field at a point/time.

    The Schmidt semi-normalization is folded into the Gauss coefficients at load
    time (the classic geomag70 trick), so the per-point Legendre recurrence works
    on *unnormalized* polynomials. The field is linear in the coefficients and the
    coefficients are linear in time, so the secular variation (d/dt of the vector
    components) is exactly the same synthesis run with the rate coefficients.
    """

    def __init__(self, cof_path: str = _COF):
        self.epoch = None
        self.model = None
        self.modeldate = None
        # c[m][n] = g (and h packed at c[n][m-1]); cd = secular-variation rates.
        n13 = _MAXORD + 1
        self.c = [[0.0] * (n13 + 1) for _ in range(n13 + 1)]
        self.cd = [[0.0] * (n13 + 1) for _ in range(n13 + 1)]
        self.k = [[0.0] * (n13) for _ in range(n13)]
        self.fn = [float(n) + 1.0 for n in range(n13 + 1)]   # fn[n] = n+1
        self.fm = [float(m) for m in range(n13 + 1)]          # fm[m] = m

        with open(cof_path) as fh:
            for line in fh:
                vals = line.strip().split()
                if len(vals) == 3:
                    self.epoch = float(vals[0])
                    self.model = vals[1]
                    self.modeldate = vals[2]
                elif len(vals) == 6:
                    n = int(float(vals[0]))
                    m = int(float(vals[1]))
                    gnm, hnm, dgnm, dhnm = (float(v) for v in vals[2:6])
                    if m <= n:
                        self.c[m][n] = gnm
                        self.cd[m][n] = dgnm
                        if m != 0:
                            self.c[n][m - 1] = hnm
                            self.cd[n][m - 1] = dhnm

        if self.epoch is None:
            raise ValueError(f"no WMM epoch line found in {cof_path}")

        # --- Schmidt-normalize: fold snorm into the coefficients; build k[m][n] ---
        snorm = [[0.0] * (n13) for _ in range(n13)]
        snorm[0][0] = 1.0
        self.k[1][1] = 0.0
        for n in range(1, _MAXORD + 1):
            snorm[0][n] = snorm[0][n - 1] * (2.0 * n - 1) / n
            j = 2.0
            m = 0
            D2 = (n - m + 1)
            while D2 > 0:
                self.k[m][n] = (((n - 1) * (n - 1)) - (m * m)) / ((2.0 * n - 1) * (2.0 * n - 3.0))
                if m > 0:
                    flnmj = ((n - m + 1.0) * j) / (n + m)
                    snorm[m][n] = snorm[m - 1][n] * math.sqrt(flnmj)
                    j = 1.0
                    self.c[n][m - 1] *= snorm[m][n]
                    self.cd[n][m - 1] *= snorm[m][n]
                self.c[m][n] *= snorm[m][n]
                self.cd[m][n] *= snorm[m][n]
                D2 -= 1
                m += 1

    # ------------------------------------------------------------------
    def _components(self, glat: float, glon: float, alt_km: float, dec_year: float):
        """Return (X, Y, Z, dX, dY, dZ) in nT and nT/yr (geodetic frame)."""
        dt = dec_year - self.epoch
        rlat = math.radians(glat)
        rlon = math.radians(glon)
        srlon, crlon = math.sin(rlon), math.cos(rlon)
        srlat, crlat = math.sin(rlat), math.cos(rlat)
        srlat2, crlat2 = srlat * srlat, crlat * crlat

        # --- geodetic -> geocentric spherical (colatitude theta, radius r) ---
        q = math.sqrt(_A2 - _C2 * srlat2)
        q1 = alt_km * q
        q2 = ((q1 + _A2) / (q1 + _B2)) ** 2
        ct = srlat / math.sqrt(q2 * crlat2 + srlat2)          # cos(colatitude)
        st = math.sqrt(1.0 - ct * ct)                          # sin(colatitude)
        r = math.sqrt(alt_km * alt_km + 2.0 * q1 + (_A4 - _C4 * srlat2) / (q * q))
        d = math.sqrt(_A2 * crlat2 + _B2 * srlat2)
        ca = (alt_km + d) / r                                  # rotation cos
        sa = _C2 * crlat * srlat / (r * d)                     # rotation sin

        # --- longitude harmonics sp[m]=sin(m*lon), cp[m]=cos(m*lon) ---
        sp = [0.0] * (_MAXORD + 1)
        cp = [0.0] * (_MAXORD + 1)
        sp[0], cp[0] = 0.0, 1.0
        sp[1], cp[1] = srlon, crlon
        for m in range(2, _MAXORD + 1):
            sp[m] = sp[1] * cp[m - 1] + cp[1] * sp[m - 1]
            cp[m] = cp[1] * cp[m - 1] - sp[1] * sp[m - 1]

        # --- Legendre p[m][n], dp[m][n] (unnormalized; snorm folded in coeffs) ---
        n13 = _MAXORD + 1
        p = [[0.0] * (n13 + 1) for _ in range(n13 + 1)]
        dp = [[0.0] * (n13 + 1) for _ in range(n13 + 1)]
        pp = [0.0] * (n13 + 1)
        p[0][0] = 1.0
        pp[0] = 1.0

        aor = _RE / r
        ar = aor * aor
        # field accumulators (bt=theta, bp=phi, br=radial) + secular-variation twins
        bt = bp = br = bpp = 0.0
        btd = bpd = brd = bppd = 0.0

        for n in range(1, _MAXORD + 1):
            ar *= aor
            m = 0
            D4 = n + 1
            while D4 > 0:
                # Legendre recurrence
                if n == m:
                    p[m][n] = st * p[m - 1][n - 1]
                    dp[m][n] = st * dp[m - 1][n - 1] + ct * p[m - 1][n - 1]
                elif n == 1 and m == 0:
                    p[m][n] = ct * p[m][n - 1]
                    dp[m][n] = ct * dp[m][n - 1] - st * p[m][n - 1]
                elif n > 1 and n != m:
                    if m > n - 2:
                        p[m][n - 2] = 0.0
                        dp[m][n - 2] = 0.0
                    p[m][n] = ct * p[m][n - 1] - self.k[m][n] * p[m][n - 2]
                    dp[m][n] = ct * dp[m][n - 1] - st * p[m][n - 1] - self.k[m][n] * dp[m][n - 2]

                # time-adjusted (field) and rate (secular-variation) coefficients
                tc = self.c[m][n] + dt * self.cd[m][n]
                td = self.cd[m][n]
                if m == 0:
                    temp1, temp2 = tc * cp[m], tc * sp[m]
                    temp1d, temp2d = td * cp[m], td * sp[m]
                else:
                    tch = self.c[n][m - 1] + dt * self.cd[n][m - 1]
                    tdh = self.cd[n][m - 1]
                    temp1 = tc * cp[m] + tch * sp[m]
                    temp2 = tc * sp[m] - tch * cp[m]
                    temp1d = td * cp[m] + tdh * sp[m]
                    temp2d = td * sp[m] - tdh * cp[m]

                par = ar * p[m][n]
                bt -= ar * temp1 * dp[m][n]
                bp += self.fm[m] * temp2 * par
                br += self.fn[n] * temp1 * par
                btd -= ar * temp1d * dp[m][n]
                bpd += self.fm[m] * temp2d * par
                brd += self.fn[n] * temp1d * par

                # geographic-pole special case (st == 0): use pp recurrence
                if st == 0.0 and m == 1:
                    if n == 1:
                        pp[n] = pp[n - 1]
                    else:
                        pp[n] = ct * pp[n - 1] - self.k[m][n] * pp[n - 2]
                    parp = ar * pp[n]
                    bpp += self.fm[m] * temp2 * parp
                    bppd += self.fm[m] * temp2d * parp

                D4 -= 1
                m += 1

        if st == 0.0:
            bp = bpp
            bpd = bppd
        else:
            bp /= st
            bpd /= st

        # rotate spherical (bt, bp, br) -> geodetic (X north, Y east, Z down)
        bx = -bt * ca - br * sa
        by = bp
        bz = bt * sa - br * ca
        dbx = -btd * ca - brd * sa
        dby = bpd
        dbz = btd * sa - brd * ca
        return bx, by, bz, dbx, dby, dbz

    # ------------------------------------------------------------------
    def field(self, glat: float, glon: float, alt_km: float, dec_year: float) -> dict:
        x, y, z, dx, dy, dz = self._components(glat, glon, alt_km, dec_year)
        h = math.hypot(x, y)
        f = math.sqrt(h * h + z * z)
        dec = math.degrees(math.atan2(y, x))
        inc = math.degrees(math.atan2(z, h))
        # analytic secular variation of the derived scalars
        dh = (x * dx + y * dy) / h if h else 0.0
        df = (x * dx + y * dy + z * dz) / f if f else 0.0
        ddec = math.degrees((x * dy - y * dx) / (h * h)) if h else 0.0
        dinc = math.degrees((h * dz - z * dh) / (f * f)) if f else 0.0
        return {
            "declination_deg": dec,
            "inclination_deg": inc,
            "horizontal_intensity_nT": h,
            "north_X_nT": x,
            "east_Y_nT": y,
            "down_Z_nT": z,
            "total_intensity_nT": f,
            "secular_variation": {
                "dDeclination_deg_per_yr": ddec,
                "dInclination_deg_per_yr": dinc,
                "dHorizontal_nT_per_yr": dh,
                "dX_nT_per_yr": dx,
                "dY_nT_per_yr": dy,
                "dZ_nT_per_yr": dz,
                "dTotal_nT_per_yr": df,
            },
        }


# --- load the model ONCE at import (a server reuses it). ---
_MODEL = _WMM(_COF)
VALID_FROM = _MODEL.epoch          # 2025.0
VALID_TO = _MODEL.epoch + 5.0      # 2030.0


def _decimal_year(when: str | None) -> tuple[float, str]:
    """ISO date/datetime, a bare decimal year ('2027.5'), or None/'now'
    -> (decimal_year, echoed_input). Decimal year uses the standard
    year + day_fraction / days_in_year convention."""
    if when is None or str(when).strip().lower() == "now":
        dt = datetime.now(timezone.utc)
        echoed = "now"
    else:
        s = str(when).strip()
        # bare decimal year, e.g. "2027.5"
        try:
            return float(s), s
        except ValueError:
            pass
        iso = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone(timezone.utc)
        echoed = s
    year = dt.year
    start = datetime(year, 1, 1, tzinfo=timezone.utc)
    end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
    frac = (dt - start).total_seconds() / (end - start).total_seconds()
    return year + frac, echoed


def _compass_point(dec_deg: float) -> str:
    """Round declination's sign to a plain-English compass note."""
    if abs(dec_deg) < 0.05:
        return "magnetic north is essentially true north here"
    side = "east" if dec_deg > 0 else "west"
    return f"magnetic north is {abs(dec_deg):.2f} deg {side} of true north"


def compute(lat: float, lon: float, altitude_km: float = 0.0,
            when: str | None = None) -> dict:
    """The full deterministic geomagnetic snapshot. JSON-serializable dict.

    lat/lon are geodetic degrees; altitude_km is height above the WGS84
    ellipsoid (WMM is valid -1 to 850 km); `when` is an ISO date/datetime, a
    bare decimal year, or 'now'. Declination is positive **east** of true north.
    """
    if not (-90.0 <= lat <= 90.0):
        raise ValueError("lat must be in [-90, 90]")
    if not (-180.0 <= lon <= 180.0):
        raise ValueError("lon must be in [-180, 180]")
    if not (-1.0 <= altitude_km <= 850.0):
        raise ValueError("altitude_km must be in [-1, 850] (WMM validity)")

    dec_year, echoed = _decimal_year(when)
    if not (VALID_FROM <= dec_year < VALID_TO):
        raise ValueError(
            f"date {dec_year:.3f} is outside WMM2025 validity "
            f"[{VALID_FROM:.1f}, {VALID_TO:.1f})"
        )

    fld = self_round(_MODEL.field(lat, lon, altitude_km, dec_year))
    fld_dec = fld["declination_deg"]
    return {
        "query": {
            "lat": lat, "lon": lon, "altitude_km": altitude_km,
            "decimal_year": round(dec_year, 5), "input_when": echoed,
        },
        "declination_deg": fld_dec,
        "compass_note": _compass_point(fld_dec),
        **fld,
        "model": _MODEL.model,
        "model_epoch": _MODEL.epoch,
        "valid_range": [VALID_FROM, VALID_TO],
        "units": {
            "declination_deg": "degrees, positive east of true north",
            "inclination_deg": "degrees, positive down",
            "intensity": "nanotesla (nT)",
            "secular_variation": "per year",
        },
        "deterministic": True,
        "engine": "WMM2025 spherical-harmonic synthesis (geomag70 algorithm)",
    }


def self_round(fld: dict) -> dict:
    """Round field outputs to sensible precision (NOAA reports D/I to 0.01 deg,
    intensities to ~0.1 nT). Keep a hair more so re-derivation stays exact."""
    out = {}
    for k, v in fld.items():
        if k == "secular_variation":
            out[k] = {kk: round(vv, 4) for kk, vv in v.items()}
        elif "deg" in k:
            out[k] = round(v, 4)
        else:
            out[k] = round(v, 2)
    return out


if __name__ == "__main__":
    import json
    # quick manual smoke: declination over a few well-known cities
    for name, la, lo in [("Boulder CO", 40.015, -105.27),
                          ("London", 51.5074, -0.1278),
                          ("Sydney", -33.8688, 151.2093)]:
        r = compute(la, lo, 0.0, "2026-06-26")
        print(f"{name:12s} D={r['declination_deg']:+7.2f} deg  "
              f"I={r['inclination_deg']:+6.2f}  F={r['total_intensity_nT']:.0f} nT  "
              f"({r['compass_note']})")
