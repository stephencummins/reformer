# reformer

Find the forms a Microsoft 365 tenant move will break, and say what each one costs to fix.

Three unrelated technologies get called "a form", and each one breaks differently when a tenant changes. None of them break loudly. The solution imports, the migration report says green, and the process is dead because the screen a person types into no longer exists or no longer points at anything.

reformer inventories what is actually there, says what each form needs, and puts a number behind it.

It only reads. It never touches a tenant and never modifies a package.

## The three things

| Called | What it is | Where the definition lives | Does it move? |
|---|---|---|---|
| A Microsoft Form | A form on the Forms service, owned by a person | The service, tied to the owner's account | **No.** No export, no supported API, no cross-tenant ownership transfer |
| A custom form | A canvas app bound to one SharePoint list | The Power Platform environment, bound via the list's property bag | Only by hand. Microsoft: *"there's currently no automated method"* |
| A Plumsail form | An SPFx form on a SharePoint list | **Files in the site**, under `Site Pages/PlumsailForms` | **Yes** — it is content, so a content migration carries it |

InfoPath was a fourth. reformer does not look for it: there is none to find, and a `.xsn` or `.xsf` template in a site listing is a row nobody has to act on. It is ignored on purpose and a test holds that, so it reads as a decision rather than an omission.

Two traps this encodes, because both mislead people reliably:

**Connector names do not mean what they look like.** `shared_plumsail` is Plumsail Documents and `shared_plumsailforms` is their cloud-hosted web forms product. Neither is a SharePoint list form, and neither tells you how many list forms a site has. reformer reports them as work to do, not as forms.

**A form with nothing downstream is invisible to a package.** A Microsoft Form is only discoverable from a solution export when a flow names it. One somebody made to collect information, with no flow behind it, appears in no package and no connector inventory. So the package-derived count is a **floor**, and reformer says so in every report rather than letting the number look complete.

That floor can be turned into a real number — see below.

## Counting Microsoft Forms properly

There is no supported API, which is usually where the conversation stops. It shouldn't. There are three routes, and they fail in different places, so the honest answer is to use more than one.

**1. Enumerate the tenant (near-complete, unsupported).** The Forms web app has an internal API, and an Entra app can be granted the **application** permission `Forms.Read.All` on the Microsoft Forms resource — a real permission, listed under *APIs my organization uses*. With client credentials you can read *any* user's forms, so looping every user from Graph gives a near-complete inventory with owners. It is undocumented, Microsoft has already moved the host once, and their own guidance is that these endpoints may change without notice. Treat it as something to re-verify, not something to depend on indefinitely.

**2. eDiscovery (supported, coarser).** Forms data lives in the **owner's Exchange mailbox**. A Content Search across all mailboxes filtered to `ItemClass="IPM.File.Forms"` finds it tenant-wide and is entirely supported. It returns blobs to parse rather than a tidy list, and needs eDiscovery permissions, but nothing about it can be withdrawn from under you.

**3. The admin activity report (supported, not an inventory).** Reports → Usage → Forms gives per-user counts of forms created. No names, no ids. Useless as an inventory, genuinely useful as a *targeting list*: it tells you which users are worth enumerating.

Two gaps survive all three, and they are worth stating to whoever asks for the number:

- **Group-owned forms.** The application permission does not cover the group context, and a group's forms are not in anyone's mailbox. Reaching them needs delegated access from an account that is a member of the group.
- **Forms of hard-deleted users**, which are destroyed 30 days after the account goes and are not recoverable.

Feed the result of route 1 or 2 in with `--forms-listing` and reformer stops hedging: the report says the count came from an enumeration, and names those two remaining gaps instead.

## Use

```
python3 -m reformer scan Solution.zip --json forms.json --html forms.html
python3 -m reformer scan exports/            # a folder of packages
python3 -m reformer scan --site-listing site-files.json --property-bags custom-forms.json
python3 -m reformer scan exports/ --forms-listing tenant-forms.json
```

Exit `0` when nothing needs doing, `2` when there are forms to decide about, `1` on a bad input. The `2` is deliberate: finding work is not a failure, but a pipeline should be able to tell it apart from finding nothing.

### What it reads

**Solution exports (`.zip`)** — needs no credentials. Canvas apps inside the package are `.msapp` files, which are themselves zips, so the bindings live one level deeper than a plain walk reaches. reformer opens them and finds:

- Microsoft Forms named by a `form_id` on the Forms connector, plus the question ids a flow reads, because each of those is a manual edit if the form is recreated
- customised list form bindings — `embeddedApp` blocks of type `SharepointFormApp`
- Plumsail connector use

**Captured listings (JSON)** — for the things no package contains. Both accept a bare list, a `{"value": [...]}` envelope, or a single object.

- `--site-listing` finds Plumsail definitions under `SitePages/PlumsailForms`. Any listing works as long as each row carries a path under `ServerRelativeUrl`, `Name` or `path`.
- `--forms-listing` takes a Microsoft Forms tenant enumeration, which is what turns the Forms count from a floor into a real one. A row needs an `id` and a `title`; an owner is used when present.
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
| Rebuild | The documented route failed on a customised list form | 4–8h |

Nothing emits the rebuild row: it is the fallback a customised list form falls to when the documented route fails on it, which is a judgement made on the day. It is in the table because it is the figure the route is argued against.

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
