"""Command line.

    reformer scan <path ...> [--site-listing F] [--property-bags F] [--json F] [--html F]
    reformer selftest

Exit codes: 0 clean · 2 forms found that need a decision · 1 error. The 2 is
deliberate: a scan that finds work is not a failure, but in a pipeline it
should be distinguishable from one that finds nothing.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .classify import classify, totals
from .package import Container
from .report import KIND_LABELS, write
from .scan import ScanResult, merge, scan_package, scan_property_bags, scan_site_listing


def _load_rows(path: str) -> list[dict]:
    """A capture, in whatever shape the thing that produced it emits: a bare
    list, a SharePoint ``{"value": [...]}`` envelope, or PowerShell's single
    object when only one row came back."""
    raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if isinstance(raw, dict):
        for key in ("value", "rows", "items"):
            if isinstance(raw.get(key), list):
                return raw[key]
        return [raw]
    if isinstance(raw, list):
        return raw
    raise ValueError(f"{path}: expected a list of rows or an object containing one")


def _scan(a: argparse.Namespace) -> int:
    results: list[ScanResult] = []
    sources: list[str] = []

    for target in a.paths or []:
        p = Path(target)
        zips = sorted(p.glob("*.zip")) if p.is_dir() else [p]
        if p.is_dir() and not zips:
            print(f"  {p}: no .zip files", file=sys.stderr)
        for z in zips:
            try:
                results.append(scan_package(Container.load(z)))
            except Exception as e:                      # a bad zip is a bad input, not a crash
                print(f"  error: {z}: {e}", file=sys.stderr)
                return 1
            sources.append(z.name)
            print(f"  {z.name}")

    for path in a.site_listing or []:
        try:
            rows = _load_rows(path)
        except (OSError, ValueError, json.JSONDecodeError) as e:
            print(f"  error: {e}", file=sys.stderr)
            return 1
        results.append(scan_site_listing(rows, Path(path).stem))
        sources.append(Path(path).name)
        print(f"  {Path(path).name}: {len(rows)} row(s)")

    for path in a.property_bags or []:
        try:
            rows = _load_rows(path)
        except (OSError, ValueError, json.JSONDecodeError) as e:
            print(f"  error: {e}", file=sys.stderr)
            return 1
        results.append(scan_property_bags(rows))
        sources.append(Path(path).name)
        print(f"  {Path(path).name}: {len(rows)} row(s)")

    if not results:
        print("  error: nothing to scan — give a package, a --site-listing or --property-bags",
              file=sys.stderr)
        return 1

    res = merge(*results)
    items = classify(res)
    t = totals(items)

    print()
    for kind, label in KIND_LABELS.items():
        n = sum(1 for i in items if i.kind == kind)
        if n or kind in ("microsoft-form", "list-form"):
            print(f"  {label + ':':<26} {n}")
    if res.canvas_apps:
        print(f"  {'canvas apps:':<26} {len(res.canvas_apps)}")
    print(f"\n  {t['forms']} form(s), {t['days_low']}–{t['days_high']} days at 7.5h")
    for note in res.notes:
        print(f"  note: {note}")

    write(Path(a.json) if a.json else None,
          Path(a.html) if a.html else None,
          res, items, sources)
    for label, path in (("json", a.json), ("html", a.html)):
        if path:
            print(f"  report ({label}): {path}")

    if items:
        print("\n  Microsoft Forms are counted only where a flow names one. Forms with nothing\n"
              "  downstream are invisible to any scan and must come from asking owners.")
    return 2 if items else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="reformer",
        description="Find the forms a tenant move will break, and say what each one costs to fix.")
    ap.add_argument("--version", action="version", version=f"reformer {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("scan", help="inventory forms from solution packages and captured listings")
    p.add_argument("paths", nargs="*", help="solution export .zip files, or a folder of them")
    p.add_argument("--site-listing", action="append", metavar="JSON",
                   help="a captured listing of a site's files; finds Plumsail and InfoPath forms")
    p.add_argument("--property-bags", action="append", metavar="JSON",
                   help="captured PowerAppFormProperties readings; finds customised list forms")
    p.add_argument("--json", help="write the machine-readable report here")
    p.add_argument("--html", help="write the readable report here")

    sub.add_parser("selftest", help="run the unit tests")

    a = ap.parse_args(argv)

    if a.cmd == "selftest":
        import unittest
        tests = Path(__file__).resolve().parent.parent / "tests"
        result = unittest.TextTestRunner(verbosity=1).run(
            unittest.defaultTestLoader.discover(str(tests)))
        return 0 if result.wasSuccessful() else 1

    return _scan(a)
