# What the engineer actually does

reformer says what exists, what each form needs and what it costs. This says how to do it.

One section per treatment, in the same words the report uses. Each one is in the same shape: **what is actually broken**, **what has to be true first**, **the steps**, **how to know it worked**, and **why it still doesn't**. The last of those is the part worth reading first, because every one of these fails silently. Nothing errors. The list opens, the flow sits there, and the form is the default one.

## Do this before the source tenant goes

Regardless of what you decide later, and first:

- **Export every Microsoft Form's responses to Excel** and save the workbook in the owning site. Responses do not migrate by any route. It costs minutes and it is the only artefact guaranteed to survive.
- **Export the Plumsail layouts** from the designer, per form, even though a content copy should carry them. Belt and braces, and free.
- **Export each customised list form** as a package with **Create as New**.
- **Capture the inventories** the scan needs from the source: the site listing, the property-bag readings, and a Microsoft Forms enumeration.
- **Decommission no account until its forms are dealt with.** A form belonging to a deleted account is destroyed 30 days later and Microsoft states it is not recoverable.

## Travels with the site content — Plumsail list forms

### First: which product are you actually holding

Three different things get called "a Plumsail form", and they remediate differently. Settle this before anything else, because two of the three have no route at all.

| Flavour | How to recognise it | Route |
|---|---|---|
| **Forms Designer** (the older, separate product) | Schema files are **`.xfds`**, root element `<FormsDesigner>` | No migration into modern Forms. Rebuild |
| **Plumsail Forms, classic add-in model** | Installed as a **SharePoint add-in**; forms render at `/SitePages/PlumsailForms/...` in an iframe | Retired. Move to SPFx or rebuild |
| **Plumsail Forms, SPFx** | **SPFx package in the tenant App Catalog**; forms render on SharePoint's own form pages (`/_layouts/15/SPListForm.aspx`) | Migrates. The rest of this section |

Three checks, none of which needs more than a browser:

1. **Open a list's New form and look at the URL.** `/_layouts/15/...` is SPFx. `/SitePages/PlumsailForms/...` is the classic add-in.
2. **Look at the schema file extension** in `Site Pages/PlumsailForms/`. `.designer.json` is the modern product on SharePoint Online. `.xfds` is Forms Designer or on-premises.
3. **Look at where the app is installed** — tenant App Catalog (SPFx) or the site's own add-ins (classic). The form URL alone does not tell you, so check the catalogue rather than inferring.

There is also a shortcut worth knowing: **the SharePoint add-in model was fully retired on 2 April 2026.** So if the forms are working today, they are SPFx — classic add-in forms stopped rendering months ago and would have been reported as broken long before any migration. Use the checks to confirm it rather than to discover it.

A fourth tell, from the store or App Catalog listing itself: the SPFx product describes itself as *"web parts and extensions"* and names its **field customizers** (Data Table, Signature, Likert Scale, Lookup) and the **Form Panel customizer**. Web parts, field customizers and form-panel customizers are SPFx extension types. A classic add-in has none of them — it has iframed add-in parts.

### Two different version numbers, and don't compare them

This catches people out. The **app package** (`.sppkg`) is versioned on a **1.x** track — the vendor's own upgrade note talks about moving from `v1.0.4.0` to `v1.0.5.0`. The **product** is versioned on a **4.x** track in the changelog. Seeing a package at `1.1.0.0` released in 2023 against a product at `4.2.x` is not a three-year-stale install: they are different things, and the package is the smaller half.

Read the installed package version in the **App Catalog → Apps for SharePoint → Version** column, not from the store listing, which tells you what the store is currently *offering*.

The package is updated by **deleting it and installing the current one** from AppSource — there is no in-place upgrade. And then the part that matters here:

> "re-save all the forms that you have in the latest version of Plumsail Forms designer app"

because re-saving **updates the scripts on each form's page**. Old forms keep working, but their pages carry scripts stamped at save time by whichever package version saved them. Which is the same conclusion the migration reaches from the other direction: the fix is a pass through the designer, per form.

### What is actually broken

Not the definition — and that is why this one confuses people. The definition really is content and really does travel:

```
Site Pages/PlumsailForms/{ListName}_{ContentTypeName}_{FormType}.designer.json
```

(`.xfds` on 2019/SE.) What does not travel is everything around it. The definition is inert on its own: it is *associated* with a list, *rendered* by a tenant-level SPFx component, under a tenant-level script policy, against a tenant-bound licence. None of those four are content, so none of them come with the site. The file arrives and the form does nothing.

Three consequences worth having in your head:

- **The definitions are in Site Pages, not in the list.** If the migration scope is "lists and libraries", the forms are not in scope. This is the single most common cause of "the Plumsail forms didn't come over".
- **The definition is not the association.** The form is attached per **list and content type** — the vendor's own provisioning API takes exactly those two as its arguments, and *"the form will replace a default new form in the target list"* is a write against them. So the file arriving in the target is necessary and not sufficient: something still has to associate it with the migrated list.
- **The association is by name.** Rename the list, or land the items under a differently named content type, and the definition sits there unreferenced while the form silently reverts to the default.

**Which is why the reattach is done in the designer, not in the filesystem.** Connect the designer to the *target* list, import or load the layout, and **save it once**. That single action writes the definition, the association, and the scripts on the form's page, all against the target tenant's installed package. It is what the vendor's own support tells people to do when a form has come adrift from its list — *"import the form in the editor, and save it again"* — and what their upgrade documentation requires after any package change. Copying files alone does not do it, and neither does hand-editing them.

Plan for it: **one designer pass per form**, and it is the same pass whether you are reattaching after a migration or re-saving after a package update. That is the work, and it is why the effort scales with the number of forms rather than being a one-off tenant-level task.

### What has to be true in the target first

All five. Any one of them missing gives you the default form or a script error, with no clue which.

1. **The SPFx package is in the target App Catalog, deployed tenant-wide.** Needs a SharePoint administrator. It is not a site-level "add an app" step on the modern product.
2. **Custom scripting is enabled on the destination site.** Off by default on group-connected sites:
   ```powershell
   Connect-SPOService -Url https://<org>-admin.sharepoint.com
   Set-SPOSite <site URL> -DenyAddAndCustomizePages 0
   ```
   Symptom if missed: *"custom web part cannot be created"* during the copy, and *"Scripting capabilities disabled for this site"* when the designer tries to save.
3. **The Plumsail hosts are trusted script sources.** SharePoint Online has enforced CSP since 1 March 2026, so a new tenant blocks them until told otherwise. Admin Center → **Advanced → Script sources**, add `https://*.plumsail.com` and `https://*.spform.com`. Symptom if missed: *"Something went wrong (script error)"*.
4. **The licence covers the target domain.** The subscription is issued per tenant and bound to the `*.sharepoint.com` domain named at checkout, and there is no published transfer procedure. Two things to settle with the vendor early, because the answer has a lead time and no documentation: whether the existing subscription is re-bound or a new one issued, and **whether both domains can be licensed at once across the cutover window** — that overlap is the thing you actually need. After activation, clear the browser cache; the licence is cached client-side and a stale one still reports as expired.
5. **Whoever edits forms has Full Control on the list *and* on the Site Pages library.** The designer writes to both.

### The steps

Order matters.

1. Migrate the **lists** that carry custom forms.
2. **Then migrate Site Pages, including subfolders.** Separate step, separate scope. Copy the whole folder.
3. Check the names still line up: list name and content type name must match the filenames in `PlumsailForms/`. Rename either and you have detached the form.
4. **Reattach each form: open it in the designer against the target list and save it.** Install the current app package first, so the pass stamps current scripts rather than needing a second one. This is the step that actually binds the form to the migrated list, and it doubles as the proof that the licence, the scripting policy and the permissions are all in place — those three fail here, loudly, rather than later in front of a user.
5. Open the list's **New** form in the browser. That is the test of success — not whether the files exist.

For more than about ten forms, script that reattach rather than clicking it: the provisioning package exposes `GetLayout()` to pull every layout from the source and `GenerateForms()` to write it against a target list and content type, which the vendor documents as working across lists, sites and tenants. It is the same operation the designer performs, in a loop. All three routes — content copy, designer export/import, provisioning API — assume the target list has the **same internal field names**, which it will if the list was migrated rather than rebuilt.

### Why it still doesn't work

Work down this list. It is ordered by how often it is the answer.

| Symptom | Cause | Fix |
|---|---|---|
| Default SharePoint form, no error | Site Pages never migrated | Copy `Site Pages/PlumsailForms/` |
| Default form, definition file is present | Never reattached to the migrated list, or the list or content type was renamed | Open the form in the designer against the target list and save it |
| Default form on every list in the tenant | App not deployed tenant-wide in the target | Deploy the SPFx package in the App Catalog |
| "Something went wrong (script error)" | CSP blocking the vendor hosts | Add both hosts to Trusted Script Sources |
| Form renders, says trial or expired | Licence bound to the old domain, or cached | Re-bind the subscription; clear the browser cache |
| Designer cannot save | Custom scripting denied, or not Full Control on Site Pages | `-DenyAddAndCustomizePages 0`; fix permissions |
| Form renders, flow behind it never fires | The flow used the ordinary SharePoint trigger and a helper column that did not survive | Re-point the flow; restore the helper columns |

That last row is worth expecting: many of these forms drive flows through the plain **When an item is created or modified** trigger and a pair of helper columns, not through a vendor connector at all. Those re-point like any other SharePoint flow — and the helper columns have to survive the list migration, which nobody checks because they look like ordinary columns.

### Audit the source before blaming the migration

- **Classic add-in forms are already gone.** The SharePoint add-in model was retired on **2 April 2026**. If any forms are the classic add-in flavour rather than SPFx, there is nothing to move: they go to SPFx or they are rebuilt. Check which app is installed in the source App Catalog — the form URL alone does not tell you which flavour you have.
- **Legacy-auth API keys are dead.** Microsoft's IDCRL retirement blocked legacy SharePoint logins from mid-February 2026, allowed an admin extension to 30 April 2026, and completed on 1 May 2026. Any vendor key created with the old "SharePoint custom credentials" pattern stopped working then. Do not recreate that pattern in the target: it also required MFA to be disabled on a service account, which will not pass a new tenant's baseline. Move to delegated or app-only auth.

## The option reformer doesn't offer — rebuild as a native list form

reformer classifies what exists. It has no way to know that a form *could* be something simpler, so it never proposes this. Worth considering for either of the two treatments above, because it is the only option that removes the form from the migration problem instead of moving it.

A native list form is configured with JSON: a header, a footer, and a body of named sections. No app package, no licence, no vendor host to allow through a content security policy, no per-form designer pass. That is the whole argument — everything the two sections above spend their length on stops applying.

### When it is the right call

When the vendor form is doing layout rather than logic. Section headings, a branded header, three fields to a row, required markers, fields that appear only when another answer makes them relevant — all of that is native now, and a form built out of it costs nothing at cutover.

### What you get, and what you don't

Native:

- **A branded header** — the header formatter takes arbitrary elements and styles, so a coloured band with a logo and a title is a few lines.
- **Grouped sections with headings** — the body formatter is `sections`, each with a `displayname` and a list of fields.
- **A multi-column layout.** Worth knowing because it is easy to assume otherwise: *"once the body is customized with one or more sections, the list or library form will switch to a multi-column layout."* You do not choose the column count, but you are not stuck with a single stack either.
- **Required markers, list validation, and read-only fields** via `fieldsettings`.
- **Conditional fields** — `=if([$Column] == 'Value', 'true', 'false')` per column, evaluated against the form as the user fills it in.

Not native, and no workaround worth building:

- **A wizard.** There is no step, page, Next/Back or per-step validation anywhere in the schema — `sections` and `fieldsettings` is the entire surface, and the body takes no clickable elements at all. You can fake the *appearance* by hiding one section's fields behind a helper "step" column, but you cannot fake the part that matters: a wizard's job is refusing to advance until the current step validates, and conditional visibility gates nothing. The user can skip ahead or save from step one. Take the scroll instead.
- **Cascading dropdowns.** One choice narrowing the next is not a native behaviour.
- **A value computed live in front of the user.** A calculated column can compose one — a document reference built from its parts, say — but only after save, not as they type.

### What has to be true first

1. **The form JSON is stored on the list content type**, so the content type must allow edits. Content types inherited from the Content Type Hub are **read-only by default**: set the content type to Edit mode, apply the formatting, set it back. This is the one that catches people, because nothing about the symptom points at the hub.
2. **The controlling columns are types conditional formulas support.** Not supported as a condition source: multi-select choice, multi-select lookup, multi-select person, calculated, currency, location, managed metadata, and the time part of a date. A single-select choice, number, date or yes/no column is safe.
3. **Required and conditional do not mix well.** Microsoft's own guidance for a conditional formula that will not work is to remove the column's required setting first, apply the formula, then reinstate it. Expect to do that, and expect the ordering to matter.
4. **Count the lookup columns.** Twelve lookups per query is the threshold, and a form with a dozen or more reference dropdowns crosses it. Choice columns do not count against it, and on a form whose dropdowns are fixed code lists they are the better modelling choice anyway.

### Does it migrate?

Undetermined, and do not assume it does. The JSON lives in `ClientFormCustomFormatter` on the **list** content type. No migration tool documents whether it carries that property: the vendor documentation covered in the Sources below addresses views and apps and is silent on form formatting, and the PnP provisioning engine states outright that it does not handle form formatting yet.

Which does not matter much, because unlike every other form in this document **the definition is a text file you can own**. Read it out before the wave:

```powershell
$ct = Get-PnPContentType -List $listName
$ct.ClientFormCustomFormatter | Out-File "form.json"
```

and put it back after:

```powershell
$ct.ClientFormCustomFormatter = $json
$ct.Update(0)
$clientContext.ExecuteQuery()
```

So the worst case is a scripted reapply per list — not a licence negotiation, not a designer pass per form. Settle it with one test rather than a support ticket: export the JSON, migrate a single list to a target, read the property off the arriving content type, and diff.

**Conditional show/hide formulas are stored separately, per field**, not in the form JSON. So a form that leans on them has two things to verify rather than one — another reason to prefer plain sections over a simulated wizard.

### Why it still doesn't work

Mostly because the form was rebuilt but the data model was not. If a form's second half is the same handful of fields repeated once per delivery stage, that is fifty-odd columns on one item and six chances to mis-key the same thing. It wants to be a parent item with a child list of stages, one row each. Do that and the form is small enough that none of the limitations above bite, the wizard has nothing left to page through, and the stages become reportable — every deliverable due next month, across every parent, is a view rather than an export.

Rebuilding the form and keeping the fifty columns gets you the same form with fewer features. The saving is in the model.

## Move via the documented route — customised list forms

### What is actually broken

The binding, and only the binding. A customised list form is a canvas app whose association with the list is recorded in the list folder's property bag under `PowerAppFormProperties` — and that value names an app **in the tenant it was made in**. Copy it verbatim and the target list points at an app that does not exist, so `new.aspx` and `edit.aspx` open to a spinner, an error or a blank frame while the list data looks perfect.

There is no automated route. The vendor of the platform says so plainly: *"there's currently no automated method in Power Apps to copy a form from one environment to another."* There is a documented manual one, and it is minutes per form against half a day to rebuild, which is the whole reason to prove it on one form before committing to rebuilds.

### What has to be true on the target list

- **The same internal column names.** Display names can differ; internal names cannot be changed after creation.
- **The same site language.** Cross-language moves are not supported.
- **No existing custom form.**

### Route A — the package route

1. Source list: **Integrate → Power Apps → Customize forms**, then in Studio **File → Export package**, choosing **Create as New**.
2. Unzip. In `Microsoft.PowerApps/apps/<guid>/`, replace the site URL, the list URL and the list GUID in all three places: `dataSources`, `dataSets` and the `embeddedApp` block. The same identifiers recur inside the `.msapp`, which is itself a zip.
3. Re-zip preserving the exact hierarchy. Zip the *contents*, not the containing folder — the most common failure of the whole route.
4. Target: **Import canvas app**, **Create as New**. "Update existing" does not work for forms.
5. Open the app, **delete and re-add the SharePoint data source**, save.
6. **File → Settings → Publish to SharePoint.** That publish is what binds the app to the list. Skipping it is why forms import cleanly and never appear.

Step 2 is hand surgery, and it is where the mistakes are. Retargeting the package with tooling removes it; hand-editing the JSON at scale does not survive contact with 70 forms.

### Route B — Copy Code

Create a fresh custom form on the target list, open source and target in Studio side by side, select all controls in the source and paste them into the target. It sidesteps the JSON entirely. Slower per form, far fewer mystery failures. **Use it as the fallback for anything Route A rejects**, rather than jumping to a rebuild.

### Clearing the stale binding

Remove the key, which restores the built-in form, then import and publish the real app, which writes a correct value:

```powershell
Get-PnPPropertyBag         -Folder /Lists/<ListName> -Key PowerAppFormProperties
Remove-PnPPropertyBagValue -Folder /Lists/<ListName> -Key PowerAppFormProperties
```

Find out how the migration tool's "customized list forms" copy option is configured **before the first wave**. It decides whether every custom-form list in the tenant arrives broken or clean, and it is one setting.

### One incompatibility to design around

A customised form cannot be shared separately — access is inherited from the list. **Users granted permission to specific items only do not get access to the customised form at all.** So a list must not have both item-level permissions and a Power Apps custom form. That matters when converting a Microsoft Form to a list, because item-level permissions are the right answer for submitter privacy, and it is a reason to keep the built-in form on a converted list.

## Convert to a SharePoint list — Microsoft Forms with a process behind them

### What is actually broken

Everything except the questions. Ownership cannot transfer between tenants at all: the delegate mechanism only works for an account disabled *within* the same tenant. Responses do not travel by any route. So the question is never "how do we move it" — it is "does this become a list, or get recreated and re-pointed".

Anything with a flow, an approval or a record behind it wants to be a **list**, because a list migrates like any other content and stops being a migration problem at all. Do the conversion in the **source** tenant, before the wave, so the conversion travels with everything else.

The shape of it: a list with a column per question, item-level permissions so submitters see only their own items, the built-in form as the entry screen, and the flow re-pointed from the Forms trigger to **When an item is created**.

## Recreate as a Form — the ones that must stay forms

For anonymous or external respondents, and for quizzes.

1. Use **Share as a template** to create the copy. This carries questions, sections, **branching**, theme and settings. It does **not** carry responses.
2. Give ownership to a **Microsoft 365 group**, not a person, so the next leaver does not repeat this exercise.
3. **Re-check the response settings.** Duplicating across an organisation boundary resets who is allowed to respond — anything you had locked down is now open.
4. Re-capture the forms inventory and re-point the flows (below).
5. **Fix every embedded link.** Pages, Teams tabs, email signatures, printed QR codes. The form id is new, so all of them are dead, and none of them report it.

Two things to test rather than assume, because neither is documented: **file-upload questions** and **collaborators**. One experiment each, before the first wave.

One environmental caveat: where the target tenant runs session controls in front of Microsoft 365, template duplication and the ownership-delegate page are both documented as breaking — users get a loading screen forever. Get a bypass agreed for the migration window before the first attempt, not during it.

### Re-pointing the flows

A flow names a form in **two** places — the `form_id` on the *When a new response is submitted* trigger and on the *Get response details* action — and then again in every expression that reads an answer, by question id. Recreating the form changes all of them.

**The flow does not error. It stops firing.** There is no failed run to notice, because the trigger never fires, so nothing appears in the run history and no alert goes off. Whoever owns the process finds out when someone asks why they never got the thing.

The form must be recreated, and the new inventory captured, **before** the solution package is imported, because the re-point resolves against that inventory.

## Investigate — Plumsail connectors

These are not SharePoint list forms and say nothing about how many list forms exist. `shared_plumsail` is the document-generation product and `shared_plumsailforms` is the cloud-hosted public web forms product. Two jobs, neither of them a form:

- **Re-authenticate every connection.** Connections never cross tenants.
- **Migrate the authentication method** if any connection still uses the retired custom-credentials pattern (see above). Delegated or app-only.

## Knowing the job is done

File counts prove nothing here — every one of these failures leaves the files in place. Verify by opening the thing a person uses:

- Each migrated list's **New** form opens the custom form, not the default one.
- One form **saved** from the designer in the target, which exercises licence, scripting policy and permissions together.
- Each re-pointed flow has a **successful run in the target**, triggered by a real submission rather than a manual test.
- The forms inventory re-captured from the target and diffed against the source, so anything not recreated is named rather than assumed.
- Re-capture the target's site listing and property-bag readings and run the scan again. Forms that were remediated should no longer appear; anything still listed is either missed or was never in scope.

## Sources

The facts above that come from vendor or Microsoft documentation, rather than from the scan:

- [Plumsail — form schema storage and file naming](https://plumsail.com/docs/forms-sp/how-to/form-versions.html)
- [Plumsail — migrating lists with custom forms between sites and tenants](https://plumsail.com/blog/sharegate-migrate/)
- [Plumsail — provisioning forms programmatically](https://plumsail.com/docs/forms-sp/provision/provision.html)
- [Plumsail — troubleshooting for SharePoint Online](https://plumsail.com/docs/forms-sp/troubleshooting/microsoft-365.html)
- [Plumsail — modern authentication and API keys](https://plumsail.com/blog/microsoft-enforcement-actions-api-keys/)
- [Plumsail — updating the app package, and re-saving forms afterwards](https://plumsail.com/docs/forms-sp/general/update-package.html)
- [Plumsail — product version history (the 4.x track)](https://plumsail.com/docs/forms-sp/general/version-history.html)
- [Plumsail community — classic add-in forms vs SPFx, and what breaks](https://community.plumsail.com/t/migrate-classic-plumsail-forms-add-in-model-to-plumsail-spfx-modern-forms-sharepoint-framework-what-breaks/20069)
- [Plumsail community — forms no longer connected to the list, and the re-save fix](https://community.plumsail.com/t/forms-not-connected-to-list-anymore/9603)
- [Plumsail community — lists stopped using the custom form assigned to the content type](https://community.plumsail.com/t/plumsail-suddenly-stopped-redirecting-lists-to-plumsail-forms/9299)
- [Microsoft — SharePoint Add-In retirement, 2 April 2026](https://learn.microsoft.com/en-us/sharepoint/dev/sp-add-ins/retirement-announcement-for-add-ins)
- [Microsoft — SharePoint Online CSP enforcement dates and guidance](https://techcommunity.microsoft.com/blog/spblog/sharepoint-online-content-security-policy-csp-enforcement-dates-and-guidance/4472662)
- [Microsoft — configuring the list form with header, footer and body sections](https://learn.microsoft.com/en-us/sharepoint/dev/declarative-customization/list-form-configuration)
- [Microsoft — conditional formulas to show or hide columns, and the unsupported column types](https://learn.microsoft.com/en-us/sharepoint/dev/declarative-customization/list-form-conditional-show-hide)
- [PnP — reading and writing `ClientFormCustomFormatter`, and the provisioning engine's gap](https://pnp.github.io/blog/post/updating-your-list-forms-using-your-provisioning-tool-of-choice/)
- [ShareGate — Migrate FAQ (views and apps; silent on form formatting)](https://help.sharegate.com/en/articles/10236131-sharegate-migrate-faq)
- [Microsoft — IDCRL legacy authentication retirement](https://techcommunity.microsoft.com/blog/microsoftmissioncriticalblog/legacy-sharepoint-authentication-idcrl-is-retiring-%E2%80%94-what-to-do-before-may-1-202/4499131)
