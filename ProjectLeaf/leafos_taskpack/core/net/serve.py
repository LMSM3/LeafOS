#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""LeafOS LAN distribution server -- core/net/serve.py

Bundle the repo, serve it over plain HTTP on the LAN, and let remote nodes
pull it with a single command.  No external dependencies; stdlib only.

Commands
--------
  serve   [--port N] [--host IP] [--once] [--no-rebuild]
              Build dist/ bundles and start HTTP server.
  download HOST[:PORT] [FILE] [--dest DIR] [--verify]
              Pull a bundle from a running serve node.
  build   [--out DIR]
              Build bundles only; do not start server.
  info    HOST[:PORT]
              Print the remote node's manifest (file list + checksums).

Terminal layout while serving
------------------------------
  ┌──────────────────────────────────────────────────┐
  │  LeafOS v0.5.0  SERVE  ◉ ACTIVE  192.168.4.44   │
  │  port  7771   pid  1234   requests  0             │
  ├──────────────────────────────────────────────────┤
  │  dist/leafos-0.5.0.tar.gz   1.2 MB               │
  │    sha256: abcd1234...                            │
  │  dist/leafos-0.5.0.zip      1.3 MB                │
  │    sha256: ef567890...                            │
  ├──────────────────────────────────────────────────┤
  │  pull from another node:                         │
  │    leaf download 192.168.4.44                    │
  │    curl http://192.168.4.44:7771/manifest.json   │
  └──────────────────────────────────────────────────┘
"""

import argparse
import hashlib
import http.server
import json
import os
import shutil
import socket
import sys
import tarfile
import threading
import time
import urllib.request
import zipfile
from datetime import datetime

# ---------------------------------------------------------------------------
# UTF-8 safety
# ---------------------------------------------------------------------------
for _s in ("stdout", "stderr"):
    _st = getattr(sys, _s, None)
    _rc = getattr(_st, "reconfigure", None)
    if _rc:
        try:
            _rc(encoding="utf-8", errors="backslashreplace")
        except (ValueError, OSError):
            pass

# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------
_HERE   = os.path.dirname(os.path.abspath(__file__))
_ROOT   = os.path.normpath(os.path.join(_HERE, "..", ".."))
_DIST   = os.path.join(_ROOT, "dist")
_WEB    = os.path.join(_ROOT, "core", "web")
DEFAULT_PORT = 7771

if _WEB not in sys.path:
    sys.path.insert(0, _WEB)
try:
    from state import build_state as _build_web_state
except Exception:
    _build_web_state = None
try:
    from midend import action_route as _midend_action_route, route as _midend_route
except Exception:
    _midend_route = None
    _midend_action_route = None

_EXCLUDE_PATTERNS = (
    ".git", ".vs", "__pycache__", ".pyc", "build", ".DS_Store",
    "dist",  # don't bundle dist/ into itself
)


# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------
def _read_version():
    vf = os.path.join(_ROOT, "VERSION")
    try:
        if os.path.isfile(vf):
            v = open(vf, encoding="utf-8").read().strip()
            if v:
                return v
    except OSError:
        pass
    return "0.5.0"

VERSION = _read_version()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _local_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _human_size(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return "{:.1f} {}".format(n, unit)
        n /= 1024
    return "{:.1f} TB".format(n)


def _web_state_payload():
    if _build_web_state is None:
        return {
            "schema_version": 1,
            "leafos_object": "web_state",
            "available": False,
            "coding_backend_choice": {
                "language": "python",
                "model_key": "gemma4-coder",
                "tier": "builder",
                "backend": "python",
            },
            "remote_metadata": {"source": "unavailable"},
        }
    try:
        return _build_web_state(refresh_metadata=False, write_cache=False)
    except Exception as exc:
        return {
            "schema_version": 1,
            "leafos_object": "web_state",
            "available": False,
            "error": str(exc),
            "coding_backend_choice": {
                "language": "python",
                "model_key": "gemma4-coder",
                "tier": "builder",
                "backend": "python",
            },
            "remote_metadata": {"source": "steady-state-error-fallback"},
        }


def _should_exclude(path):
    parts = path.replace("\\", "/").split("/")
    for part in parts:
        for pat in _EXCLUDE_PATTERNS:
            if part == pat or part.endswith(pat):
                return True
    return False


# ---------------------------------------------------------------------------
# Bundle builder
# ---------------------------------------------------------------------------
def build_bundles(out_dir=None):
    """Build .tar.gz and .zip bundles; return list of {name,path,size,sha256}."""
    out_dir = out_dir or _DIST
    os.makedirs(out_dir, exist_ok=True)

    base = "leafos-{}".format(VERSION)
    tgz_path = os.path.join(out_dir, base + ".tar.gz")
    zip_path = os.path.join(out_dir, base + ".zip")

    print("  building {}  ...".format(os.path.basename(tgz_path)), end="", flush=True)
    with tarfile.open(tgz_path, "w:gz") as tf:
        for dirpath, dirnames, filenames in os.walk(_ROOT):
            rel_dir = os.path.relpath(dirpath, _ROOT)
            if _should_exclude(rel_dir):
                dirnames[:] = []
                continue
            dirnames[:] = [d for d in dirnames if not _should_exclude(d)]
            for fname in filenames:
                if _should_exclude(fname):
                    continue
                full = os.path.join(dirpath, fname)
                arc  = os.path.join(base, rel_dir, fname).replace("\\", "/")
                tf.add(full, arcname=arc)
    print(" done")

    print("  building {}  ...".format(os.path.basename(zip_path)), end="", flush=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for dirpath, dirnames, filenames in os.walk(_ROOT):
            rel_dir = os.path.relpath(dirpath, _ROOT)
            if _should_exclude(rel_dir):
                dirnames[:] = []
                continue
            dirnames[:] = [d for d in dirnames if not _should_exclude(d)]
            for fname in filenames:
                if _should_exclude(fname):
                    continue
                full = os.path.join(dirpath, fname)
                arc  = os.path.join(base, rel_dir, fname).replace("\\", "/")
                zf.write(full, arc)
    print(" done")

    bundles = []
    for p in (tgz_path, zip_path):
        bundles.append({
            "name":   os.path.basename(p),
            "path":   p,
            "size":   os.path.getsize(p),
            "sha256": _sha256(p),
        })

    # write manifest.json
    manifest = {
        "leafos_object": "manifest",
        "version":       VERSION,
        "built_at":      datetime.now().astimezone().isoformat(timespec="seconds"),
        "host_ip":       _local_ip(),
        "web_state": {
            "endpoint": "/web-state.json",
            "api_endpoint": "/api/state",
            "metadata_refresh": "manual via leaf web-state --refresh-metadata --write",
        },
        "bundles":       [{"name": b["name"], "size": b["size"], "sha256": b["sha256"]}
                          for b in bundles],
    }
    mf_path = os.path.join(out_dir, "manifest.json")
    with open(mf_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)

    return bundles


# ---------------------------------------------------------------------------
# HTTP request handler
# ---------------------------------------------------------------------------
class _LeafHandler(http.server.BaseHTTPRequestHandler):

    def log_message(self, fmt, *args):
        # route to our counter instead of stderr
        msg = fmt % args
        _REQ_COUNT[0] += 1
        ts = datetime.now().strftime("%H:%M:%S")
        print("  [{ts}] {addr}  {msg}".format(
            ts=ts, addr=self.client_address[0], msg=msg.strip()))

    def do_GET(self):
        if _midend_route is not None:
            response = _midend_route(self.path)
            if response is not None:
                status, content_type, payload = response
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", "no-store" if content_type.startswith("application/json") else "no-cache")
                self.send_header("X-LeafOS-Version", VERSION)
                self.send_header("X-LeafOS-Authority", "read-only-midend")
                self.end_headers()
                self.wfile.write(payload)
                if _ONCE[0]:
                    threading.Thread(target=_shutdown_server, daemon=True).start()
                return
        path = self.path.lstrip("/") or "manifest.json"
        if path in ("web-state.json", "api/state", "api/runtime"):
            payload = json.dumps(_web_state_payload(), indent=2, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("X-LeafOS-Version", VERSION)
            self.end_headers()
            self.wfile.write(payload)
            if _ONCE[0]:
                threading.Thread(target=_shutdown_server, daemon=True).start()
            return
        full = os.path.join(_DIST, path)
        if not os.path.isfile(full):
            self.send_error(404, "Not found")
            return
        size = os.path.getsize(full)
        self.send_response(200)
        if path.endswith(".gz"):
            self.send_header("Content-Type", "application/gzip")
        elif path.endswith(".zip"):
            self.send_header("Content-Type", "application/zip")
        else:
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(size))
        self.send_header("X-LeafOS-Version", VERSION)
        self.end_headers()
        with open(full, "rb") as fh:
            shutil.copyfileobj(fh, self.wfile)
        if _ONCE[0]:
            threading.Thread(target=_shutdown_server, daemon=True).start()

    def do_POST(self):
        if _midend_action_route is None:
            self.send_error(503, "Native midend admission unavailable")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_error(400, "Invalid content length")
            return
        body = self.rfile.read(min(length, 16385))
        response = _midend_action_route(self.path, body)
        if response is None:
            self.send_error(404, "Not found")
            return
        status, content_type, payload = response
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-LeafOS-Version", VERSION)
        self.send_header("X-LeafOS-Authority", "native-inlet-admission")
        self.end_headers()
        self.wfile.write(payload)


_REQ_COUNT = [0]
_ONCE      = [False]
_SERVER    = [None]


def _shutdown_server():
    time.sleep(0.3)
    if _SERVER[0]:
        _SERVER[0].shutdown()


# ---------------------------------------------------------------------------
# Terminal banner
# ---------------------------------------------------------------------------
_ANSI_RESET  = "\033[0m"
_ANSI_BOLD   = "\033[1m"
_ANSI_CYAN   = "\033[1;36m"
_ANSI_GREEN  = "\033[1;32m"
_ANSI_DIM    = "\033[2m"
_ANSI_YELLOW = "\033[1;33m"


def _banner(bundles, ip, port):
    W = 60
    hl = "\u2500" * (W - 2)
    t  = "\u250c" + hl + "\u2510"
    b  = "\u2514" + hl + "\u2518"
    d  = "\u251c" + hl + "\u2524"

    def row(s):
        vis = len(s.encode("utf-8"))  # approximate; fine for ASCII-heavy lines
        import re
        vis = len(re.sub(r"\033\[[0-9;]*m", "", s))
        pad = max(0, W - 2 - vis)
        return "\u2502 " + s + " " * pad + " \u2502"

    lines = [
        t,
        row("{}LeafOS v{}{}  {}SERVE{}  {}◉ ACTIVE{}  {}{}{}".format(
            _ANSI_BOLD, VERSION, _ANSI_RESET,
            _ANSI_CYAN, _ANSI_RESET,
            _ANSI_GREEN, _ANSI_RESET,
            _ANSI_DIM, ip, _ANSI_RESET,
        )),
        row("{}port{} {:5d}   {}pid{} {:6d}   {}requests{} {}".format(
            _ANSI_DIM, _ANSI_RESET, port,
            _ANSI_DIM, _ANSI_RESET, os.getpid(),
            _ANSI_DIM, _ANSI_RESET, "0",
        )),
        d,
    ]
    for b_info in bundles:
        lines.append(row("  {}{:<38}{}  {}{}{}".format(
            _ANSI_CYAN, b_info["name"], _ANSI_RESET,
            _ANSI_DIM, _human_size(b_info["size"]), _ANSI_RESET,
        )))
        lines.append(row("    {}sha256:{} {}{}{}".format(
            _ANSI_DIM, _ANSI_RESET,
            _ANSI_DIM, b_info["sha256"][:48] + "...", _ANSI_RESET,
        )))
    lines += [
        d,
        row("  {}pull from another node on this LAN:{}".format(_ANSI_BOLD, _ANSI_RESET)),
        row("    {}leaf download {}{}".format(_ANSI_YELLOW, ip, _ANSI_RESET)),
        row("    {}leaf download {}:{} {}{}".format(
            _ANSI_DIM, ip, port, bundles[0]["name"] if bundles else "", _ANSI_RESET)),
        row("    {}curl http://{}:{}/manifest.json{}".format(
            _ANSI_DIM, ip, port, _ANSI_RESET)),
        b,
        row("  {}Ctrl-C to stop{}".format(_ANSI_DIM, _ANSI_RESET)),
        "\u2514" + "\u2500" * (W - 2) + "\u2518",
    ]
    # last line duplicated; trim
    lines = lines[:-1]
    print("\n".join(lines))


# ---------------------------------------------------------------------------
# serve command
# ---------------------------------------------------------------------------
def cmd_serve(args):
    ip   = args.host or _local_ip()
    port = args.port

    if not args.no_rebuild:
        print("\n{}building bundles ...{}".format(_ANSI_BOLD, _ANSI_RESET))
        bundles = build_bundles()
    else:
        bundles = []
        if os.path.isdir(_DIST):
            for fname in sorted(os.listdir(_DIST)):
                if fname.endswith((".tar.gz", ".zip")):
                    p = os.path.join(_DIST, fname)
                    bundles.append({
                        "name":   fname,
                        "path":   p,
                        "size":   os.path.getsize(p),
                        "sha256": _sha256(p),
                    })
        if not bundles:
            print("no bundles in dist/ — rebuilding")
            bundles = build_bundles()

    _ONCE[0] = args.once
    print()
    _banner(bundles, ip, port)
    print()

    server = http.server.HTTPServer((ip, port), _LeafHandler)
    _SERVER[0] = server
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n{}serve stopped{}".format(_ANSI_DIM, _ANSI_RESET))


# ---------------------------------------------------------------------------
# build command
# ---------------------------------------------------------------------------
def cmd_build(args):
    out = args.out or _DIST
    print("{}building LeafOS v{} bundles → {}{}".format(
        _ANSI_BOLD, VERSION, out, _ANSI_RESET))
    bundles = build_bundles(out_dir=out)
    for b in bundles:
        print("  {}{:<40}{} {}{}{}".format(
            _ANSI_CYAN, b["name"], _ANSI_RESET,
            _ANSI_DIM, _human_size(b["size"]), _ANSI_RESET,
        ))
        print("    sha256: {}".format(b["sha256"]))


# ---------------------------------------------------------------------------
# info command
# ---------------------------------------------------------------------------
def cmd_info(args):
    host = args.host_port
    if ":" not in host:
        host = "{}:{}".format(host, DEFAULT_PORT)
    url = "http://{}/manifest.json".format(host)
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        print("error: {}".format(exc), file=sys.stderr)
        return 1
    print(json.dumps(data, indent=2))
    return 0


# ---------------------------------------------------------------------------
# download command
# ---------------------------------------------------------------------------
def cmd_download(args):
    host = args.host_port
    if ":" not in host:
        host = "{}:{}".format(host, DEFAULT_PORT)

    dest_dir = args.dest or os.getcwd()
    os.makedirs(dest_dir, exist_ok=True)

    # fetch manifest
    mf_url = "http://{}/manifest.json".format(host)
    print("{}fetching manifest from {}{}".format(_ANSI_BOLD, mf_url, _ANSI_RESET))
    try:
        with urllib.request.urlopen(mf_url, timeout=8) as resp:
            manifest = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        print("error: {}".format(exc), file=sys.stderr)
        return 1

    bundles = manifest.get("bundles", [])
    if not bundles:
        print("no bundles in manifest", file=sys.stderr)
        return 1

    # pick file — prefer tar.gz by default; or match explicit request
    target_name = args.file
    if target_name:
        chosen = next((b for b in bundles if b["name"] == target_name), None)
        if not chosen:
            print("file '{}' not in manifest".format(target_name), file=sys.stderr)
            return 1
    else:
        chosen = next((b for b in bundles if b["name"].endswith(".tar.gz")), bundles[0])

    url  = "http://{}/{}".format(host, chosen["name"])
    dest = os.path.join(dest_dir, chosen["name"])
    size = chosen["size"]

    print("  {}→ {}{}  ({})".format(
        _ANSI_CYAN, chosen["name"], _ANSI_RESET, _human_size(size)))
    print("  url : {}{}{}".format(_ANSI_DIM, url, _ANSI_RESET))

    # stream download with progress bar
    downloaded = 0
    bar_width  = 40
    t0 = time.time()
    try:
        with urllib.request.urlopen(url, timeout=60) as resp, \
                open(dest, "wb") as out_fh:
            while True:
                chunk = resp.read(65536)
                if not chunk:
                    break
                out_fh.write(chunk)
                downloaded += len(chunk)
                pct = min(downloaded / size, 1.0) if size else 0
                filled = int(pct * bar_width)
                bar = "\u2588" * filled + "\u2591" * (bar_width - filled)
                elapsed = time.time() - t0
                rate = downloaded / elapsed if elapsed > 0 else 0
                sys.stdout.write(
                    "\r  [{}] {:5.1f}%  {}  {:>8}/s  ".format(
                        bar, pct * 100,
                        _human_size(downloaded),
                        _human_size(rate),
                    )
                )
                sys.stdout.flush()
    except Exception as exc:
        print("\nerror: {}".format(exc), file=sys.stderr)
        return 1

    elapsed = time.time() - t0
    print("\n  {}done{} in {:.1f}s  →  {}".format(
        _ANSI_GREEN, _ANSI_RESET, elapsed, dest))

    # verify checksum
    if args.verify or True:   # always verify
        print("  verifying sha256 ...", end="", flush=True)
        actual = _sha256(dest)
        expected = chosen["sha256"]
        if actual == expected:
            print("  {}OK{}".format(_ANSI_GREEN, _ANSI_RESET))
        else:
            print("  {}MISMATCH{}".format("\033[1;31m", _ANSI_RESET))
            print("    expected: {}".format(expected))
            print("    got:      {}".format(actual))
            return 1

    print("\n  to install:")
    if dest.endswith(".tar.gz"):
        print("    tar -xzf {}".format(dest))
        print("    bash {}/bin/install_demo.sh".format(
            dest.replace(".tar.gz", "")))
    elif dest.endswith(".zip"):
        print("    unzip {}".format(dest))
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def build_parser():
    p = argparse.ArgumentParser(
        prog="serve.py",
        description="LeafOS LAN distribution server and pull client",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # serve
    ps = sub.add_parser("serve", help="build bundles and start HTTP server")
    ps.add_argument("--port", type=int, default=DEFAULT_PORT,
                    help="TCP port (default {})".format(DEFAULT_PORT))
    ps.add_argument("--host", default=None,
                    help="bind address (default: local LAN IP)")
    ps.add_argument("--once", action="store_true",
                    help="shutdown after the first completed download")
    ps.add_argument("--no-rebuild", action="store_true",
                    help="skip bundle rebuild if dist/ already has bundles")

    # build
    pb = sub.add_parser("build", help="build bundles only, do not serve")
    pb.add_argument("--out", default=None, help="output directory (default: dist/)")

    # download
    pd = sub.add_parser("download", help="pull a bundle from a serve node")
    pd.add_argument("host_port", help="HOST or HOST:PORT of the serve node")
    pd.add_argument("file", nargs="?", default=None,
                    help="specific filename to download (default: .tar.gz)")
    pd.add_argument("--dest", default=None,
                    help="destination directory (default: current dir)")
    pd.add_argument("--verify", action="store_true",
                    help="verify SHA256 after download (always enabled)")

    # info
    pi = sub.add_parser("info", help="print manifest from a remote serve node")
    pi.add_argument("host_port", help="HOST or HOST:PORT")

    return p


def main():
    parser = build_parser()
    args   = parser.parse_args()
    dispatch = {
        "serve":    cmd_serve,
        "build":    cmd_build,
        "download": cmd_download,
        "info":     cmd_info,
    }
    fn = dispatch.get(args.cmd)
    if fn:
        raise SystemExit(fn(args) or 0)


if __name__ == "__main__":
    main()
