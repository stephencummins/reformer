"""Write the script that puts lists with a Plumsail form back on SharePoint's own.

A Plumsail form is attached by pointing a list content type's New, Edit and
Display form URLs at a page under ``SitePages/PlumsailForms``. The files travel
with a content migration; the SPFx package that renders them does not. Where
the package is not in the target tenant, every such list opens to a blank page.
Clearing the three URLs gives the list its standard forms back, and the
definitions stay where they are for the day the package is installed.

reformer itself never signs in and never writes. It emits a script; a site
admin reads it and pastes it into the browser console on the site, where it
runs with their own session. It starts as a dry run, and what it changes it
records, so the same script can put the URLs back.
"""
from __future__ import annotations

import json
import re

_SITE = re.compile(r"^/[A-Za-z0-9._~\-]+(?:/[A-Za-z0-9._~\-]+)*$")

_TEMPLATE = r"""// reformer __VERSION__ - put lists with a Plumsail form back on the standard SharePoint forms.
//
// Run it in the browser console (F12) on any page of the site, signed in as a
// site admin. It uses your session and nothing else.
//
//   1. Run it as it is. DRY_RUN is true: it lists what it would change and changes nothing.
//   2. Set DRY_RUN to false and run it again to clear the form URLs.
//   3. Keep the JSON it prints. To undo, paste that JSON in as RESTORE and run once more.
//
// The Plumsail definitions under SitePages/PlumsailForms are not touched.
(async () => {
  const DRY_RUN = true;
  const RESTORE = null;          // the "changed" array a previous run printed, to put the URLs back
  const SITE = __SITE__;         // server-relative site path, or null to use the site this page is in
  const MARKER = "/plumsailforms/";
  const FIELDS = ["NewFormUrl", "EditFormUrl", "DisplayFormUrl"];

  const site = SITE || (location.pathname.match(/^\/(?:sites|teams)\/[^\/]+/) || [""])[0];
  const api = location.origin + site + "/_api";
  const json = { accept: "application/json;odata=nometadata" };

  const get = async (url) => {
    const rows = [];
    while (url) {
      const r = await fetch(url, { headers: json, credentials: "same-origin" });
      if (!r.ok) throw new Error("GET " + r.status + " " + url.split("?")[0]);
      const body = await r.json();
      rows.push(...(body.value || []));
      url = body["odata.nextLink"] || null;
    }
    return rows;
  };

  let digest = null;
  const write = async (listId, contentTypeId, values) => {
    if (!digest) {
      const r = await fetch(api + "/contextinfo", { method: "POST", headers: json, credentials: "same-origin" });
      if (!r.ok) throw new Error("contextinfo " + r.status);
      digest = (await r.json()).FormDigestValue;
    }
    const url = api + "/web/lists(guid'" + listId + "')/ContentTypes('" + contentTypeId + "')";
    const r = await fetch(url, {
      method: "POST", credentials: "same-origin",
      headers: { ...json, "content-type": "application/json;odata=nometadata",
                 "X-RequestDigest": digest, "X-HTTP-Method": "MERGE", "IF-MATCH": "*" },
      body: JSON.stringify(values),
    });
    if (!r.ok) throw new Error("MERGE " + r.status + " on content type " + contentTypeId);
    const now = (await (await fetch(url + "?$select=" + FIELDS.join(","), { headers: json, credentials: "same-origin" })).json());
    return FIELDS.every((f) => !(f in values) || (now[f] || "") === values[f]);
  };

  const result = { site: location.origin + site, dryRun: DRY_RUN, restoring: !!RESTORE, changed: [], failed: [] };

  if (RESTORE) {
    for (const row of RESTORE) {
      try {
        if (!DRY_RUN && !(await write(row.listId, row.contentTypeId, row.was))) throw new Error("read-back differs");
        result.changed.push(row);
      } catch (e) { result.failed.push({ ...row, error: String(e.message || e) }); }
    }
  } else {
    const lists = await get(api + "/web/lists?$select=Id,Title&$filter=Hidden eq false");
    for (const list of lists) {
      const types = await get(api + "/web/lists(guid'" + list.Id + "')/ContentTypes?$select=StringId,Name," + FIELDS.join(","));
      for (const ct of types) {
        const was = {};
        for (const f of FIELDS) if ((ct[f] || "").toLowerCase().includes(MARKER)) was[f] = ct[f];
        if (!Object.keys(was).length) continue;
        const row = { list: list.Title, listId: list.Id, contentType: ct.Name, contentTypeId: ct.StringId, was };
        try {
          const cleared = Object.fromEntries(Object.keys(was).map((f) => [f, ""]));
          if (!DRY_RUN && !(await write(list.Id, ct.StringId, cleared))) throw new Error("read-back differs");
          result.changed.push(row);
        } catch (e) { result.failed.push({ ...row, error: String(e.message || e) }); }
      }
    }
    result.listsChecked = lists.length;
  }

  const verb = DRY_RUN ? "would be " : "";
  console.log("reformer: " + result.changed.length + " content type(s) " + verb + (RESTORE ? "restored" : "reset") +
              ", " + result.failed.length + " failed, on " + result.site);
  console.table(result.changed.map((r) => ({ list: r.list, contentType: r.contentType, urls: Object.keys(r.was).join(", ") })));
  console.log("Keep this. It is the RESTORE value that undoes the change:");
  console.log(JSON.stringify(result.changed));
  return result;
})();
"""


def reset_script(site: str | None = None, version: str = "") -> str:
    """The script text. ``site`` pins it to one server-relative site path
    (``/sites/Example``); without it the script works on whichever site's page
    it is run from."""
    if site is not None:
        site = site.rstrip("/")
        if not _SITE.match(site):
            raise ValueError(f"not a server-relative site path: {site!r} (expected something like /sites/Example)")
    return (_TEMPLATE.replace("__VERSION__", version)
            .replace("__SITE__", json.dumps(site)))
