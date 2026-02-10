"""
parsing.py – Extract and update image URLs inside nested JSON structures.

Paths use a simple dot notation with [] to indicate arrays:
    "Images[]"            → product["Images"] is a list of URL strings
    "variants[].Image"    → product["variants"][*]["Image"] is a URL string
    "media.images[]"      → product["media"]["images"] is a list of URL strings
"""

from __future__ import annotations

import re


# Marker written into fields that should be removed from the output
REMOVE_MARKER = "__REMOVE__"

# Source types
SOURCE_URL = "url"
SOURCE_FILE = "file"
SOURCE_INVALID = "invalid"


# ── Path Parsing ─────────────────────────────────────────


def _parse_segments(path_str: str) -> list[dict]:
    """Turn 'variants[].Image' into segment descriptors."""
    segments = []
    for part in path_str.split("."):
        if part.endswith("[]"):
            segments.append({"field": part[:-2], "is_array": True})
        else:
            segments.append({"field": part, "is_array": False})
    return segments


# ── ImageLocation ────────────────────────────────────────


class ImageLocation:
    """Reference to a single image value inside a product dict."""

    __slots__ = ("path_display", "keys", "original_url", "source_type")

    def __init__(self, path_display: str, keys: list, original_url: str, source_type: str):
        self.path_display = path_display   # human-readable, e.g. "Images[0]"
        self.keys = keys                   # traversal keys, e.g. ["Images", 0]
        self.original_url = original_url
        self.source_type = source_type     # "url", "file", or "invalid"


# ── Extraction ───────────────────────────────────────────


def extract_image_locations(product: dict, path_str: str) -> list[ImageLocation]:
    """Return all image entries found at *path_str* inside *product*.

    Every non-empty string is returned — valid or not — so the pipeline
    can report invalid values and mark them for removal.
    """
    segments = _parse_segments(path_str)
    results: list[ImageLocation] = []
    _walk(product, segments, 0, [], results)
    return results


def _is_file_path(s: str) -> bool:
    """Check if a string looks like a local file path."""
    # Windows:  C:\..  D:/..
    if re.match(r"^[A-Za-z]:[\\\/]", s):
        return True
    # Unix absolute
    if s.startswith("/"):
        return True
    # Relative
    if s.startswith(("./", "../", ".\\", "..\\")):
        return True
    return False


def _classify_source(s: str) -> str:
    """Return SOURCE_URL, SOURCE_FILE, or SOURCE_INVALID."""
    if s.startswith(("http://", "https://")):
        return SOURCE_URL
    if _is_file_path(s):
        return SOURCE_FILE
    return SOURCE_INVALID


def _walk(obj, segments, seg_idx, keys_so_far, results):
    # All segments consumed → obj should be a string value
    if seg_idx >= len(segments):
        if isinstance(obj, str) and obj.strip():
            source_type = _classify_source(obj.strip())
            results.append(
                ImageLocation(
                    path_display=_format_keys(keys_so_far),
                    keys=list(keys_so_far),
                    original_url=obj,
                    source_type=source_type,
                )
            )
        return

    seg = segments[seg_idx]
    field = seg["field"]
    is_array = seg["is_array"]

    if not isinstance(obj, dict) or field not in obj:
        return

    value = obj[field]

    if is_array:
        if not isinstance(value, list):
            return
        for i, item in enumerate(value):
            _walk(item, segments, seg_idx + 1, keys_so_far + [field, i], results)
    else:
        _walk(value, segments, seg_idx + 1, keys_so_far + [field], results)


def _format_keys(keys) -> str:
    """['variants', 0, 'Image'] → 'variants[0].Image'"""
    parts: list[str] = []
    for k in keys:
        if isinstance(k, int):
            parts[-1] = f"{parts[-1]}[{k}]"
        else:
            parts.append(k)
    return ".".join(parts)


# ── Update ───────────────────────────────────────────────


def update_image_url(product: dict, keys: list, new_url: str):
    """Set a new URL at the position described by *keys*."""
    obj = product
    for key in keys[:-1]:
        obj = obj[key]
    obj[keys[-1]] = new_url


# ── Cleanup: remove failed / invalid entries ─────────────


def cleanup_removed_images(product: dict, path_strs: list[str]):
    """Remove every REMOVE_MARKER left in the product after processing.

    - Array fields: filter out the marker (shrinks the list).
    - Single-value fields: set to None.
    """
    for path_str in path_strs:
        segments = _parse_segments(path_str)
        _cleanup(product, segments, 0)


def _cleanup(obj, segments, seg_idx):
    if seg_idx >= len(segments):
        return

    seg = segments[seg_idx]
    field = seg["field"]
    is_array = seg["is_array"]

    if not isinstance(obj, dict) or field not in obj:
        return

    value = obj[field]

    if is_array:
        if not isinstance(value, list):
            return

        if seg_idx == len(segments) - 1:
            # Last segment — array of URL strings → filter out markers
            obj[field] = [v for v in value if v != REMOVE_MARKER]
        else:
            # Array of objects — recurse, then drop objects whose target is None
            for item in value:
                _cleanup(item, segments, seg_idx + 1)
    else:
        if seg_idx == len(segments) - 1:
            # Last segment — single value
            if value == REMOVE_MARKER:
                obj[field] = None
        else:
            _cleanup(value, segments, seg_idx + 1)
