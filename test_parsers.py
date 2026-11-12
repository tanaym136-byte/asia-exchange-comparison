"""Parser tests on real exchange files (trimmed): an NSE UDiFF cash-market bhavcopy for 14 Oct 2026
and the Market Highlights block of HKEX's Daily Quotations sheet for 21 Oct 2026."""
import datetime as dt
import io
import zipfile
from pathlib import Path

import pandas as pd
import pytest

import pull_volumes as pv

FIX = Path(__file__).parent / "fixtures"


def test_udiff_plain_csv():
    p = pv.parse_udiff((FIX / "nse_cm_20261014_sample.csv").read_bytes())
    assert p["date"] == dt.date(2026, 10, 14)
    assert p["rows"] == 6
    assert p["turnover"] == pytest.approx(468_097_310.83, abs=0.01)
    assert p["trades"] == 19_714


def test_udiff_zipped_matches_plain():
    raw = (FIX / "nse_cm_20261014_sample.csv").read_bytes()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("BhavCopy_NSE_CM_0_0_0_20261014_F_0000.csv", raw)
    assert pv.parse_udiff(buf.getvalue()) == pv.parse_udiff(raw)


def test_udiff_rejects_html_page():
    # BSE returns its web page with HTTP 200 for a day with no file
    assert pv.parse_udiff(b"<!DOCTYPE html><html><body>Bhavcopy</body></html>") is None


def test_udiff_rejects_mixed_dates():
    raw = (FIX / "nse_cm_20261014_sample.csv").read_text().splitlines()
    raw[-1] = raw[-1].replace("2026-10-14", "2026-10-15", 1)
    with pytest.raises(ValueError):
        pv.parse_udiff("\n".join(raw).encode())


def test_hkex_sheet():
    p = pv.parse_hkex_sheet((FIX / "hkex_d261021e_head.htm").read_text(encoding="latin-1"))
    assert p == {"date": dt.date(2026, 10, 21), "turnover": 176_597_304_443.0, "trades": 3_514_778}


def test_hkex_sheet_without_figures():
    assert pv.parse_hkex_sheet("<html>Daily Quotations not available</html>") is None


def test_krx_daily_groups_markets():
    df = pd.DataFrame({
        "Date": ["2026-11-09"] * 4 + ["2026-11-10"],
        "Market": ["KOSPI", "KOSPI", "KOSDAQ", "KOSDAQ GLOBAL", "KONEX"],
        "Amount": [100.0, 50.0, 20.0, 5.0, 0.0],
    })
    g = pv.krx_daily(df).set_index(["date", "market"])["turnover_local"]
    assert g[(dt.date(2026, 11, 9), "KOSPI")] == 150
    assert g[(dt.date(2026, 11, 9), "KOSDAQ")] == 25  # KOSDAQ GLOBAL is part of KOSDAQ
    assert (dt.date(2026, 11, 10), "KONEX") not in g.index  # zero-turnover rows dropped


def test_weekdays_skip_weekends():
    days = pv.weekdays(dt.date(2026, 11, 6), dt.date(2026, 11, 10))
    assert days == [dt.date(2026, 11, 6), dt.date(2026, 11, 9), dt.date(2026, 11, 10)]
