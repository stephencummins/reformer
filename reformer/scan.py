"""Finding the three different things people call "a form".

They have almost nothing in common, so each is recognised by its own evidence:

- **A Microsoft Form** is named by the ``form_id`` parameter of a trigger or
  action on the Microsoft Forms connector. A form-shaped string anywhere else
  is not a reference — ids are opaque and a plain string that resembles one is
  usually a comment or a link someone pasted. The questions a flow reads show
  up separately as ``r`` + 32 hex tokens.
- **A customised list form** is a canvas app bound to one list, marked by an
  ``embeddedApp`` block of type ``SharepointFormApp`` carrying the site, the
  list id and the list URL.
- **A Plumsail list form** is not in the package at all: its definition is a
  file in the site, so it is found from a captured site listing instead.

InfoPath was a fourth and is not recognised here. There is none to find, so
its template files would only be rows nobody has to act on: a ``.xsn`` or
``.xsf`` in a site listing is ignored on purpose, and a test holds that.

The connector names are a trap worth stating in code as well as in the
documentation: ``shared_plumsail`` is Plumsail Documents and
``shared_plumsailforms`` is their cloud-hosted web forms product. Neither tells
you anything about how many Plumsail *list* forms a site has.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .package import Container, walk_dicts

FORMS_CONNECTOR = "shared_microsoftforms"
PLUMSAIL_CONNECTORS = {
    "shared_plumsail": "Plumsail Documents (not a SharePoint form)",
    "shared_plumsailforms": "Plumsail web forms, cloud-hosted (not a SharePoint list form)",
    "shared_plumsailsp": "Plumsail Actions (not a form)",
}
SHAREPOINT_FORM_APP = "sharepointformapp"

QUESTION_RE = re.compile(r"(?<![A-Za-z0-9])r[0-9a-f]{32}(?![A-Za-z0-9])")
GUID_RE = re.compile(r"^\{?[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}\}?$")


@dataclass
class Finding:
    """One thing found, and where. ``kind`` decides how it is treated later."""

    kind: str                 # microsoft-form | list-form | plumsail-form | plumsail-connector | canvas-app
    identity: str             # the id or path that names it
    source: str               # the member or file it was found in
    name: str = ""            # a human label where one is available
    detail: dict = field(default_factory=dict)

    def key(self) -> tuple[str, str]:
        return (self.kind, self.identity)


@dataclass
class ScanResult:
    findings: list[Finding] = field(default_factory=list)
    questions: dict[str, set[str]] = field(default_factory=dict)   # form id -> question ids the package reads
    canvas_apps: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def of_kind(self, kind: str) -> list[Finding]:
        return [f for f in self.findings if f.kind == kind]

    def add(self, f: Finding) -> None:
        if not any(x.key() == f.key() and x.source == f.source for x in self.findings):
            self.findings.append(f)

    def summary(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for f in self.findings:
            out[f.kind] = out.get(f.kind, 0) + 1
        return out


def _connector_of(host: dict) -> str:
    """The connector a flow step runs on, from either shape the export uses.

    Keys arrive already lower-cased, because exports are not consistent about
    casing and matching on the original spelling misses half of them.
    """
    name = str(host.get("connectionname") or "").strip().lower()
    if name:
        return name
    api = str(host.get("apiid") or "").strip().lower()
    return api.rsplit("/", 1)[-1] if api else ""


def scan_package(container: Container) -> ScanResult:
    """Everything a solution export can tell us about forms, offline."""
    res = ScanResult()
    res.canvas_apps = container.canvas_apps()
    for app in res.canvas_apps:
        res.add(Finding("canvas-app", app, container.name, name=app.rsplit("/", 1)[-1]))

    for member, doc in container.json_members():
        for node in walk_dicts(doc):
            _inspect(node, member, res)

    # Question tokens are only meaningful once a form is known: they say how
    # much of the flow has to be rewritten by hand if that form is recreated.
    known = {f.identity for f in res.of_kind("microsoft-form")}
    if known:
        for member, text in container.texts():
            found = set(QUESTION_RE.findall(text))
            if not found:
                continue
            for fid in known:
                if fid in text:
                    res.questions.setdefault(fid, set()).update(found)
    return res


def _inspect(node: dict, member: str, res: ScanResult) -> None:
    lower = {str(k).lower(): v for k, v in node.items()}

    host = lower.get("host")
    if isinstance(host, dict):
        connector = _connector_of({str(k).lower(): v for k, v in host.items()})
        params = lower.get("parameters")
        if connector == FORMS_CONNECTOR and isinstance(params, dict):
            for key, value in params.items():
                if str(key).lower() != "form_id" or not isinstance(value, str) or not value.strip():
                    continue
                fid = value.strip()
                if fid.startswith("@"):
                    res.notes.append(f"{member}: form_id is an expression, not a literal — check what it resolves to")
                    continue
                res.add(Finding("microsoft-form", fid, member))
        elif connector in PLUMSAIL_CONNECTORS:
            res.add(Finding("plumsail-connector", connector, member,
                            name=PLUMSAIL_CONNECTORS[connector]))

    embedded = lower.get("embeddedapp")
    if isinstance(embedded, dict):
        _embedded_app(embedded, member, res)
    elif str(lower.get("type") or "").lower() == SHAREPOINT_FORM_APP:
        _embedded_app(node, member, res)


def _embedded_app(block: dict, member: str, res: ScanResult) -> None:
    low = {str(k).lower(): v for k, v in block.items()}
    if str(low.get("type") or "").lower() != SHAREPOINT_FORM_APP:
        return
    list_id = str(low.get("listid") or "").strip()
    if not list_id:
        return
    site = str(low.get("siteid") or "").strip()
    list_url = str(low.get("listurl") or "").strip()
    res.add(Finding(
        "list-form", list_id.strip("{}").lower(), member,
        name=_list_name_from(list_url),
        detail={"site_id": site, "list_url": list_url,
                "site_id_is_guid": bool(GUID_RE.match(site))},
    ))


def _list_name_from(list_url: str) -> str:
    """The list's name as it appears in its own URL, for a readable report."""
    if not list_url:
        return ""
    parts = [p for p in list_url.split("/") if p]
    for i, part in enumerate(parts):
        if part.lower() == "lists" and i + 1 < len(parts):
            from urllib.parse import unquote
            return unquote(parts[i + 1])
    return ""


def scan_site_listing(rows: list[dict], site: str) -> ScanResult:
    """Plumsail list forms from a captured listing of a site's files.

    Plumsail keeps each SharePoint form as a file under
    ``Site Pages/PlumsailForms``, named for the list and form type it serves.
    That is why a content migration carries them: they are content. It is also
    why no connector inventory can count them.

    ``rows`` is whatever a listing produced, as long as each row carries a path
    under a ``Name``, ``ServerRelativeUrl`` or ``path`` key.
    """
    res = ScanResult()
    for row in rows:
        path = ""
        for key in ("ServerRelativeUrl", "serverRelativeUrl", "Name", "name", "path", "Path"):
            if isinstance(row, dict) and row.get(key):
                path = str(row[key])
                break
        if not path:
            continue
        low = path.lower()
        if "plumsailforms/" in low and low.endswith(".json"):
            res.add(Finding("plumsail-form", path, site, name=_plumsail_name(path)))
    return res


def _plumsail_name(path: str) -> str:
    """Plumsail names a definition ``{List}_{ContentType}_{FormType}``, so the
    list it belongs to is readable straight off the filename."""
    leaf = path.rsplit("/", 1)[-1]
    for suffix in (".designer.json", ".json"):
        if leaf.lower().endswith(suffix):
            leaf = leaf[: -len(suffix)]
            break
    return leaf.split("_", 1)[0] if "_" in leaf else leaf


def scan_forms_listing(rows: list[dict], source: str) -> ScanResult:
    """Microsoft Forms from a tenant enumeration.

    There is no supported API, but there is a real one. An Entra app granted
    the **application** permission ``Forms.Read.All`` on the Microsoft Forms
    resource can read any user's forms, so looping every user produces a
    near-complete inventory. It is undocumented and Microsoft has already moved
    the host once, so treat it as something to re-verify, not to rely on.

    Two gaps survive that method and both matter:

    - **Group-owned forms.** The group context does not accept application
      permissions, so those need delegated access from an account in the group.
    - **Forms of hard-deleted users**, which are destroyed 30 days after the
      account goes.

    The supported alternative reaches user-owned forms without any of this:
    Forms data lives in the owner's Exchange mailbox, so an eDiscovery search
    for ``ItemClass="IPM.File.Forms"`` finds it tenant-wide. It returns blobs to
    parse rather than a tidy list, and shares the group blind spot.

    A row needs an id and a title; an owner is used when present.
    """
    res = ScanResult()
    for row in rows:
        if not isinstance(row, dict):
            continue
        fid = str(row.get("id") or row.get("Id") or row.get("formId") or "").strip()
        title = str(row.get("title") or row.get("Title") or row.get("name") or "").strip()
        if not fid:
            continue
        owner = str(row.get("owner") or row.get("ownerId") or row.get("userPrincipalName")
                    or row.get("createdBy") or "").strip()
        detail = {"from": "tenant-listing"}
        if owner:
            detail["owner"] = owner
        if row.get("ownerContext") or row.get("owner_context"):
            detail["owner_context"] = str(row.get("ownerContext") or row.get("owner_context"))
        res.add(Finding("microsoft-form", fid, source, name=title or fid, detail=detail))
    return res


def scan_property_bags(rows: list[dict]) -> ScanResult:
    """Customised list forms from a captured property-bag reading.

    SharePoint records the binding on the list folder under
    ``PowerAppFormProperties``, and the value names the app in the tenant it
    was made in. Two consequences: it is the only reliable way to enumerate
    customised forms across a tenant, and if a migration copies it verbatim the
    target list points at an app that does not exist there.
    """
    res = ScanResult()
    for row in rows:
        if not isinstance(row, dict):
            continue
        list_name = str(row.get("list") or row.get("List") or row.get("Title") or "").strip()
        site = str(row.get("site") or row.get("Site") or row.get("webUrl") or "").strip()
        value = row.get("PowerAppFormProperties") or row.get("powerAppFormProperties") or row.get("value")
        if not value:
            continue
        res.add(Finding(
            "list-form", (list_name or str(value))[:200], site or "captured property bag",
            name=list_name,
            detail={"property_bag": str(value)[:400], "from": "property-bag"},
        ))
    return res


def merge(*results: ScanResult) -> ScanResult:
    out = ScanResult()
    for r in results:
        for f in r.findings:
            out.add(f)
        for fid, qs in r.questions.items():
            out.questions.setdefault(fid, set()).update(qs)
        out.canvas_apps.extend(a for a in r.canvas_apps if a not in out.canvas_apps)
        out.notes.extend(n for n in r.notes if n not in out.notes)
    return out
