# WO-004-C-01 — Wakeup Runtime Node

```text
Status: Implemented and verified (2026-07-19 closeout)
Branch: ~C
System: LeafOS / Project New Leaf
Module: Wakeup
Primary files: wakeup.py, wakeup.sh, tickers.txt
```

## 1. Purpose

Create a small LeafOS wakeup node that can be run from CLI as a self-contained embedded action.

This node performs four simple operations:

```text
1. Collect local date and time.
2. Flip a local random coin.
3. If tails, print a time-aware greeting.
4. If heads, select a random ticker and optionally collect quote data.
```

This is intentionally small. The goal is not financial automation, market prediction, or yet another cursed dashboard. The goal is to create a clean miniature example of a LeafOS node with:

```text
input → stochastic branch → optional data collection → structured output → logs
```

## 2. LeafOS Symbol Mapping

```text
𔓘  root        WO-004-C identity
🍃  active      normal wakeup branch
⋆   model/event stochastic heads branch
𓂃  flow        collection and logging
⚠︎  warning     degraded quote collection
⚝  complete    output/log finished
⎙  print/export JSON and CSV logs written
```

Machine aliases:

```text
@leaf.root
@leaf.active
@leaf.model
@leaf.flow
@leaf.warning
@leaf.verify
@leaf.print
```

## 3. Required Behavior

### 3.1 Runtime Start

When invoked, the script shall collect:

```text
local date
local time
local timezone name
hour
hostname
platform
work order label
```

The default work order label is:

```text
WO-004-C
```

### 3.2 Coin Branch

The node shall flip a local random coin using OS-backed randomness.

Implementation target:

```python
secrets.randbelow(2)
```

Accepted branches:

```text
heads
tails
```

Testing override shall exist:

```bash
--force heads
--force tails
```

This is required so the branch logic can be tested without sitting around flipping coins like a very bored oracle.

## 4. Tails Branch

If the result is tails:

```text
if hour is 15 through 23:
    greeting = "Good afternoon"
else:
    greeting = "Good morning"
```

Required output:

```text
Good morning, the time is $time
```

or:

```text
Good afternoon, the time is $time
```

Example:

```text
🍃 Good morning, the time is 09:14:22
```

The tails branch shall not attempt stock collection.

## 5. Heads Branch

If the result is heads:

```text
1. Select a random ticker from tickers.txt or default ticker universe.
2. Attempt quote collection using an optional Python module.
3. Build a compact JSON import string.
4. Print the afterlife analysis prompt.
```

Required output shape:

```text
Welcome back from the after life! Please analyze in an offline environment the following data around the stock ticker $importstring
```

Where `$importstring` is compact JSON.

Example shape:

```json
{
  "leafos_object": "wakeup_stock_payload",
  "version": "0.4.0-C",
  "work_order": "WO-004-C",
  "collected_at": "2026-06-21T09:14:22-07:00",
  "date": "2026-06-21",
  "time": "09:14:22",
  "ticker": "NVDA",
  "price": 123.45,
  "currency": "USD",
  "market_time": "2026-06-21 09:14:00-07:00",
  "source": "yfinance.fast_info",
  "status": "ok",
  "warning": null
}
```

## 6. Ticker Universe

The script shall support:

```text
tickers.txt
```

Rules:

```text
one ticker per line
blank lines ignored
comment lines starting with # ignored
symbols uppercased
fallback default ticker list used if file is missing or empty
```

The term “truly random stock” is treated practically as:

```text
random ticker selected from a defined ticker universe using OS-backed randomness
```

Because “random stock from all possible markets” is not a dataset, it is a lawsuit wearing a hat.

## 7. Optional Quote Module

Recommended optional module:

```bash
python3 -m pip install yfinance
```

The quote fetch is best-effort.

Failure modes shall not crash the entire wakeup node.

Accepted degraded states:

```text
module_unavailable
quote_error
no_quote
offline
```

If quote collection fails, the script still prints the heads prompt with a structured payload containing:

```text
ticker
status
warning
source
date/time
```

## 8. Logging Requirements

Each run shall write structured logs.

Default layout:

```text
runs/
├── latest -> timestamped run folder, if symlink is available
├── wakeup_log.csv
└── YYYY-MM-DD_HH-MM-SS_WO-004-C/
    └── wakeup_result.json
```

The JSON result shall include:

```text
leafos_object
version
symbol
branch
context
quote
message
importstring
```

CSV shall append compact rows:

```text
local_datetime
branch
message
ticker
price
currency
quote_status
quote_source
warning
```

## 9. CLI Interface

Required commands:

```bash
./wakeup.sh
./wakeup.sh --force tails
./wakeup.sh --force heads
./wakeup.sh --force heads --ticker NVDA
```

Direct Python invocation shall also work:

```bash
python3 wakeup.py
python3 wakeup.py --force heads --ticker NVDA
```

## 10. Files

Required files:

```text
wakeup.py
wakeup.sh
tickers.txt
README.md
```

Optional future files:

```text
tests/test_wakeup.sh
tests/test_wakeup_json.py
docs/wakeup_node.md
```

## 11. Safety and Non-Goals

This work order shall not implement:

```text
trading
investment advice
portfolio management
automatic buying or selling
network persistence
scheduled background autorun
credential storage
API key collection
```

The heads branch only collects and formats a stock quote payload for offline analysis.

The output shall not claim prediction, recommendation, or financial certainty.

## 12. Acceptance Criteria

The work order is complete when:

```text
wakeup.py exists
wakeup.sh exists
tickers.txt exists
README.md exists
./wakeup.sh --force tails prints a greeting and time
./wakeup.sh --force heads --ticker NVDA prints the afterlife prompt
runs/*/wakeup_result.json is written
runs/wakeup_log.csv is appended
heads branch survives missing yfinance
tails branch does not attempt quote collection
```

Recommended checks:

```bash
bash -n wakeup.sh
python3 -m py_compile wakeup.py
./wakeup.sh --force tails
./wakeup.sh --force heads --ticker NVDA
```

## 13. Completion State

When accepted:

```text
⚝ WO-004-C-01 verified
ꕤ wakeup runtime node checkpoint allowed
```

The runtime is now available through `leafctl wakeup` on Bash and PowerShell.
Both deterministic branches and the structured log contract pass their current
regression suite. See `reports/work-orders/WO-004-C-COMPLETION-REPORT.md`.
