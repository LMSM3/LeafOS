#!/usr/bin/env python3
"""Small, optional foreground-activity probes for resident scheduling."""

from __future__ import annotations

import ctypes
import os
import time
from typing import Callable


class _LastInputInfo(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def input_idle_seconds() -> float | None:
    """Return Windows local-input idle time, or None when unsupported."""
    if os.name != "nt":
        return None
    info = _LastInputInfo()
    info.cbSize = ctypes.sizeof(info)
    try:
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
            return None
        elapsed_ms = (ctypes.windll.kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF
        return max(0.0, elapsed_ms / 1000.0)
    except (AttributeError, OSError):
        return None


class ResponsivenessProbe:
    """Measure supervisor wakeup delay without touching foreground processes."""

    def __init__(self, interval: float, clock: Callable[[], float] = time.monotonic):
        self.interval = max(0.01, float(interval))
        self.clock = clock
        self.last = self.clock()

    def sample(self) -> float:
        now = self.clock()
        delay = max(0.0, now - self.last - self.interval) * 1000.0
        self.last = now
        return round(delay, 3)
