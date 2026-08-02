# WO-004-C -- Wakeup Node

A small, self-contained LeafOS node that demonstrates the shape:

```text
input -> stochastic branch -> optional data collection -> structured output -> logs
```

It is intentionally tiny. It is not trading, not advice, and not prediction.

## Purpose

On each run the node:

1. Collects local date and time.
2. Flips a local OS-backed coin.
3. **Tails** -> prints a time-aware greeting.
4. **Heads** -> selects a random ticker and (best-effort) collects quote data,
   then prints an offline-analysis prompt carrying a compact-JSON payload.

Symbol mapping:

```text
LEAF  active    normal wakeup branch (tails)   @leaf.active
*     model     stochastic heads branch        @leaf.model
WARN  warning   degraded quote collection      @leaf.warning
```

## Run

```bash
./wakeup.sh
./wakeup.sh --force tails
./wakeup.sh --force heads --ticker NVDA
```

Direct Python invocation works the same way:

```bash
python3 wakeup.py
python3 wakeup.py --force heads --ticker NVDA
```

## Test branches

The coin is OS-backed (`secrets.randbelow(2)`). To test branch logic
deterministically, force the result instead of flipping forever:

```bash
./wakeup.sh --force tails    # always the greeting branch
./wakeup.sh --force heads    # always the ticker branch
```

The `tails` branch never attempts quote collection.

## Optional stock quote module

Quote collection on the `heads` branch is **optional and best-effort**.
It uses an optional Python module:

```bash
python3 -m pip install yfinance
```

If `yfinance` is missing, or a quote cannot be fetched, the node does **not**
crash. It still prints the heads prompt with a structured payload whose
`status`/`warning` fields record the degraded state. Accepted degraded states:

```text
module_unavailable   quote_error   no_quote   offline
```

## Output

Every run writes structured logs under `runs/`:

```text
runs/
|-- latest/                        -> newest run (symlink, or a copy fallback)
|-- wakeup_log.csv                 -> one compact row appended per run
`-- YYYY-MM-DD_HH-MM-SS_WO-004-C/
	`-- wakeup_result.json         -> full structured result
```

`wakeup_result.json` is a `leafos_wakeup_result` object containing
`version`, `symbol`, `branch`, `context`, `quote`, `message`, and
`importstring` (compact JSON on heads, `null` on tails).

## Ticker universe

`tickers.txt` defines the universe (one symbol per line; blank lines and
`#` comments ignored; symbols uppercased). If the file is missing or empty a
built-in fallback list is used. "Random stock" here means a random ticker
from this defined universe, selected with OS-backed randomness.

## Safety note

This node does **not** perform trading, investment advice, portfolio
management, automatic buying/selling, network persistence, scheduled autorun,
credential storage, or API-key collection. The heads branch only collects and
formats a stock-quote payload for **offline** analysis, and makes no claim of
prediction, recommendation, or financial certainty.
