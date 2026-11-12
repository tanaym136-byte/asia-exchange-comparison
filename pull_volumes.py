"""Pull daily cash-equity turnover for NSE, BSE, Korea Exchange and HKEX.

    python pull_volumes.py                               # last 20 weekdays
    python pull_volumes.py --start 2026-09-01 --end 2026-11-11
    python pull_volumes.py --only KRX HKEX                 # some exchanges only

In a Jupyter notebook:  %run pull_volumes.py --start 2026-09-01

Writes data/volumes.csv, one row per exchange, market and trading day:
    date, exchange, market, turnover_local, currency, trades, source

Where each number comes from (the workbook's Volumes sheet explains what each one counts):
  NSE   official UDiFF cash-market bhavcopy; sum of TtlTrfVal and TtlNbOfTxsExctd over every row
  BSE   official UDiFF equity bhavcopy, same layout and same sums
  KRX   daily stock-level trading value from KRX, as mirrored in FinanceData/marcap on GitHub
        (KRX's own data portal needs a login or an API key), summed by market
  HKEX  official Daily Quotations sheet ("Today's Turnover", HK$ and deals); HKEX keeps about five
        weeks online, so older days fall back to the sycheng0924/hsi-data mirror of the same figure

A weekday with no file is skipped: it is either an exchange holiday or a file not yet posted.
If a source cannot be reached at all (network blocked, site down), the script says so and moves on.
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import re
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
NSE_URL = "https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_{:%Y%m%d}_F_0000.csv.zip"
BSE_URL = "https://www.bseindia.com/download/BhavCopy/Equity/BhavCopy_BSE_CM_0_0_0_{:%Y%m%d}_F_0000.CSV"
HKEX_URL = "https://www.hkex.com.hk/eng/stat/smstat/dayquot/d{:%y%m%d}e.htm"
HKEX_MIRROR = "https://raw.githubusercontent.com/sycheng0924/hsi-data/main/docs/hsi.json"
KRX_MIRROR = "https://raw.githubusercontent.com/FinanceData/marcap/master/data/marcap-{}.parquet"
KRX_MARKETS = {"KOSPI": "KOSPI", "KOSDAQ": "KOSDAQ", "KOSDAQ GLOBAL": "KOSDAQ", "KONEX": "KONEX"}
COLUMNS = ["date", "exchange", "market", "turnover_local", "currency", "trades", "source"]


class Unreachable(Exception):
    """The host could not be reached at all, as opposed to a missing file."""


def fetch(url: str, referer: str | None = None, timeout: int = 30) -> bytes | None:
    """Body of url, None on HTTP 404, Unreachable on any network-level failure."""
    headers = {"User-Agent": UA, "Accept": "*/*"}
    if referer:
        headers["Referer"] = referer
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise Unreachable(f"HTTP {e.code}") from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise Unreachable(str(e)) from e


# ---------------------------------------------------------------------------------------------
# Parsers. Each takes the raw file and returns a dict, or None when the file is not a bhavcopy.
# ---------------------------------------------------------------------------------------------

def parse_udiff(raw: bytes) -> dict | None:
    """Totals from an NSE or BSE UDiFF cash-market bhavcopy (zipped or plain CSV)."""
    if raw[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            raw = z.read(z.namelist()[0])
    if not raw.lstrip(b"\xef\xbb\xbf").startswith(b"TradDt"):
        return None  # BSE answers a missing day with an HTML page and HTTP 200
    df = pd.read_csv(io.BytesIO(raw))
    dates = pd.to_datetime(df["TradDt"].unique())
    if len(dates) != 1:
        raise ValueError(f"bhavcopy holds {len(dates)} trade dates")
    return {"date": dates[0].date(), "turnover": float(df["TtlTrfVal"].sum()),
            "trades": int(df["TtlNbOfTxsExctd"].fillna(0).sum()), "rows": len(df)}


def parse_hkex_sheet(text: str) -> dict | None:
    """Turnover (HK$) and deals from the Market Highlights block of a Daily Quotations sheet."""
    turnover = re.search(r"Today's Turnover:\s*\(HK\$\):\s*([\d,]+)", text)
    deals = re.search(r"\(Deals\):\s*([\d,]+)", text)
    date = re.search(r"DATE:\s*(\d{1,2} [A-Z]{3} \d{4})", text)
    if not (turnover and date):
        return None
    return {"date": dt.datetime.strptime(date.group(1), "%d %b %Y").date(),
            "turnover": float(turnover.group(1).replace(",", "")),
            "trades": int(deals.group(1).replace(",", "")) if deals else None}


def krx_daily(df: pd.DataFrame) -> pd.DataFrame:
    """Stock-level KRX rows (Date, Market, Amount) to one row per day and market."""
    d = df[df["Market"].isin(KRX_MARKETS)].assign(market=lambda x: x["Market"].map(KRX_MARKETS))
    g = d.groupby([pd.to_datetime(d["Date"]).dt.date, "market"])["Amount"].sum().reset_index()
    g.columns = ["date", "market", "turnover_local"]
    return g[g["turnover_local"] > 0]


# ---------------------------------------------------------------------------------------------
# Pullers
# ---------------------------------------------------------------------------------------------

def weekdays(start: dt.date, end: dt.date):
    return [d.date() for d in pd.bdate_range(start, end)]


def pull_udiff(name, url, referer, start, end, log) -> list[dict]:
    rows, failures = [], 0
    for day in weekdays(start, end):
        try:
            raw = fetch(url.format(day), referer)
        except Unreachable as e:
            failures += 1
            if failures >= 3:
                log(f"{name}: cannot reach {url.split('/')[2]} ({e}); skipped. Run from a normal internet connection.")
                return rows
            continue
        parsed = parse_udiff(raw) if raw else None
        if parsed is None:
            continue  # holiday or not yet posted
        if parsed["date"] != day:
            raise ValueError(f"{name} file for {day} says {parsed['date']}")
        rows.append({"date": day, "exchange": name, "market": "Cash market", "turnover_local": parsed["turnover"],
                     "currency": "INR", "trades": parsed["trades"], "source": url.split("/")[2]})
    log(f"{name}: {len(rows)} sessions")
    return rows


def pull_krx(start, end, log) -> list[dict]:
    frames = []
    for year in range(start.year, end.year + 1):
        try:
            raw = fetch(KRX_MIRROR.format(year), timeout=120)
        except Unreachable as e:
            log(f"KRX: cannot reach GitHub ({e}); skipped.")
            return []
        if raw:
            frames.append(pd.read_parquet(io.BytesIO(raw), columns=["Date", "Market", "Amount"]))
    if not frames:
        return []
    g = krx_daily(pd.concat(frames))
    g = g[(g["date"] >= start) & (g["date"] <= end)]
    log(f"KRX: {g['date'].nunique()} sessions")
    return [{"date": r.date, "exchange": "KRX", "market": r.market, "turnover_local": float(r.turnover_local),
             "currency": "KRW", "trades": None, "source": "github.com/FinanceData/marcap (KRX data)"}
            for r in g.itertuples()]


def pull_hkex(start, end, log) -> list[dict]:
    rows, failures, reachable = {}, 0, True
    for day in weekdays(max(start, end - dt.timedelta(days=40)), end):  # sheets stay online ~5 weeks
        if not reachable:
            break
        try:
            raw = fetch(HKEX_URL.format(day))
        except Unreachable as e:
            failures += 1
            if failures >= 3:
                reachable = False
                log(f"HKEX: cannot reach hkex.com.hk ({e}); using the mirror for every day.")
            continue
        parsed = parse_hkex_sheet(raw.decode("latin-1")) if raw else None
        if parsed and parsed["date"] == day:
            rows[day] = {"date": day, "exchange": "HKEX", "market": "Main Board", "turnover_local": parsed["turnover"],
                         "currency": "HKD", "trades": parsed["trades"], "source": "hkex.com.hk Daily Quotations"}
    try:
        mirror = json.loads(fetch(HKEX_MIRROR))
        for d, _close, _prev, turnover, _half in mirror["rows"]:
            day = dt.date.fromisoformat(d)
            if start <= day <= end and day not in rows:
                rows[day] = {"date": day, "exchange": "HKEX", "market": "Main Board", "turnover_local": float(turnover),
                             "currency": "HKD", "trades": None,
                             "source": "github.com/sycheng0924/hsi-data (HKEX Daily Quotations)"}
    except (Unreachable, TypeError) as e:
        log(f"HKEX mirror: unavailable ({e})")
    log(f"HKEX: {len(rows)} sessions")
    return list(rows.values())


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--start", type=dt.date.fromisoformat)
    ap.add_argument("--end", type=dt.date.fromisoformat, default=dt.date.today())
    ap.add_argument("--days", type=int, default=20, help="weekdays back from --end when --start is not given")
    ap.add_argument("--out", type=Path, default=Path("data/volumes.csv"))
    ap.add_argument("--only", nargs="*", choices=["NSE", "BSE", "KRX", "HKEX"])
    if argv is None and "ipykernel" in sys.modules:
        # Inside Jupyter: the kernel adds its own arguments (-f kernel.json), so ignore anything unknown
        a, _ = ap.parse_known_args([x for x in sys.argv[1:] if not x.endswith(".json")])
    else:
        a = ap.parse_args(argv)
    start = a.start or (pd.Timestamp(a.end) - pd.offsets.BDay(a.days - 1)).date()
    log = lambda m: print(m, file=sys.stderr)  # noqa: E731
    want = set(a.only or ["NSE", "BSE", "KRX", "HKEX"])

    rows = []
    if "NSE" in want:
        rows += pull_udiff("NSE", NSE_URL, "https://www.nseindia.com/", start, a.end, log)
    if "BSE" in want:
        rows += pull_udiff("BSE", BSE_URL, "https://www.bseindia.com/", start, a.end, log)
    if "KRX" in want:
        rows += pull_krx(start, a.end, log)
    if "HKEX" in want:
        rows += pull_hkex(start, a.end, log)

    df = pd.DataFrame(rows, columns=COLUMNS).sort_values(["exchange", "market", "date"]).reset_index(drop=True)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(a.out, index=False, float_format="%.0f")
    print(f"wrote {len(df)} rows to {a.out}")
    if len(df):
        summary = df.groupby(["exchange", "market", "currency"]).agg(
            sessions=("date", "nunique"), first=("date", "min"), last=("date", "max"),
            avg_daily_turnover=("turnover_local", "mean"))
        print(summary.to_string(float_format=lambda v: f"{v:,.0f}"))
    print(f"To update the workbook, paste {a.out} over the 'Volume data' sheet (from cell A1).")


if __name__ == "__main__":
    main()
