#!/usr/bin/env python3
"""Bounded GGUF metadata reader for local runtime capability negotiation."""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Any, BinaryIO


class GGUFError(ValueError):
    pass


SCALARS = {
    0: "B", 1: "b", 2: "H", 3: "h", 4: "I", 5: "i",
    6: "f", 7: "?", 10: "Q", 11: "q", 12: "d",
}


def _read_exact(handle: BinaryIO, length: int) -> bytes:
    value = handle.read(length)
    if len(value) != length:
        raise GGUFError("truncated GGUF metadata")
    return value


def _u32(handle: BinaryIO) -> int:
    return struct.unpack("<I", _read_exact(handle, 4))[0]


def _u64(handle: BinaryIO) -> int:
    return struct.unpack("<Q", _read_exact(handle, 8))[0]


def _string(handle: BinaryIO) -> str:
    length = _u64(handle)
    if length > 16 * 1024 * 1024:
        raise GGUFError("GGUF metadata string exceeds safety limit")
    return _read_exact(handle, length).decode("utf-8", errors="replace")


def _value(handle: BinaryIO, value_type: int, depth: int = 0) -> Any:
    if depth > 2:
        raise GGUFError("nested GGUF metadata arrays are unsupported")
    if value_type in SCALARS:
        fmt = "<" + SCALARS[value_type]
        return struct.unpack(fmt, _read_exact(handle, struct.calcsize(fmt)))[0]
    if value_type == 8:
        return _string(handle)
    if value_type == 9:
        item_type = _u32(handle)
        length = _u64(handle)
        if length > 1_000_000:
            raise GGUFError("GGUF metadata array exceeds safety limit")
        return [_value(handle, item_type, depth + 1) for _ in range(length)]
    raise GGUFError(f"unsupported GGUF metadata type: {value_type}")


def read_metadata(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        if _read_exact(handle, 4) != b"GGUF":
            raise GGUFError("model is not a GGUF file")
        version = _u32(handle)
        if version not in {2, 3}:
            raise GGUFError(f"unsupported GGUF version: {version}")
        tensor_count = _u64(handle)
        metadata_count = _u64(handle)
        if metadata_count > 100_000:
            raise GGUFError("GGUF metadata entry count exceeds safety limit")
        metadata: dict[str, Any] = {}
        for _ in range(metadata_count):
            key = _string(handle)
            metadata[key] = _value(handle, _u32(handle))
    architecture = str(metadata.get("general.architecture", ""))
    context_keys = [
        f"{architecture}.context_length" if architecture else "",
        "llama.context_length", "context_length",
    ]
    context_limit = next((int(metadata[key]) for key in context_keys if key in metadata), None)
    return {
        "format": "GGUF", "version": version, "tensor_count": tensor_count,
        "metadata_count": metadata_count, "name": metadata.get("general.name"),
        "architecture": architecture or None, "context_length": context_limit,
        "metadata": metadata,
    }
