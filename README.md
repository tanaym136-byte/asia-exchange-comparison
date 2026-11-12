# How NSE, BSE, Korea Exchange and HKEX trade

A side-by-side comparison of the rules that decide how four Asian exchanges trade: hours (converted to UTC), opening and closing auctions, price limits and volatility controls, tick sizes, flagship index derivatives and settlement cycles. Rules are as at 11 November 2026, and every row cites its source. A short Python script pulls daily cash turnover for the four markets.

- `exchange_comparison.xlsx`: the comparison (12 sheets, formula-driven where a number can be computed)
- `pull_volumes.py`: daily cash turnover from exchange files, written to `data/volumes.csv`
- `tests/`: parser tests on real NSE and HKEX files

## What the comparison shows

1. **The four cash markets trade together for only 95 minutes a day**: 03:45-04:00 and 05:00-06:20 UTC. HKEX's lunch break and the end of KRX's continuous session set the window. The Hours sheet converts every session from local time with a formula, so the overlap updates if any time changes.
2. **India's ticks are far finer, and NSE and BSE differ from each other.** At a US$10 share price, one tick is 0.5 bp of the price on NSE and BSE, 6.4 bp on HKEX and 7.4 bp on KRX. A stock at Rs 1,500 ticks in Rs 0.10 on NSE but Rs 0.05 on BSE; at Rs 200 it is Rs 0.01 on NSE and Rs 0.05 on BSE. BSE's own trading page still describes an older rule, so I tested the table against the prices traded on each exchange: between Rs 1,000 and Rs 5,000, 92% of NSE prices sit on the Rs 0.10 grid against 68% of BSE prices.
3. **September 2026 average daily cash turnover** was about US$25.7bn on HKEX, $15.9bn on KOSPI, $12.1bn on NSE, $5.3bn on KOSDAQ and $1.2bn on BSE. The ranking depends on definitions: HKEX's headline turnover includes ETPs, warrants and CBBCs; the KRX figure here covers listed stocks only, without ETFs or trades on Nextrade. The script's August and September averages for NSE and BSE match the figures the exchanges published to within 0.001%.
4. **India changes its closing rules twice in 2026.** A closing auction for stocks with derivatives started on 3 August and also set derivatives expiry prices. From 7 December the auction moves to 15:30-15:40 and expiry settlement goes back to a 30-minute VWAP (SEBI circular of 15 October 2026).
5. **Korea now trades almost all day.** KRX added a continuous after-market to 20:00 on 14 September 2026, Nextrade trades the same stocks from 08:00, and KOSPI 200 derivatives have a night session to 06:00. Volatility interruptions fired 1,637 times on the after-market's first day.
6. **Settlement is moving to T+1**: India since January 2023, Korea and Hong Kong both aiming for 2028.

## The workbook

| Sheet | Contents |
| --- | --- |
| Comparison | The four exchanges on 16 attributes, with source IDs |
| Hours (UTC) | 47 sessions and auction phases, local time and UTC, overlap in minutes, chart |
| Auctions | Opening and closing auctions: phases, order types, price limits, random ends, fallbacks |
| Price limits | Daily limits, volatility interruptions, circuit breakers |
| Tick sizes | Tick tables, a calculator of tick size in basis points at the same US dollar price, and the NSE/BSE price-grid test |
| Index derivatives | Nifty 50, Sensex, KOSPI 200, Hang Seng Index: contract size, tick value, contract value in USD, expiry, settlement |
| Volumes | September 2026 and latest-window turnover in local currency and USD; reconciliation with published NSE and BSE figures |
| Checks | Session counts, missing weekdays explained, UTC conversions, HKEX turnover against HKEX's own sheet, duplicates, script against published NSE and BSE averages |
| Changes to watch | Ten dated rule changes, live and announced |
| Sources | 49 sources with URLs |

Blue cells are inputs typed in from a source, black cells are formulas, green cells are formulas that read another sheet, and yellow cells are still to verify (found only in a secondary source, or not found for that exchange).

## Pulling volumes

```
pip install pandas pyarrow
python pull_volumes.py --start 2026-09-01           # or --days 20 for the last 20 weekdays
python -m pytest                                     # 8 tests
```

Then paste `data/volumes.csv` over the workbook's `Volume data` sheet; the Volumes and Checks sheets read from it.

| Market | Source | What is summed |
| --- | --- | --- |
| NSE | Official UDiFF cash-market bhavcopy (`nsearchives.nseindia.com`) | Turnover and trades over every row |
| BSE | Official UDiFF equity bhavcopy (`bseindia.com`) | Same |
| KRX | KRX daily stock data, mirrored in [FinanceData/marcap](https://github.com/FinanceData/marcap) | Trading value of listed stocks by market |
| HKEX | Official Daily Quotations sheet, with the [sycheng0924/hsi-data](https://github.com/sycheng0924/hsi-data) mirror for days older than about five weeks | "Today's Turnover" (HK$) and deals |

A weekday with no file is skipped. `data/volumes.csv` covers 3 August to 11 November 2026 (407 rows), and every missing weekday is an exchange holiday: four Indian holidays on both NSE and BSE, five Korean and two Hong Kong. If a host cannot be reached at all, the script says so and carries on with the others; on a day with no file, BSE returns its web page with HTTP 200, which the script detects.

## Limits

- The workbook summarises exchange rules; it is not a rulebook. Check the cited circular before any live use.
- The Sensex futures tick (Rs 0.05) comes from 2023 specifications; NSE moved its index futures to level-based ticks in 2025 and BSE may have done the same. The KOSPI 200 level is left blank for input.
- Turnover is converted at one FX rate per currency for the whole window.

## Author

Tanay Mishra, MSc Finance with Banking (Distinction), University of Bath. Other work: [tanaymishraresearch.substack.com](https://tanaymishraresearch.substack.com)
