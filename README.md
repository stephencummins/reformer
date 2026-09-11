# reformer

Find the forms a Microsoft 365 tenant move will break, and say what each one costs to fix.

Four unrelated technologies get called "a form", and each one breaks differently when a tenant changes. None of them break loudly. The solution imports, the migration report says green, and the process is dead because the screen a person types into no longer exists or no longer points at anything.

reformer inventories what is actually there, says what each form needs, and puts a number behind it.

It only reads. It never touches a tenant and never modifies a package.

## The four things

| Called | What it is | Where the definition lives | Does it move? |
|---|---|---|---|
| A Microsoft Form | A form on the Forms service, owned by a person | The service, tied to the owner's account | **No.** No export, no supported API, no cross-tenant ownership transfer |
| A custom form | A canvas app bound to one SharePoint list | The Power Platform environment, bound via the list's property bag | Only by hand. Microsoft: *"there's currently no automated method"* |
| A Plumsail form | An SPFx form on a SharePoint list | **Files in the site**, under `Site Pages/PlumsailForms` | **Yes** — it is content, so a content migration carries it |
| An InfoPath form | Retired SharePoint form technology | The site | No. Rebuild |

Two traps this encodes, because both mislead people reliably:

**Connector names do not mean what they look like.** `shared_plumsail` is Plumsail Documents and `shared_plumsailforms` is their cloud-hosted web forms product. Neither is a SharePoint list form, and neither tells you how many list forms a site has. reformer reports them as work to do, not as forms.

**A form with nothing downstream is invisible.** A Microsoft Form is only discoverable from a package when a flow names it. One somebody made to collect information, with no flow behind it, appears in no package and no connector inventory. **Treat the Microsoft Forms count as a floor, never a total** — the rest has to come from asking owners. reformer says so in every report rather than letting the number look complete.

## Use

```
python3 -m reformer scan Solution.zip --json forms.json --html forms.html
python3 -m reformer scan exports/            # a folder of packages
python3 -m reformer scan --site-listing site-files.json --property-bags custom-forms.json
```

Exit `0` when nothing needs doing, `2` when there are forms to decide about, `1` on a bad input. The `2` is deliberate: finding work is not a failure, but a pipeline should be able to tell it apart from finding nothing.

### What it reads

**Solution exports (`.zip`)** — needs no credentials. Canvas apps inside the package are `.msapp` files, which are themselves zips, so the bindings live one level deeper than a plain walk reaches. reformer opens them and finds:

- Microsoft Forms named by a `form_id` on the Forms connector, plus the question ids a flow reads, because each of those is a manual edit if the form is recreated
- customised list form bindings — `embeddedApp` blocks of type `SharepointFormApp`
- Plumsail connector use

**Captured listings (JSON)** — for the things no package contains. Both accept a bare list, a `{"value": [...]}` envelope, or a single object.

- `--site-listing` finds Plumsail definitions under `SitePages/PlumsailForms` and InfoPath templates. Any listing works as long as each row carries a path under `ServerRelativeUrl`, `Name` or `path`.
- `--property-bags` finds customised list forms from readings of `PowerAppFormProperties` on each list's folder. This is the only reliable way to enumerate them across a tenant, and far better than asking site owners.

The property bag is also *why* lists arrive broken: its value names the app in the tenant it was made in, so if a migration copies it verbatim the target list points at an app that does not exist there, and the new and edit pages open to a spinner. Clear the key, then import and publish the app, which writes a correct one.

### What comes out

A worklist, one row per form — not one per occurrence. The same binding is repeated in the app JSON, in the app's `Properties.json` and in its control tree, and a flow names the same form on both its trigger and its action. Counting those would overstate the inventory and, worse, double the effort figure that people plan against.

Each row carries a treatment, an effort band and what to watch for:

| Treatment | When | Band |
|---|---|---|
| Convert to a SharePoint list | A flow, approval or record depends on the responses | 4–16h + 30m per question a flow reads |
| Recreate as a Form, owned by a group | Nothing downstream depends on it | 1–4h |
| Move via the documented route | A customised list form that works and is in use | 15m–1h |
| Travels with the site content | A Plumsail list form | 0–30m |
| Rebuild | InfoPath, or the route failed | 4–8h |

Bands, not averages. The spread within a kind is real and driven by how much flow sits behind the form. The custom-form line is the one worth arguing about: minutes to move against half a day to rebuild is the whole case for proving the route on one form before committing to rebuilds.

## Design

- **Python standard library only.** No install, no lockfile, no supply chain. `python3 -m reformer` from a clone.
- **Read-only by construction.** There is no write path to a tenant anywhere in the codebase.
- **Offline first.** Everything a solution package can answer is answered without credentials. Tenant-side facts arrive as captured files, so whoever holds the access can produce them separately from whoever runs the analysis.
- **Honest about its own blind spot.** Every report states that the Microsoft Forms count is a floor. A number that looks complete and is not is worse than no number.

```
reformer/
  package.py    zips, and the .msapp zips inside them
  scan.py       recognising each kind by its own evidence
  classify.py   treatment and effort, one row per form
  report.py     JSON and HTML
  cli.py
```

## Tests

```
python3 -m reformer selftest
```

Every fixture is synthetic. Nothing in this repository carries a real tenant, site, list or form identifier — the shapes are what matter, and the shapes are public behaviour.
