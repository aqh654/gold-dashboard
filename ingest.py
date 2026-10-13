"""Ingestion. One function per source; each writes data/<name>.csv plus a
timestamped vintage under data/vintages/ (sources revise silently).

    python ingest.py --synthetic     # generate sample data; app runs immediately
    python ingest.py --all           # real pulls (network required)
    python ingest.py --source price  # one source

Design rule: the app never fetches. It reads data/*.csv only.
"""
import argparse, io, sys, datetime as dt
from pathlib import Path
import numpy as np
import pandas as pd

DATA = Path(__file__).parent / "data"
VINT = DATA / "vintages"

MONTHS = pd.date_range("2021-01-01", "2026-08-01", freq="MS")   # sample span
M = len(MONTHS)

def _write(name: str, df: pd.DataFrame) -> None:
    DATA.mkdir(exist_ok=True); VINT.mkdir(exist_ok=True)
    df.to_csv(DATA / f"{name}.csv", index=False)
    stamp = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    df.to_csv(VINT / f"{name}_{stamp}.csv", index=False)
    print(f"wrote {name}: {len(df)} rows")

# ---------------------------------------------------------------- synthetic --
def _series(anchors, n=M):
    """Piecewise-linear interpolation through (index, value) anchors."""
    out = np.empty(n)
    for (m0, v0), (m1, v1) in zip(anchors, anchors[1:]):
        idx = np.arange(m0, m1 + 1)
        out[idx] = np.interp(idx, [m0, m1], [v0, v1])
    return out

def _wig(a, amp, per):
    return a + amp * np.sin(np.arange(len(a)) / per * 2 * np.pi)

def synthetic():
    price = _wig(_series([(0,1950),(6,1780),(11,1830),(13,1900),(21,1640),(26,1990),(31,1930),
        (35,2060),(39,2340),(45,2680),(49,2880),(53,3320),(57,3480),(59,3620),
        (63,3940),(67,4152)]), 22, 9)
    ry = _wig(_series([(0,-1.30),(6,-0.55),(11,-1.05),(13,-0.60),(17,0.90),(21,1.55),(26,1.15),
        (33,2.45),(41,1.95),(47,2.10),(53,2.25),(59,1.85),(67,1.70)]), .05, 7)
    implied = 1655 - 227 * ry                  # pre-2022 real-yield fit, extrapolated
    _write("price", pd.DataFrame({"date": MONTHS, "price_usd_oz": price.round(0),
        "real_yield_pct": ry.round(2), "yield_implied_usd_oz": implied.round(0)}))

    etf = _wig(_series([(0,1558),(11,1500),(15,1585),(23,1372),(33,1268),(37,1218),
        (42,1262),(47,1352),(53,1478),(59,1524),(67,1608)]), 6, 5)
    _write("etf", pd.DataFrame({"date": MONTHS, "tonnes": etf.round(1)}))

    # Declared official sector: monthly net purchases, tonnes, per country.
    banks = [("China",190),("Poland",92),("Turkey",76),("India",68),("Iraq",24),
             ("Kazakhstan",22),("Uzbekistan",18),("Czechia",14),("Singapore",10),
             ("Thailand",9),("Qatar",8),("Hungary",6),("Serbia",5),
             ("Philippines",-4),("Russia",-44)]
    rows = []
    for k, (name, t12) in enumerate(banks):
        monthly = t12/12 + (t12/14) * np.sin((np.arange(M) + k) * 1.1)
        rows.append(pd.DataFrame({"date": MONTHS, "country": name,
                                  "net_purchases_t": monthly.round(2)}))
    _write("declared", pd.concat(rows, ignore_index=True))

    # The gap: quarterly, IMF-reported vs WGC estimate of official demand.
    q = pd.period_range("2022Q1", "2026Q2", freq="Q").to_timestamp(how="end").normalize()
    qi = [30,45,88,120, 60,55,70,95, 40,35,60,75, 25,30,45,55, 16,20]
    qw = [165,180,400,417, 284,175,337,229, 290,183,220,333, 244,166,258,231, 244,234]
    _write("gap", pd.DataFrame({"quarter_end": q, "imf_reported_t": qi,
                                "wgc_estimate_t": qw}))

    # Swiss exports by destination, tariff heading 7108, tonnes.
    dests = {
        "China + HK": _wig(_series([(0,58),(14,88),(24,96),(30,72),(38,60),(48,44),(58,52),(67,58)]), 7, 5),
        "India":      _wig(_series([(0,26),(20,30),(33,40),(45,30),(57,34),(67,30)]), 6, 6),
        "Turkey":     _wig(_series([(0,8),(20,20),(27,30),(31,14),(45,10),(67,12)]), 3, 5),
        "UAE + Gulf": _wig(_series([(0,12),(24,18),(48,20),(67,22)]), 3, 7),
        "UK + US":    _wig(_series([(0,16),(22,8),(46,12),(48,64),(50,30),(53,26),(60,34),(67,40)]), 4, 6),
        "other":      _wig(_series([(0,14),(30,16),(67,18)]), 2, 8),
    }
    rows = [pd.DataFrame({"date": MONTHS, "destination": d, "tonnes": np.clip(s,0,None).round(1)})
            for d, s in dests.items()]
    _write("swiss", pd.concat(rows, ignore_index=True))

# ------------------------------------------------------------- real fetchers --
# Each returns a DataFrame in the same schema the synthetic generator writes,
# so the app is indifferent to provenance.

def fetch_price():
    """COMEX front-month futures via yfinance; real yield via FRED's keyless
    CSV endpoint. Daily; the app downsamples for display."""
    import yfinance as yf, requests
    px = yf.download("GC=F", start="2021-01-01", auto_adjust=True)["Close"].rename("price_usd_oz")
    r = requests.get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFII10", timeout=30)
    ry = pd.read_csv(io.StringIO(r.text), parse_dates=["DATE"]).set_index("DATE")["DFII10"]
    ry = pd.to_numeric(ry, errors="coerce").rename("real_yield_pct")
    df = pd.concat([px, ry], axis=1).dropna().reset_index(names="date")
    # Fit price ~ a + b*real_yield on pre-2022 data, extrapolate as the implied level.
    pre = df[df.date < "2022-01-01"]
    b, a = np.polyfit(pre.real_yield_pct, pre.price_usd_oz, 1)
    df["yield_implied_usd_oz"] = a + b * df.real_yield_pct
    _write("price", df)

def fetch_etf():
    """GLD daily bar list (State Street) + IAU holdings (BlackRock). Issuer
    CSV/XLSX URLs move occasionally; update here, nowhere else."""
    raise NotImplementedError(
        "Point this at the current GLD spreadsheet "
        "(https://www.spdrgoldshares.com -> historical data) and the IAU "
        "holdings file, sum ounces to tonnes, emit columns [date, tonnes].")

def fetch_declared():
    """IMF monetary gold by country, SDMX REST at data.imf.org (dataset: IRFCL /
    International Reserves). Emit [date, country, net_purchases_t] as the monthly
    first difference of holdings converted at 32,150.7 oz/t."""
    raise NotImplementedError("See data.imf.org API docs; reporting is voluntary and lagged 1-3 months.")

def fetch_gap():
    """WGC Gold Demand Trends official-sector estimate: four numbers a year,
    hand-entered from the quarterly release (free registration). IMF-reported
    aggregate comes from fetch_declared(); keep both in one file."""
    raise NotImplementedError("Hand-edit data/gap.csv each quarter; automation is not worth a login scrape.")

def fetch_swiss():
    """Swiss-Impex (Federal Office for Customs and Border Security), tariff
    heading 7108 exports by partner, monthly CSV export from the web query.
    Drop the download into data/raw/ and normalise to [date, destination, tonnes]."""
    raise NotImplementedError("Swiss-Impex query UI -> CSV; group partners into the six buckets in design.HUES.")

REAL = {"price": fetch_price, "etf": fetch_etf, "declared": fetch_declared,
        "gap": fetch_gap, "swiss": fetch_swiss}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--source", choices=REAL.keys())
    args = ap.parse_args()
    if args.synthetic:
        synthetic()
    elif args.all:
        for n, f in REAL.items():
            try: f()
            except NotImplementedError as e: print(f"[skip] {n}: {e}", file=sys.stderr)
    elif args.source:
        REAL[args.source]()
    else:
        ap.print_help()
