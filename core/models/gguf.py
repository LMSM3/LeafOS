from __future__ import annotations

import hashlib
import re
import struct
from pathlib import Path
from typing import Any, BinaryIO


class GGUFError(ValueError):
    pass


_FIXED = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 1, 10: 8, 11: 8, 12: 8}
_UNPACK = {0: "<B", 1: "<b", 2: "<H", 3: "<h", 4: "<I", 5: "<i", 6: "<f", 7: "<?", 10: "<Q", 11: "<q", 12: "<d"}
_FILE_TYPES = {
    0: "F32", 1: "F16", 2: "Q4_0", 3: "Q4_1", 7: "Q8_0", 8: "Q5_0", 9: "Q5_1",
    10: "Q2_K", 11: "Q3_K_S", 12: "Q3_K_M", 13: "Q3_K_L", 14: "Q4_K_S",
    15: "Q4_K_M", 16: "Q5_K_S", 17: "Q5_K_M", 18: "Q6_K", 19: "IQ2_XXS",
    20: "IQ2_XS", 21: "IQ3_XXS", 22: "IQ1_S", 23: "IQ4_NL", 24: "IQ3_S",
    25: "IQ2_S", 26: "IQ4_XS", 27: "I8", 28: "I16", 29: "I32", 30: "I64",
    31: "F64", 32: "IQ1_M", 33: "BF16", 34: "Q4_0_4_4", 35: "Q4_0_4_8",
    36: "Q4_0_8_8", 37: "TQ1_0", 38: "TQ2_0",
}
_GGML_BLOCK_BYTES = {
    0: (1, 4), 1: (1, 2), 2: (32, 18), 3: (32, 20), 6: (32, 22), 7: (32, 24),
    8: (32, 34), 9: (32, 40), 10: (256, 84), 11: (256, 110), 12: (256, 144),
    13: (256, 176), 14: (256, 210), 15: (256, 292), 16: (256, 66), 17: (256, 74),
    18: (256, 98), 19: (256, 50), 20: (32, 18), 21: (256, 110), 22: (256, 82),
    23: (256, 136), 24: (1, 1), 25: (1, 2), 26: (1, 4), 27: (1, 8),
    28: (256, 56), 30: (1, 2),
}
_QUANT_PATTERN = re.compile(
    r"(?:^|[-_.])(IQ[1-4]_[A-Z0-9_]+|Q[2-8](?:_K(?:_[SML])?|_[01])|BF16|F16|F32|MXFP4(?:_MOE)?)(?:[-_.]|$)",
    re.I,
)


def _read_exact(stream: BinaryIO, size: int) -> bytes:
    value = stream.read(size)
    if len(value) != size:
        raise GGUFError("truncated GGUF metadata")
    return value


def _u32(stream: BinaryIO) -> int:
    return struct.unpack("<I", _read_exact(stream, 4))[0]


def _u64(stream: BinaryIO) -> int:
    return struct.unpack("<Q", _read_exact(stream, 8))[0]


def _string(stream: BinaryIO, *, keep: bool = True) -> str | None:
    length = _u64(stream)
    if length > 64 * 1024 * 1024:
        raise GGUFError(f"unreasonable GGUF string length: {length}")
    if keep:
        return _read_exact(stream, length).decode("utf-8", errors="replace")
    stream.seek(length, 1)
    return None


def _read_value(stream: BinaryIO, value_type: int) -> Any:
    if value_type in _UNPACK:
        return struct.unpack(_UNPACK[value_type], _read_exact(stream, _FIXED[value_type]))[0]
    if value_type == 8:
        return _string(stream)
    raise GGUFError(f"unsupported GGUF metadata type: {value_type}")


def _skip_value(stream: BinaryIO, value_type: int) -> None:
    if value_type in _FIXED:
        stream.seek(_FIXED[value_type], 1)
        return
    if value_type == 8:
        _string(stream, keep=False)
        return
    if value_type == 9:
        element_type = _u32(stream)
        count = _u64(stream)
        if count > 100_000_000:
            raise GGUFError(f"unreasonable GGUF array length: {count}")
        if element_type in _FIXED:
            stream.seek(_FIXED[element_type] * count, 1)
            return
        for _ in range(count):
            _skip_value(stream, element_type)
        return
    raise GGUFError(f"unsupported GGUF metadata type: {value_type}")


def _quant_from_name(path: Path) -> str:
    match = _QUANT_PATTERN.search(path.name)
    return match.group(1).upper() if match else "unknown"


def inspect_gguf(path: Path, runtime_available: bool) -> dict[str, Any]:
    path = path.expanduser().resolve()
    size = path.stat().st_size
    metadata: dict[str, Any] = {}
    with path.open("rb") as stream:
        if _read_exact(stream, 4) != b"GGUF":
            raise GGUFError("missing GGUF magic")
        version = _u32(stream)
        if version not in {2, 3}:
            raise GGUFError(f"unsupported GGUF version: {version}")
        tensor_count = _u64(stream)
        kv_count = _u64(stream)
        if kv_count > 10_000_000 or tensor_count > 10_000_000:
            raise GGUFError("unreasonable GGUF header counts")
        wanted = {"general.architecture", "general.name", "general.file_type", "general.alignment"}
        for _ in range(kv_count):
            key = _string(stream)
            value_type = _u32(stream)
            if key in wanted:
                metadata[key] = _read_value(stream, value_type)
            else:
                _skip_value(stream, value_type)
        tensor_ends: list[int] = []
        for _ in range(tensor_count):
            _string(stream, keep=False)
            dimensions = _u32(stream)
            if dimensions > 8:
                raise GGUFError(f"unreasonable tensor dimension count: {dimensions}")
            elements = 1
            for _ in range(dimensions):
                elements *= _u64(stream)
            tensor_type = _u32(stream)
            offset = _u64(stream)
            layout = _GGML_BLOCK_BYTES.get(tensor_type)
            if layout:
                block, block_bytes = layout
                tensor_bytes = ((elements + block - 1) // block) * block_bytes
                tensor_ends.append(offset + tensor_bytes)
            else:
                tensor_ends.append(offset + 1)
        alignment = metadata.get("general.alignment", 32)
        if not isinstance(alignment, int) or alignment <= 0 or alignment > 65536:
            raise GGUFError(f"invalid GGUF alignment: {alignment}")
        data_start = ((stream.tell() + alignment - 1) // alignment) * alignment
        required_size = data_start + max(tensor_ends, default=0)
        if tensor_count and size < required_size:
            raise GGUFError(f"truncated GGUF tensor data: {size} bytes present, at least {required_size} required")
    architecture = str(metadata.get("general.architecture") or "unknown")
    file_type = metadata.get("general.file_type")
    quant = _FILE_TYPES.get(file_type, _quant_from_name(path)) if isinstance(file_type, int) else _quant_from_name(path)
    model_name = str(metadata.get("general.name") or path.stem)
    normalized = f"{model_name}\0{quant}\0{size}".casefold().encode("utf-8")
    slug = re.sub(r"[^a-z0-9]+", "-", path.stem.casefold()).strip("-")[:52] or "model"
    runtime_compatible = bool(runtime_available and architecture != "unknown")
    return {
        "id": f"{slug}-{hashlib.sha1(normalized).hexdigest()[:8]}",
        "path": str(path),
        "name": model_name,
        "size_bytes": size,
        "mtime_ns": path.stat().st_mtime_ns,
        "quant": quant,
        "architecture": architecture,
        "gguf_version": version,
        "tensor_count": tensor_count,
        "required_size_bytes": required_size,
        "runtime_compatible": runtime_compatible,
        "runtime_compatibility": "preflight" if runtime_compatible else "unavailable",
        "load_status": "not_loaded",
        "error": None,
    }
