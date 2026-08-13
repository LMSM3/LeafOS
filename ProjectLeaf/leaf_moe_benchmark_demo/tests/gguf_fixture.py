from __future__ import annotations

import struct
from pathlib import Path
from typing import Any, Iterable, Sequence, Tuple


UINT32 = 4
STRING = 8
ARRAY = 9


def _string(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return struct.pack("<Q", len(encoded)) + encoded


def write_fake_gguf(
    path: Path,
    metadata: Iterable[Tuple[str, int, Any]],
    tensors: Iterable[Tuple[str, Sequence[int], int, int]] = (),
) -> None:
    items = list(metadata)
    tensor_items = list(tensors)
    payload = bytearray()
    payload.extend(b"GGUF")
    payload.extend(struct.pack("<IQQ", 3, len(tensor_items), len(items)))
    for key, value_type, value in items:
        payload.extend(_string(key))
        payload.extend(struct.pack("<I", value_type))
        if value_type == STRING:
            payload.extend(_string(str(value)))
        elif value_type == UINT32:
            payload.extend(struct.pack("<I", int(value)))
        elif value_type == ARRAY:
            element_type, values = value
            payload.extend(struct.pack("<IQ", int(element_type), len(values)))
            if element_type == STRING:
                for item in values:
                    payload.extend(_string(str(item)))
            elif element_type == UINT32:
                for item in values:
                    payload.extend(struct.pack("<I", int(item)))
            else:
                raise ValueError("Unsupported test array type")
        else:
            raise ValueError("Unsupported test value type")
    for name, dimensions, tensor_type, offset in tensor_items:
        payload.extend(_string(name))
        payload.extend(struct.pack("<I", len(dimensions)))
        for dimension in dimensions:
            payload.extend(struct.pack("<Q", int(dimension)))
        payload.extend(struct.pack("<IQ", int(tensor_type), int(offset)))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def qwen_metadata(name: str = "Qwen Demo 35B A3B"):
    return [
        ("general.name", STRING, name),
        ("general.architecture", STRING, "qwen35moe"),
        ("qwen35moe.block_count", UINT32, 40),
        ("qwen35moe.context_length", UINT32, 32768),
        ("qwen35moe.embedding_length", UINT32, 2048),
        ("qwen35moe.expert_count", UINT32, 93),
        ("qwen35moe.expert_used_count", UINT32, 8),
        ("tokenizer.ggml.tokens", ARRAY, (STRING, ["a", "b", "c"])),
    ]
