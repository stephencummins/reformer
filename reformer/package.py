"""Reading the containers forms hide inside, without unpacking anything to disk.

A Power Platform solution export is a zip. Canvas apps inside it are ``.msapp``
files, which are themselves zips, so the interesting JSON is one level further
down than a naive walk reaches. Members are addressed with ``!`` between the
outer and inner name, the way an archive tool shows a nested entry:

    CanvasApps/pub_form_DocumentUri.msapp!References/DataSources.json

Nothing here writes. reformer reports what exists; changing a package is a
different job with a different risk profile.
"""
from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

NESTED_SEP = "!"
MSAPP_SUFFIX = ".msapp"


def is_text(data: bytes) -> bool:
    """Text means decodes as UTF-8 and holds no NUL. Images and compiled blobs
    fail one or the other, and scanning them wastes time and produces noise."""
    if b"\x00" in data:
        return False
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


@dataclass
class Container:
    """One archive: its text members, and any nested archives opened in turn."""

    name: str
    members: dict[str, bytes] = field(default_factory=dict)
    nested: dict[str, "Container"] = field(default_factory=dict)

    @classmethod
    def from_bytes(cls, data: bytes, name: str) -> "Container":
        c = cls(name=name)
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for info in z.infolist():
                if info.is_dir():
                    continue
                raw = z.read(info)
                if info.filename.lower().endswith(MSAPP_SUFFIX) and _looks_like_zip(raw):
                    c.nested[info.filename] = cls.from_bytes(raw, info.filename)
                else:
                    c.members[info.filename] = raw
        return c

    @classmethod
    def load(cls, path: str | Path) -> "Container":
        p = Path(path)
        return cls.from_bytes(p.read_bytes(), p.name)

    def texts(self) -> list[tuple[str, str]]:
        """Every text member, nested archives included, as (address, text)."""
        out: list[tuple[str, str]] = []
        for name, raw in self.members.items():
            if is_text(raw):
                out.append((name, raw.decode("utf-8")))
        for outer, inner in self.nested.items():
            for name, text in inner.texts():
                out.append((f"{outer}{NESTED_SEP}{name}", text))
        return out

    def json_members(self) -> list[tuple[str, object]]:
        """Text members that parse as JSON. A member that does not parse is not
        an error: a solution carries plenty of XML and plain text too."""
        out: list[tuple[str, object]] = []
        for name, text in self.texts():
            if not name.lower().endswith(".json"):
                continue
            try:
                out.append((name, json.loads(text)))
            except json.JSONDecodeError:
                continue
        return out

    def canvas_apps(self) -> list[str]:
        return sorted(self.nested)


def _looks_like_zip(data: bytes) -> bool:
    try:
        return zipfile.is_zipfile(io.BytesIO(data))
    except Exception:       # a truncated or unreadable member is simply not one
        return False


def walk_dicts(node: object):
    """Every dict anywhere in a decoded JSON document.

    Bindings are found by shape rather than by path, because the same block
    appears in the app JSON, in Properties.json and in the control tree, and
    hard-coding those paths breaks whenever the export format shifts.
    """
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from walk_dicts(v)
    elif isinstance(node, list):
        for v in node:
            yield from walk_dicts(v)
