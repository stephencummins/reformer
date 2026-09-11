"""The output: JSON for anything downstream, HTML for the person deciding.

The report is the deliverable. A scan nobody reads changes nothing, and the
audience here is usually a programme lead who wants the count, the treatment
split and the effort before they want any detail.
"""
from __future__ import annotations

import html
import json
from datetime import datetime, timezone

from .classify import Item, totals
from .scan import ScanResult

KIND_LABELS = {
    "microsoft-form": "Microsoft Forms",
    "list-form": "Customised list forms",
    "plumsail-form": "Plumsail list forms",
    "infopath": "InfoPath forms",
    "plumsail-connector": "Plumsail connectors",
    "canvas-app": "Canvas apps",
}


def to_json(res: ScanResult, items: list[Item], sources: list[str], enumerated: bool = False) -> dict:
    return {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources": sources,
        "forms_count_is_complete": enumerated,
        "summary": res.summary(),
        "totals": totals(items),
        "items": [i.as_dict() for i in items],
        "canvas_apps": res.canvas_apps,
        "notes": res.notes,
    }


def _esc(v) -> str:
    return html.escape(str(v))


def _forms_caveat(enumerated: bool) -> str:
    """How much the Microsoft Forms number is worth depends entirely on where
    it came from, so the report says which."""
    if enumerated:
        return ('<div class="caveat"><b>Counted from a tenant enumeration.</b> Two gaps survive it: '
                'forms owned by a Microsoft 365 <b>group</b>, which the application permission cannot '
                'read, and forms of hard-deleted users, which are destroyed 30 days after the account '
                'goes. Everything else owned by an active user should be here.</div>')
    return ('<div class="caveat"><b>This Microsoft Forms count is a floor, not a total.</b> Only forms '
            'a flow names are visible to a package scan; one somebody made to collect information, with '
            'nothing downstream, appears in no package and no connector inventory. A tenant enumeration '
            'is possible — see the README — and passing it as <code>--forms-listing</code> turns this '
            'into a real number.</div>')


def _hours(item: Item) -> str:
    if item.low_hours == item.high_hours:
        return f"{item.low_hours:g}h"
    return f"{item.low_hours:g}–{item.high_hours:g}h"


def to_html(res: ScanResult, items: list[Item], sources: list[str], enumerated: bool = False) -> str:
    t = totals(items)
    rows = []
    for kind in KIND_LABELS:
        group = [i for i in items if i.kind == kind]
        if not group:
            continue
        rows.append(f"<h2>{_esc(KIND_LABELS[kind])} <span class='n'>{len(group)}</span></h2>")
        rows.append("<table><tr><th>Name</th><th>Treatment</th><th>Effort</th><th>Why</th><th>Watch for</th></tr>")
        for i in group:
            flags = "".join(f"<li>{_esc(f)}</li>" for f in i.flags)
            rows.append(
                f"<tr><td><code>{_esc(i.name or i.identity)}</code><div class='src'>{_esc(i.source)}</div></td>"
                f"<td>{_esc(i.treatment)}</td><td class='num'>{_hours(i)}</td>"
                f"<td>{_esc(i.why)}</td><td><ul>{flags}</ul></td></tr>"
            )
        rows.append("</table>")

    if not items:
        rows.append("<p class='none'>No forms found in what was scanned. "
                    "That is a real answer only if the inputs covered the sites and packages you care about.</p>")

    split = "".join(f"<li><b>{_esc(v)}</b> &times; {_esc(k)}</li>" for k, v in sorted(t["by_treatment"].items()))
    notes = "".join(f"<li>{_esc(n)}</li>" for n in res.notes)
    notes_block = f"<h2>Notes</h2><ul>{notes}</ul>" if notes else ""

    return f"""<!doctype html>
<meta charset="utf-8"><title>reformer — forms inventory</title>
<style>
 body {{ font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Arial, sans-serif;
        margin: 2.5rem auto; max-width: 66rem; padding: 0 1.25rem; color: #1a1a1a; }}
 h1 {{ font-size: 1.6rem; margin-bottom: .2rem; }}
 h2 {{ font-size: 1.1rem; margin-top: 2.2rem; border-bottom: 2px solid #e3e3e3; padding-bottom: .3rem; }}
 .n {{ color: #666; font-weight: 400; }}
 .meta {{ color: #666; font-size: .87rem; margin-bottom: 1.5rem; }}
 table {{ border-collapse: collapse; width: 100%; margin-top: .6rem; }}
 th, td {{ border: 1px solid #ddd; padding: .5rem .6rem; text-align: left; vertical-align: top; font-size: .88rem; }}
 th {{ background: #f4f4f4; font-weight: 600; }}
 td.num {{ white-space: nowrap; font-variant-numeric: tabular-nums; }}
 code {{ font: .85rem/1.4 ui-monospace, SFMono-Regular, Consolas, monospace; word-break: break-all; }}
 .src {{ color: #777; font-size: .78rem; margin-top: .2rem; word-break: break-all; }}
 ul {{ margin: 0; padding-left: 1.1rem; }}
 li {{ margin: .15rem 0; }}
 .cards {{ display: flex; gap: 1rem; flex-wrap: wrap; margin: 1.2rem 0; }}
 .card {{ border: 1px solid #ddd; border-radius: 6px; padding: .7rem 1rem; min-width: 9rem; }}
 .card b {{ display: block; font-size: 1.5rem; }}
 .card span {{ color: #666; font-size: .82rem; }}
 .none {{ color: #666; }}
 .caveat {{ background: #fff8e6; border-left: 4px solid #e8a33d; padding: .7rem 1rem; margin: 1.4rem 0; font-size: .9rem; }}
</style>
<h1>Forms inventory</h1>
<div class="meta">{_esc(datetime.now(timezone.utc).strftime('%d %B %Y, %H:%M UTC'))}
 &middot; scanned: {_esc(', '.join(sources) or 'nothing')}</div>

<div class="cards">
  <div class="card"><b>{t['forms']}</b><span>forms</span></div>
  <div class="card"><b>{t['days_low']}–{t['days_high']}</b><span>days, at 7.5h</span></div>
  <div class="card"><b>{len(res.canvas_apps)}</b><span>canvas apps</span></div>
</div>

{_forms_caveat(enumerated)}

<h2>Treatment</h2><ul>{split or '<li>nothing to do</li>'}</ul>
{''.join(rows)}
{notes_block}
"""


def write(path_json, path_html, res: ScanResult, items: list[Item], sources: list[str],
          enumerated: bool = False) -> None:
    if path_json:
        path_json.parent.mkdir(parents=True, exist_ok=True)
        path_json.write_text(json.dumps(to_json(res, items, sources, enumerated), indent=2) + "\n",
                             encoding="utf-8")
    if path_html:
        path_html.parent.mkdir(parents=True, exist_ok=True)
        path_html.write_text(to_html(res, items, sources, enumerated), encoding="utf-8")
