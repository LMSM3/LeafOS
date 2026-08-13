"""Bounded GGUF metadata reader.

The reader touches only the GGUF header and metadata area. It never maps tensor
payloads and intentionally does not retain large tokenizer arrays.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Dict, Optional


class GGUFError(ValueError):
    pass


@dataclass(frozen=True)
class GGUFHeader:
    version: int
    tensor_count: int
    parameter_count: int
    metadata_count: int
    metadata: Dict[str, Any]
    metadata_bytes_read: int
    tensor_info_bytes_read: int


_SCALAR_FORMATS = {
    0: "B",   # UINT8
    1: "b",   # INT8
    2: "H",   # UINT16
    3: "h",   # INT16
    4: "I",   # UINT32
    5: "i",   # INT32
    6: "f",   # FLOAT32
    7: "?",   # BOOL
    10: "Q",  # UINT64
    11: "q",  # INT64
    12: "d",  # FLOAT64
}
_STRING = 8
_ARRAY = 9
_MAX_STRING_BYTES = 64 * 1024 * 1024
_MAX_ARRAY_ITEMS = 4_000_000
_MAX_TENSORS = 1_000_000
_MAX_TENSOR_DIMENSIONS = 4


def _read_exact(handle: BinaryIO, length: int) -> bytes:
    data = handle.read(length)
    if len(data) != length:
        raise GGUFError(f"Unexpected end of file while reading {length} bytes")
    return data


def _read_struct(handle: BinaryIO, fmt: str) -> Any:
    size = struct.calcsize("<" + fmt)
    return struct.unpack("<" + fmt, _read_exact(handle, size))[0]


def _read_length(handle: BinaryIO) -> int:
    return int(_read_struct(handle, "Q"))


def _read_string(handle: BinaryIO, retain: bool) -> Optional[str]:
    length = _read_length(handle)
    if length > _MAX_STRING_BYTES:
        raise GGUFError(f"GGUF string length {length} exceeds the safety bound")
    if retain:
        return _read_exact(handle, length).decode("utf-8", errors="replace")
    handle.seek(length, 1)
    return None


def _read_or_skip_value(handle: BinaryIO, value_type: int, retain: bool, depth: int = 0) -> Any:
    if depth > 2:
        raise GGUFError("Nested GGUF metadata arrays exceed the supported depth")
    if value_type in _SCALAR_FORMATS:
        value = _read_struct(handle, _SCALAR_FORMATS[value_type])
        return value if retain else None
    if value_type == _STRING:
        return _read_string(handle, retain)
    if value_type == _ARRAY:
        element_type = int(_read_struct(handle, "I"))
        count = _read_length(handle)
        if count > _MAX_ARRAY_ITEMS:
            raise GGUFError(f"GGUF metadata array length {count} exceeds the safety bound")
        if element_type in _SCALAR_FORMATS:
            size = struct.calcsize("<" + _SCALAR_FORMATS[element_type])
            if retain and count <= 256:
                return [_read_struct(handle, _SCALAR_FORMATS[element_type]) for _ in range(count)]
            handle.seek(size * count, 1)
            return {"array_type": element_type, "count": count} if retain else None
        if element_type == _STRING:
            if retain and count <= 64:
                return [_read_string(handle, True) for _ in range(count)]
            for _ in range(count):
                _read_string(handle, False)
            return {"array_type": element_type, "count": count} if retain else None
        if element_type == _ARRAY:
            values = [] if retain and count <= 16 else None
            for _ in range(count):
                item = _read_or_skip_value(handle, element_type, values is not None, depth + 1)
                if values is not None:
                    values.append(item)
            return values if values is not None else ({"array_type": element_type, "count": count} if retain else None)
        raise GGUFError(f"Unsupported GGUF array element type: {element_type}")
    raise GGUFError(f"Unsupported GGUF metadata value type: {value_type}")


def _retain_key(key: str) -> bool:
    if key in {
        "general.name",
        "general.architecture",
        "general.file_type",
        "general.quantization_version",
    }:
        return True
    suffixes = (
        ".block_count",
        ".context_length",
        ".embedding_length",
        ".expert_count",
        ".expert_used_count",
        ".expert_shared_count",
        ".attention.head_count",
        ".attention.head_count_kv",
    )
    return key.endswith(suffixes)


def read_gguf_header(path: Path) -> GGUFHeader:
    source = path.expanduser().resolve()
    with source.open("rb") as handle:
        if _read_exact(handle, 4) != b"GGUF":
            raise GGUFError("Invalid GGUF magic")
        version = int(_read_struct(handle, "I"))
        if version not in {2, 3}:
            raise GGUFError(f"Unsupported GGUF version: {version}")
        tensor_count = int(_read_struct(handle, "Q"))
        metadata_count = int(_read_struct(handle, "Q"))
        if tensor_count > _MAX_TENSORS:
            raise GGUFError(f"Tensor count {tensor_count} exceeds the safety bound")
        if metadata_count > 1_000_000:
            raise GGUFError(f"Metadata count {metadata_count} exceeds the safety bound")

        metadata: Dict[str, Any] = {}
        for _ in range(metadata_count):
            key = _read_string(handle, True)
            if key is None:
                raise GGUFError("Metadata key unexpectedly missing")
            value_type = int(_read_struct(handle, "I"))
            retain = _retain_key(key)
            value = _read_or_skip_value(handle, value_type, retain)
            if retain:
                metadata[key] = value

        metadata_bytes_read = handle.tell()
        parameter_count = 0
        for _ in range(tensor_count):
            _read_string(handle, False)
            dimension_count = int(_read_struct(handle, "I"))
            if dimension_count <= 0 or dimension_count > _MAX_TENSOR_DIMENSIONS:
                raise GGUFError(
                    f"GGUF tensor dimension count {dimension_count} is outside 1..{_MAX_TENSOR_DIMENSIONS}"
                )
            tensor_parameters = 1
            for _ in range(dimension_count):
                dimension = int(_read_struct(handle, "Q"))
                if dimension <= 0:
                    raise GGUFError("GGUF tensor dimensions must be positive")
                tensor_parameters *= dimension
            _read_struct(handle, "I")  # ggml_type
            _read_struct(handle, "Q")  # aligned tensor-data offset
            parameter_count += tensor_parameters

        if handle.tell() > source.stat().st_size:
            raise GGUFError("GGUF metadata or tensor descriptors extend beyond the end of the file")

        return GGUFHeader(
            version=version,
            tensor_count=tensor_count,
            parameter_count=parameter_count,
            metadata_count=metadata_count,
            metadata=metadata,
            metadata_bytes_read=metadata_bytes_read,
            tensor_info_bytes_read=handle.tell() - metadata_bytes_read,
        )
