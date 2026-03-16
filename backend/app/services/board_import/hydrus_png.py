from __future__ import annotations

import json
import struct
import zlib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image

from app.services.board_import.hydrus_types import META_TYPE_NAMES, SERIALISABLE_TYPE_NAMES


@dataclass(slots=True)
class HydrusPngPayload:
    path: Path
    width: int
    height: int
    top_height: int
    payload_length: int
    payload_bytes: bytes


def _first_channel_bytes(image: Image.Image) -> bytes:
    if image.mode == "L":
        return image.tobytes()

    if image.mode == "P":
        image = image.convert("RGBA")

    bands = len(image.getbands())
    raw = image.tobytes()
    return raw[0::bands]


def decode_hydrus_png(path: str | Path) -> HydrusPngPayload:
    source = Path(path)
    image = Image.open(source)
    payload_source = _first_channel_bytes(image)
    width, height = image.size

    if len(payload_source) < 2:
        raise ValueError(f"{source} is too small to contain a Hydrus PNG header")

    top_height = struct.unpack("!H", payload_source[:2])[0]
    payload_offset = width * top_height

    if payload_offset + 4 > len(payload_source):
        raise ValueError(f"{source} has an invalid Hydrus PNG payload offset")

    payload_and_header = payload_source[payload_offset:]
    payload_length = struct.unpack("!I", payload_and_header[:4])[0]
    payload_start = 4
    payload_end = payload_start + payload_length

    if payload_end > len(payload_and_header):
        raise ValueError(f"{source} declared a payload larger than the image data")

    payload_bytes = payload_and_header[payload_start:payload_end]

    return HydrusPngPayload(
        path=source,
        width=width,
        height=height,
        top_height=top_height,
        payload_length=payload_length,
        payload_bytes=payload_bytes,
    )


def decompress_payload(payload_bytes: bytes) -> bytes:
    try:
        return zlib.decompress(payload_bytes)
    except zlib.error:
        return payload_bytes


def payload_to_text(payload_bytes: bytes) -> str:
    return decompress_payload(payload_bytes).decode("utf-8")


def payload_to_json(payload_bytes: bytes) -> Any:
    return json.loads(payload_to_text(payload_bytes))


def is_meta_tuple(value: Any) -> bool:
    return (
        isinstance(value, (list, tuple))
        and len(value) == 2
        and isinstance(value[0], int)
        and value[0] in META_TYPE_NAMES
    )


def is_serialisable_tuple(value: Any) -> bool:
    if not isinstance(value, (list, tuple)):
        return False

    if len(value) == 3:
        serialisable_type, version, _info = value
        return isinstance(serialisable_type, int) and isinstance(version, int)

    if len(value) == 4:
        serialisable_type, name, version, _info = value
        return (
            isinstance(serialisable_type, int)
            and isinstance(name, str)
            and isinstance(version, int)
        )

    return False


def _short_type_name(type_id: int) -> str:
    return SERIALISABLE_TYPE_NAMES.get(type_id, f"serialisable_type_{type_id}")


def inspect_hydrus_object(
    obj: Any,
    *,
    max_depth: int = 6,
    max_items: int = 25,
    _depth: int = 0,
) -> Any:
    if _depth >= max_depth:
        return {"kind": "truncated", "reason": "max_depth"}

    if is_meta_tuple(obj):
        meta_type, payload = obj
        meta_name = META_TYPE_NAMES.get(meta_type, f"meta_type_{meta_type}")

        if meta_type == 1 and isinstance(payload, str):
            preview = payload[:48]
            return {
                "kind": "meta",
                "meta_type": meta_name,
                "value_preview": preview,
                "value_length": len(payload),
            }

        return {
            "kind": "meta",
            "meta_type": meta_name,
            "value": inspect_hydrus_object(
                payload,
                max_depth=max_depth,
                max_items=max_items,
                _depth=_depth + 1,
            ),
        }

    if is_serialisable_tuple(obj):
        if len(obj) == 3:
            serialisable_type, version, info = obj
            name = None
        else:
            serialisable_type, name, version, info = obj

        result = {
            "kind": "serialisable",
            "type_id": serialisable_type,
            "type_name": _short_type_name(serialisable_type),
            "version": version,
        }

        if name is not None:
            result["name"] = name

        result["info"] = inspect_hydrus_object(
            info,
            max_depth=max_depth,
            max_items=max_items,
            _depth=_depth + 1,
        )
        return result

    if isinstance(obj, list):
        items = [
            inspect_hydrus_object(
                item,
                max_depth=max_depth,
                max_items=max_items,
                _depth=_depth + 1,
            )
            for item in obj[:max_items]
        ]
        result = {"kind": "list", "length": len(obj), "items": items}
        if len(obj) > max_items:
            result["truncated_items"] = len(obj) - max_items
        return result

    if isinstance(obj, dict):
        items: list[dict[str, Any]] = []
        for index, (key, value) in enumerate(obj.items()):
            if index >= max_items:
                break
            items.append(
                {
                    "key": inspect_hydrus_object(
                        key,
                        max_depth=max_depth,
                        max_items=max_items,
                        _depth=_depth + 1,
                    ),
                    "value": inspect_hydrus_object(
                        value,
                        max_depth=max_depth,
                        max_items=max_items,
                        _depth=_depth + 1,
                    ),
                }
            )
        result = {"kind": "dict", "length": len(obj), "items": items}
        if len(obj) > max_items:
            result["truncated_items"] = len(obj) - max_items
        return result

    if isinstance(obj, str):
        preview = obj[:160]
        return {"kind": "string", "length": len(obj), "value_preview": preview}

    return obj


def _collect_serialisable_nodes(
    obj: Any,
    *,
    counter: Counter[str],
    named: list[dict[str, Any]],
    max_named: int = 100,
) -> None:
    if is_meta_tuple(obj):
        _meta_type, payload = obj
        _collect_serialisable_nodes(payload, counter=counter, named=named, max_named=max_named)
        return

    if is_serialisable_tuple(obj):
        if len(obj) == 3:
            serialisable_type, version, info = obj
            name = None
        else:
            serialisable_type, name, version, info = obj

        type_name = _short_type_name(serialisable_type)
        counter[type_name] += 1

        if name is not None and len(named) < max_named:
            named.append(
                {
                    "type_id": serialisable_type,
                    "type_name": type_name,
                    "version": version,
                    "name": name,
                }
            )

        _collect_serialisable_nodes(info, counter=counter, named=named, max_named=max_named)
        return

    if isinstance(obj, list):
        for item in obj:
            _collect_serialisable_nodes(item, counter=counter, named=named, max_named=max_named)
        return

    if isinstance(obj, dict):
        for key, value in obj.items():
            _collect_serialisable_nodes(key, counter=counter, named=named, max_named=max_named)
            _collect_serialisable_nodes(value, counter=counter, named=named, max_named=max_named)


def inspect_hydrus_png(
    path: str | Path,
    *,
    max_depth: int = 6,
    max_items: int = 25,
) -> dict[str, Any]:
    decoded = decode_hydrus_png(path)
    decompressed = decompress_payload(decoded.payload_bytes)

    report: dict[str, Any] = {
        "path": str(decoded.path),
        "image": {
            "width": decoded.width,
            "height": decoded.height,
            "top_height": decoded.top_height,
        },
        "payload": {
            "length_bytes": decoded.payload_length,
            "compressed": decompressed != decoded.payload_bytes,
        },
    }

    try:
        text = decompressed.decode("utf-8")
        report["payload"]["utf8"] = True
        report["payload"]["text_preview"] = text[:240]
    except UnicodeDecodeError:
        report["payload"]["utf8"] = False
        report["payload"]["text_preview"] = None
        return report

    try:
        data = json.loads(text)
        report["payload"]["json"] = True
        report["payload"]["structure"] = inspect_hydrus_object(
            data,
            max_depth=max_depth,
            max_items=max_items,
        )
        counts: Counter[str] = Counter()
        named_objects: list[dict[str, Any]] = []
        _collect_serialisable_nodes(data, counter=counts, named=named_objects)
        report["payload"]["catalog"] = {
            "type_counts": dict(sorted(counts.items(), key=lambda item: (-item[1], item[0]))),
            "named_objects": named_objects,
        }
    except json.JSONDecodeError:
        report["payload"]["json"] = False

    return report
