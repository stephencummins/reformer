"""Turning "here is a form" into "here is what to do about it, and what it costs".

The treatments come from how each kind actually behaves in a tenant move, not
from preference:

- A **Microsoft Form** has no export, no supported API and no cross-tenant
  ownership transfer, and its responses do not travel. So the question is never
  "how do we move it" but "does this become a list, or get recreated and
  re-pointed". Anything with a process behind it wants to be a list, because a
  list migrates like any other content.
- A **customised list form** has no automated route — the vendor says so
  plainly — but it does have a documented manual one. Moving it is minutes and
  rebuilding it is half a day, which is the whole argument for proving the
  route before committing to rebuilds.
- A **Plumsail list form** is a file in the site, so the content migration
  carries it. The work is licensing and verification, not moving.

Effort is given as a band, not a number. The bands are what a competent person
takes, and the estimate is per form including its flow, which is usually the
larger half.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .scan import Finding, ScanResult

CONVERT = "convert to a SharePoint list"
RECREATE = "recreate as a Form, owned by a group"
ROUTE = "move via the documented route"
CONTENT = "travels with the site content"
REBUILD = "rebuild"
RETIRE = "retire"
INVESTIGATE = "investigate"

# Hours, as a band. A band beats a false average: the spread within a kind is
# real and driven by how much flow sits behind the form.
BANDS = {
    CONVERT: (4.0, 16.0),
    RECREATE: (1.0, 4.0),
    ROUTE: (0.25, 1.0),
    CONTENT: (0.0, 0.5),
    REBUILD: (4.0, 8.0),   # nothing emits this: it is the fallback figure the
                           # customised-list-form argument is made against
    RETIRE: (0.25, 0.5),
    INVESTIGATE: (0.5, 2.0),
}


@dataclass
class Item:
    kind: str
    identity: str
    name: str
    source: str
    treatment: str
    low_hours: float
    high_hours: float
    why: str
    flags: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "kind": self.kind, "identity": self.identity, "name": self.name,
            "source": self.source, "treatment": self.treatment,
            "hours_low": self.low_hours, "hours_high": self.high_hours,
            "why": self.why, "flags": self.flags,
        }


def _band(treatment: str) -> tuple[float, float]:
    return BANDS.get(treatment, (0.5, 2.0))


def _one_row_per_form(findings: list[Finding]) -> list[Finding]:
    """Collapse the same form found in several places into one row.

    A customised form's binding is repeated in the app JSON, in the app's
    ``Properties.json`` and in its control tree, and a flow can name the same
    form on both its trigger and its action. Those are one thing each. Counting
    the occurrences would overstate both the inventory and, worse, the effort —
    and the effort figure is the number people plan against.

    The richest occurrence wins, so a binding that carries a list URL is
    preferred over the bare one that does not.
    """
    best: dict[tuple[str, str], Finding] = {}
    seen_in: dict[tuple[str, str], list[str]] = {}
    for f in findings:
        key = f.key()
        seen_in.setdefault(key, [])
        if f.source not in seen_in[key]:
            seen_in[key].append(f.source)
        current = best.get(key)
        if current is None or _richness(f) > _richness(current):
            best[key] = f
    out = []
    for key, f in best.items():
        places = seen_in[key]
        if len(places) > 1:
            f.detail = {**f.detail, "also_in": places[1:]}
        out.append(f)
    return out


def _richness(f: Finding) -> int:
    """How much a given occurrence tells us, for choosing between duplicates."""
    score = len(f.detail)
    if f.name:
        score += 2
    if f.detail.get("list_url"):
        score += 3
    return score


def classify(res: ScanResult, drives_a_process: bool | None = None) -> list[Item]:
    """One row per form, with a treatment and an effort band.

    ``drives_a_process`` is the one judgement a scan cannot make for a
    Microsoft Form: whether anything downstream depends on the responses. When
    it is not supplied, the presence of a flow reading the form's questions is
    used as the evidence, which is the best a package can offer.
    """
    items: list[Item] = []
    for f in _one_row_per_form(res.findings):
        if f.kind == "microsoft-form":
            items.append(_microsoft_form(f, res, drives_a_process))
        elif f.kind == "list-form":
            items.append(_list_form(f))
        elif f.kind == "plumsail-form":
            items.append(_plumsail_form(f))
        elif f.kind == "plumsail-connector":
            items.append(Item(
                f.kind, f.identity, f.name, f.source, INVESTIGATE, *_band(INVESTIGATE),
                "A Plumsail connector, not a SharePoint form. It needs re-authenticating in the "
                "target and says nothing about how many list forms exist.",
                flags=["counts as work, not as a form"],
            ))
    return items


def _microsoft_form(f: Finding, res: ScanResult, drives_a_process: bool | None) -> Item:
    questions = sorted(res.questions.get(f.identity, set()))
    has_flow = bool(questions) or True   # it was found on a flow's connector at all
    process = has_flow if drives_a_process is None else drives_a_process
    flags = []
    if questions:
        flags.append(f"{len(questions)} question(s) read by a flow — each is a manual edit if recreated")
    flags.append("responses do not migrate: export them to Excel before the source tenant goes")

    if process:
        low, high = _band(CONVERT)
        # Every question a flow reads is a field reference to rewrite by hand.
        high += 0.5 * len(questions)
        return Item(f.kind, f.identity, f.name or f.identity, f.source, CONVERT, low, high,
                    "A flow depends on the responses, so a list gives the same screen, the same "
                    "records and a trigger that migrates like any other list.", flags)
    return Item(f.kind, f.identity, f.name or f.identity, f.source, RECREATE, *_band(RECREATE),
                "Nothing downstream depends on it, so recreating is cheaper than converting. "
                "Own it with a group so the next leaver does not repeat this.", flags)


def _list_form(f: Finding) -> Item:
    flags = []
    if f.detail.get("from") == "property-bag":
        flags.append("binding names an app in the source tenant; clear the property bag before importing")
    if f.detail.get("site_id_is_guid"):
        flags.append("site is identified by GUID, which has no title to match on and must be mapped by hand")
    if not f.detail.get("list_url") and f.detail.get("from") != "property-bag":
        flags.append("no list URL in the binding, so the target list cannot be inferred")
    return Item(f.kind, f.identity, f.name or f.identity, f.source, ROUTE, *_band(ROUTE),
                "Retargeting the package is automated; the import is not. Minutes per form against "
                "half a day to rebuild, which is why the route is worth proving before committing.",
                flags + [
                    "the binding is retargeted by the migration tooling — do not hand-edit the JSON",
                    "by hand after import: Create as New (update-existing does not work), "
                    "delete and re-add the data source, then Publish to SharePoint, which is what binds it",
                    "target list needs identical internal column names, same language, no existing custom form",
                ])


def _plumsail_form(f: Finding) -> Item:
    return Item(f.kind, f.identity, f.name or f.identity, f.source, CONTENT, *_band(CONTENT),
                "The definition is a file in the site, so a content migration carries it. "
                "The work is the licence and verifying it bound, not moving it.",
                ["licence is bound to the tenant's SharePoint domain — confirm re-binding and cutover overlap",
                 "classic add-in forms cannot be installed in a new tenant at all; confirm these are SPFx"])


def totals(items: list[Item]) -> dict:
    low = sum(i.low_hours for i in items)
    high = sum(i.high_hours for i in items)
    by_treatment: dict[str, int] = {}
    for i in items:
        by_treatment[i.treatment] = by_treatment.get(i.treatment, 0) + 1
    return {
        "forms": len(items),
        "hours_low": round(low, 1),
        "hours_high": round(high, 1),
        "days_low": round(low / 7.5, 1),
        "days_high": round(high / 7.5, 1),
        "by_treatment": by_treatment,
    }
