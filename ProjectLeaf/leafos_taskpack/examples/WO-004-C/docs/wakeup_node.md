# LeafOS Wakeup Node (WO-004-C)

This document explains the WO-004-C wakeup node for the LeafOS Brain/Coder/Reviewer
parser layer and for humans who prefer their nodes documented.

## WO-004-C purpose

The wakeup node is a minimal LeafOS embedded action that demonstrates the canonical
node shape:

```text
input -> stochastic branch -> optional data collection -> structured output -> logs
```

It collects local date/time context, flips an OS-backed coin, and takes one of two
branches. It is deliberately small. It does not trade, advise, predict, or persist
anything to a network.

## Heads / tails branch logic

The coin uses `secrets.randbelow(2)` (OS-backed randomness). A `--force heads|tails`
override exists so branch logic is testable without flipping forever.

```text
tails  ->  greeting = "Good afternoon" if 15 <= hour <= 23 else "Good morning"
		   prints: "<greeting>, the time is <HH:MM:SS>"
		   importstring = null   (no quote collection)

heads  ->  pick a random ticker from tickers.txt (or the fallback universe)
		   best-effort quote collection (optional yfinance)
		   build a compact-JSON wakeup_stock_payload
		   prints the offline-analysis prompt carrying that payload
```

Symbols:

```text
LEAF  @leaf.active    tails branch
*     @leaf.model     heads branch
WARN  @leaf.warning   degraded quote collection
```

## JSON importstring payload

On the heads branch, `importstring` is a compact (no-whitespace) JSON
`wakeup_stock_payload`:

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

On the tails branch, `importstring` is `null`.

When a quote cannot be collected the payload is still emitted with
`price`/`currency`/`market_time` set to `null` and `status`/`warning` describing
the degraded state. Accepted degraded states:

```text
module_unavailable   quote_error   no_quote   offline
```

## Log files

Every run writes structured logs under the module's `runs/` directory:

```text
runs/
|-- latest/                        newest run (symlink, or a copy fallback on Windows)
|   `-- wakeup_result.json
|-- wakeup_log.csv                 one compact row appended per run
`-- YYYY-MM-DD_HH-MM-SS_WO-004-C/
	`-- wakeup_result.json
```

`wakeup_result.json` is a `leafos_wakeup_result` object with:

```text
leafos_object  version  symbol  branch  context  quote  message  importstring
```

`wakeup_log.csv` columns:

```text
local_datetime  branch  message  ticker  price  currency  quote_status  quote_source  warning
```

## How this fits LeafOS embedded actions

The node is representable as a LeafOS agent graph node (`embedded_action`). See
[agent_node.json](../agent_node.json). The node declares its entrypoint
(`./wakeup.sh`), expected outputs, test commands, and a completion gate. This lets
a graph/loop driver run the node, verify its outputs, and gate a checkpoint, which
is exactly the 0.3.0/0.4.0 graph + embedded-action model the rest of LeafOS uses.

## How to test offline

The node is offline-first; quote collection is the only optional piece, and its
absence is an accepted degraded state -- not a failure.

```bash
bash -n wakeup.sh
python3 -m py_compile wakeup.py
./wakeup.sh --force tails
./wakeup.sh --force heads --ticker NVDA
python3 tests/test_wakeup_json.py runs/latest/wakeup_result.json
bash tests/test_wakeup_shell.sh
```

All of the above pass without network access and without `yfinance` installed.
