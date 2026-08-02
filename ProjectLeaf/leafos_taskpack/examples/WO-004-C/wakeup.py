#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WO-004-C -- LeafOS wakeup runtime node.

A small, self-contained LeafOS node:

    input -> stochastic branch -> optional data collection -> structured output -> logs

Tails: print a time-aware greeting.
Heads: select a random ticker, best-effort quote collection, and print an
       offline-analysis prompt carrying a compact-JSON payload.

This is intentionally small. It is not trading, advice, or prediction.
See README.md and docs/wakeup_node.md for the full contract.
"""

import argparse
import csv
import json
import os
import platform as _platform
import secrets
import shutil
import socket
import sys
from datetime import datetime
from pathlib import Path


def _force_utf8_streams():
    """Emit UTF-8 regardless of the console code page (e.g. cp1252 capture)."""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="backslashreplace")
            except (ValueError, OSError):
                pass


_force_utf8_streams()

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------
VERSION = "0.4.0-C"
DEFAULT_WORK_ORDER = "WO-004-C"

# LeafOS symbol mapping (see WO-004-C section 2)
SYMBOL_ACTIVE = "\U0001F343"   # leaf  -- normal wakeup branch (tails)
SYMBOL_MODEL = "\u22C6"        # star  -- stochastic heads branch
SYMBOL_WARNING = "\u26A0\uFE0E"  # warning -- degraded quote collection

# Fallback ticker universe used when tickers.txt is missing or empty.
DEFAULT_TICKERS = [
    "NVDA", "AAPL", "MSFT", "AMD", "INTC",
    "TSLA", "AMZN", "GOOGL", "META", "NFLX",
]

HERE = Path(__file__).resolve().parent

CSV_FIELDS = [
    "local_datetime", "branch", "message", "ticker", "price",
    "currency", "quote_status", "quote_source", "warning",
]


# --------------------------------------------------------------------------
# Runtime context
# --------------------------------------------------------------------------
def collect_context(work_order):
    """Collect local date/time and host context (WO-004-C section 3.1)."""
    now = datetime.now().astimezone()
    return {
        "work_order": work_order,
        "local_date": now.strftime("%Y-%m-%d"),
        "local_time": now.strftime("%H:%M:%S"),
        "local_datetime": now.isoformat(timespec="seconds"),
        "timezone": now.tzname() or "local",
        "hour": now.hour,
        "hostname": socket.gethostname(),
        "platform": _platform.system() or sys.platform,
    }


# --------------------------------------------------------------------------
# Coin branch
# --------------------------------------------------------------------------
def flip_coin(force=None):
    """Flip an OS-backed coin; honor a testing override.

    Returns "heads" or "tails".
    """
    if force in ("heads", "tails"):
        return force
    return "heads" if secrets.randbelow(2) == 1 else "tails"


# --------------------------------------------------------------------------
# Ticker universe
# --------------------------------------------------------------------------
def load_tickers(tickers_file):
    """Load a ticker universe, applying the WO-004-C section 6 rules."""
    path = Path(tickers_file) if tickers_file else (HERE / "tickers.txt")
    symbols = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                symbols.append(line.upper())
    except OSError:
        symbols = []
    return symbols or list(DEFAULT_TICKERS)


def pick_ticker(tickers, override=None):
    """Pick a ticker -- override wins, else OS-backed random choice."""
    if override:
        return override.upper()
    return tickers[secrets.randbelow(len(tickers))]


# --------------------------------------------------------------------------
# Optional quote collection (best-effort, never crashes the node)
# --------------------------------------------------------------------------
def _degraded(status, warning, source="none"):
    return {
        "price": None,
        "currency": None,
        "market_time": None,
        "source": source,
        "status": status,
        "warning": warning,
    }


def collect_quote(ticker):
    """Best-effort quote collection via optional yfinance.

    Accepted degraded states: module_unavailable, quote_error, no_quote, offline.
    """
    try:
        import yfinance  # type: ignore
    except Exception:
        return _degraded("module_unavailable", "yfinance not installed")

    try:
        info = yfinance.Ticker(ticker).fast_info
    except Exception as exc:  # network / lookup failure
        return _degraded("quote_error", _short_err(exc))

    try:
        price = _fast_info_get(info, "last_price", "lastPrice")
        currency = _fast_info_get(info, "currency")
        market_time = _fast_info_get(info, "last_price_time", "regularMarketTime")
        if price is None:
            return _degraded("no_quote", "no price returned", source="yfinance.fast_info")
        return {
            "price": float(price),
            "currency": currency,
            "market_time": str(market_time) if market_time is not None else None,
            "source": "yfinance.fast_info",
            "status": "ok",
            "warning": None,
        }
    except Exception as exc:
        return _degraded("quote_error", _short_err(exc), source="yfinance.fast_info")


def _fast_info_get(info, *keys):
    for key in keys:
        try:
            value = info[key]
        except Exception:
            value = getattr(info, key, None)
        if value is not None:
            return value
    return None


def _short_err(exc):
    text = str(exc).strip().splitlines()
    return (text[0] if text else exc.__class__.__name__)[:160]


# --------------------------------------------------------------------------
# Payloads and messages
# --------------------------------------------------------------------------
def build_stock_payload(ticker, quote, ctx):
    """Compact stock payload (WO-004-C section 5)."""
    return {
        "leafos_object": "wakeup_stock_payload",
        "version": VERSION,
        "work_order": ctx["work_order"],
        "collected_at": ctx["local_datetime"],
        "date": ctx["local_date"],
        "time": ctx["local_time"],
        "ticker": ticker,
        "price": quote["price"],
        "currency": quote["currency"],
        "market_time": quote["market_time"],
        "source": quote["source"],
        "status": quote["status"],
        "warning": quote["warning"],
    }


def compact_json(obj):
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)


def run_tails(ctx):
    """Tails branch -- time-aware greeting, no quote collection."""
    greeting = "Good afternoon" if 15 <= ctx["hour"] <= 23 else "Good morning"
    message = "{}, the time is {}".format(greeting, ctx["local_time"])
    return {
        "symbol": SYMBOL_ACTIVE,
        "branch": "tails",
        "quote": None,
        "message": message,
        "importstring": None,
        "printed": "{} {}".format(SYMBOL_ACTIVE, message),
    }


def run_heads(ctx, ticker_override=None, tickers_file=None):
    """Heads branch -- ticker payload and offline-analysis prompt."""
    tickers = load_tickers(tickers_file)
    ticker = pick_ticker(tickers, ticker_override)
    quote = collect_quote(ticker)
    payload = build_stock_payload(ticker, quote, ctx)
    importstring = compact_json(payload)
    message = ("Welcome back from the after life! Please analyze in an "
               "offline environment the following data around the stock ticker")
    symbol = SYMBOL_MODEL if quote["status"] == "ok" else SYMBOL_WARNING
    return {
        "symbol": symbol,
        "branch": "heads",
        "quote": quote,
        "message": message,
        "importstring": importstring,
        "printed": "{} {} {}".format(SYMBOL_MODEL, message, importstring),
    }


# --------------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------------
def build_result(ctx, branch_out):
    """Assemble the structured wakeup result (WO-004-C section 8)."""
    return {
        "leafos_object": "leafos_wakeup_result",
        "version": VERSION,
        "symbol": branch_out["symbol"],
        "branch": branch_out["branch"],
        "context": ctx,
        "quote": branch_out["quote"],
        "message": branch_out["message"],
        "importstring": branch_out["importstring"],
    }


def write_logs(result, runs_dir=None):
    """Write the run folder, refresh runs/latest, and append the CSV."""
    runs_dir = Path(runs_dir) if runs_dir else (HERE / "runs")
    runs_dir.mkdir(parents=True, exist_ok=True)

    ctx = result["context"]
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    run_dir = runs_dir / "{}_{}".format(stamp, ctx["work_order"])
    run_dir.mkdir(parents=True, exist_ok=True)

    result_path = run_dir / "wakeup_result.json"
    with open(result_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    _update_latest(runs_dir, run_dir, result_path)
    _append_csv(runs_dir / "wakeup_log.csv", result)
    return result_path


def _update_latest(runs_dir, run_dir, result_path):
    """Point runs/latest at the newest run; copy as a fallback."""
    latest = runs_dir / "latest"
    try:
        if latest.is_symlink() or latest.exists():
            if latest.is_dir() and not latest.is_symlink():
                shutil.rmtree(latest)
            else:
                latest.unlink()
    except OSError:
        pass
    try:
        latest.symlink_to(run_dir.name, target_is_directory=True)
        return
    except (OSError, NotImplementedError, AttributeError):
        pass
    latest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(result_path, latest / "wakeup_result.json")


def _append_csv(csv_path, result):
    ctx = result["context"]
    quote = result["quote"] or {}
    row = {
        "local_datetime": ctx["local_datetime"],
        "branch": result["branch"],
        "message": result["message"],
        "ticker": (quote.get("ticker") if isinstance(quote, dict) else None)
        or _result_ticker(result),
        "price": quote.get("price") if isinstance(quote, dict) else None,
        "currency": quote.get("currency") if isinstance(quote, dict) else None,
        "quote_status": quote.get("status") if isinstance(quote, dict) else None,
        "quote_source": quote.get("source") if isinstance(quote, dict) else None,
        "warning": quote.get("warning") if isinstance(quote, dict) else None,
    }
    write_header = not csv_path.exists()
    with open(csv_path, "a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        if write_header:
            writer.writeheader()
        writer.writerow(row)


def _result_ticker(result):
    """Recover the ticker from the heads importstring when present."""
    if not result.get("importstring"):
        return None
    try:
        return json.loads(result["importstring"]).get("ticker")
    except Exception:
        return None


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="wakeup.py",
        description="LeafOS WO-004-C wakeup runtime node.",
    )
    parser.add_argument("--force", choices=["heads", "tails"],
                        help="override the coin flip (for testing)")
    parser.add_argument("--ticker", help="force a ticker on the heads branch")
    parser.add_argument("--work-order", default=DEFAULT_WORK_ORDER,
                        help="work order label (default: %(default)s)")
    parser.add_argument("--tickers-file", help="path to a ticker universe file")
    parser.add_argument("--runs-dir", help="override the runs/ output directory")
    parser.add_argument("--no-log", action="store_true",
                        help="skip writing run logs")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)

    ctx = collect_context(args.work_order)
    branch = flip_coin(args.force)
    if branch == "tails":
        branch_out = run_tails(ctx)
    else:
        branch_out = run_heads(ctx, args.ticker, args.tickers_file)

    print(branch_out["printed"])

    result = build_result(ctx, branch_out)
    if not args.no_log:
        result_path = write_logs(result, args.runs_dir)
        rel = os.path.relpath(str(result_path), str(HERE))
        print("{} log: {}".format(SYMBOL_ACTIVE, rel), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
