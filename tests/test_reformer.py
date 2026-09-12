"""Everything here is synthetic. This repo is public, so no fixture carries a
real tenant, site, list or form id — the shapes are what matter, and the shapes
are public behaviour."""
from __future__ import annotations

import contextlib
import io
import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

from reformer import cli
from reformer.classify import CONTENT, CONVERT, RECREATE, ROUTE, classify, totals
from reformer.package import Container, walk_dicts
from reformer.report import to_html, to_json
from reformer.scan import (merge, scan_forms_listing, scan_package, scan_property_bags,
                           scan_site_listing)

FORM_A = "AAAAFORM" + "0" * 60 + "01u"
FORM_B = "BBBBFORM" + "0" * 60 + "02u"
FORM_OTHER = "CCCCFORM" + "0" * 60 + "03u"
Q1, Q2 = "r" + "a1" * 16, "r" + "a2" * 16
LIST_GUID = "11111111-2222-4333-8444-555555555555"
SITE_GUID = "99999999-8888-4777-8666-555555555555"
OLD_SITE = "https://oldtenant.sharepoint.com/sites/Example"

FORMS_HOST = {"connectionName": "shared_microsoftforms",
              "apiId": "/providers/Microsoft.PowerApps/apis/shared_microsoftforms"}


def forms_flow() -> dict:
    return {"properties": {"definition": {
        "triggers": {"When_a_new_response_is_submitted": {
            "type": "OpenApiConnectionWebhook",
            "inputs": {"host": {**FORMS_HOST, "operationId": "CreateFormWebhook"},
                       "parameters": {"form_id": FORM_A}}}},
        "actions": {
            "Get_response_details": {"type": "OpenApiConnection", "inputs": {
                "host": {**FORMS_HOST, "operationId": "GetFormResponseById"},
                "parameters": {"form_id": FORM_A, "response_id": "@triggerOutputs()"}}},
            "Compose_name": {"type": "Compose",
                             "inputs": f"@{{outputs('Get_response_details')?['body/{Q1}']}}"},
            "Compose_rating": {"type": "Compose",
                               "inputs": f"@{{outputs('Get_response_details')?['body/{Q2}']}}"},
            "Not_forms": {"type": "OpenApiConnection", "inputs": {
                "host": {"connectionName": "shared_custom", "operationId": "GetForm"},
                "parameters": {"form_id": FORM_OTHER}}},
            "Expression_form": {"type": "OpenApiConnection", "inputs": {
                "host": {**FORMS_HOST, "operationId": "GetFormResponseById"},
                "parameters": {"form_id": "@variables('whichForm')"}}},
        }}}}


def embedded_app_json() -> dict:
    return {"properties": {"embeddedApp": {
        "siteId": OLD_SITE, "listId": LIST_GUID,
        "listUrl": f"{OLD_SITE}/Lists/Travel%20Requests/AllItems.aspx",
        "type": "SharepointFormApp"}}}


def build_msapp() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("Properties.json", json.dumps(
            {"siteId": SITE_GUID, "listId": LIST_GUID, "listUrl": "/sites/Example/Lists/Travel",
             "type": "SharepointFormApp"}))
        z.writestr("References/DataSources.json", json.dumps(
            {"DataSources": [{"DatasetName": OLD_SITE, "TableName": LIST_GUID}]}))
        z.writestr("Resources/logo.png", b"\x89PNG\r\n\x1a\n binary")
    return buf.getvalue()


def build_package(path: Path, with_form_app: bool = True, with_flow: bool = True) -> Path:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("solution.xml", "<ImportExportXml><SolutionManifest/></ImportExportXml>")
        if with_flow:
            z.writestr("Workflows/Demo-11111111.json", json.dumps(forms_flow(), indent=1))
        if with_form_app:
            z.writestr("Microsoft.PowerApps/apps/1/app.json", json.dumps(embedded_app_json()))
            z.writestr("CanvasApps/pub_form_DocumentUri.msapp", build_msapp())
    return path


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="reformer_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.zip = build_package(self.tmp / "Demo.zip")

    def test_opens_the_canvas_app_inside_the_package(self):
        c = Container.load(self.zip)
        self.assertEqual(c.canvas_apps(), ["CanvasApps/pub_form_DocumentUri.msapp"])
        addresses = [name for name, _ in c.texts()]
        self.assertIn("CanvasApps/pub_form_DocumentUri.msapp!Properties.json", addresses)

    def test_binary_members_are_not_treated_as_text(self):
        c = Container.load(self.zip)
        self.assertNotIn("CanvasApps/pub_form_DocumentUri.msapp!Resources/logo.png",
                         [name for name, _ in c.texts()])

    def test_walk_dicts_reaches_a_nested_block(self):
        found = [d for d in walk_dicts(embedded_app_json()) if d.get("type") == "SharepointFormApp"]
        self.assertEqual(len(found), 1)


class ScanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="reformer_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.res = scan_package(Container.load(build_package(self.tmp / "Demo.zip")))

    def test_finds_a_microsoft_form_only_on_the_forms_connector(self):
        ids = {f.identity for f in self.res.of_kind("microsoft-form")}
        self.assertEqual(ids, {FORM_A})
        self.assertNotIn(FORM_OTHER, ids)       # form_id on a different connector

    def test_an_expression_form_id_is_noted_not_counted(self):
        self.assertTrue(any("expression" in n for n in self.res.notes))

    def test_counts_the_questions_a_flow_reads(self):
        self.assertEqual(self.res.questions[FORM_A], {Q1, Q2})

    def test_finds_the_customised_list_form_binding(self):
        forms = self.res.of_kind("list-form")
        self.assertTrue(forms)
        f = forms[0]
        self.assertEqual(f.identity, LIST_GUID)
        self.assertEqual(f.name, "Travel Requests")     # decoded from the list URL
        self.assertEqual(f.detail["site_id"], OLD_SITE)
        self.assertFalse(f.detail["site_id_is_guid"])

    def test_a_guid_site_id_is_flagged_as_such(self):
        # the copy inside the .msapp identifies its site by GUID, not URL
        guid_sited = [f for f in self.res.of_kind("list-form") if f.detail.get("site_id_is_guid")]
        self.assertTrue(guid_sited, "the .msapp binding should be found too")

    def test_a_package_with_no_forms_finds_none(self):
        res = scan_package(Container.load(
            build_package(self.tmp / "Empty.zip", with_form_app=False, with_flow=False)))
        self.assertEqual(res.findings, [])

    def test_plumsail_connectors_are_not_counted_as_forms(self):
        flow = {"properties": {"definition": {"actions": {"Doc": {"inputs": {
            "host": {"connectionName": "shared_plumsail"}, "parameters": {}}}}}}}
        z = self.tmp / "Plum.zip"
        with zipfile.ZipFile(z, "w") as zf:
            zf.writestr("Workflows/P.json", json.dumps(flow))
        res = scan_package(Container.load(z))
        self.assertEqual([f.kind for f in res.findings], ["plumsail-connector"])
        self.assertIn("not a SharePoint form", res.findings[0].name)


class CaptureTests(unittest.TestCase):
    def test_site_listing_finds_plumsail_definitions(self):
        rows = [{"ServerRelativeUrl": "/sites/Example/SitePages/PlumsailForms/Travel_Item_New.designer.json"},
                {"ServerRelativeUrl": "/sites/Example/SitePages/Home.aspx"}]
        res = scan_site_listing(rows, "Example")
        kinds = {f.kind for f in res.findings}
        self.assertEqual(kinds, {"plumsail-form"})
        plum = res.of_kind("plumsail-form")[0]
        self.assertEqual(plum.name, "Travel")   # the list the definition serves

    def test_infopath_templates_are_ignored(self):
        """There is no InfoPath to find, so a template file is not a row to act
        on. Reporting one would only add work nobody has to do."""
        rows = [{"ServerRelativeUrl": "/sites/Example/Forms/Legacy.xsn"},
                {"ServerRelativeUrl": "/sites/Example/Forms/manifest.xsf"}]
        res = scan_site_listing(rows, "Example")
        self.assertEqual(res.findings, [])

    def test_property_bags_find_customised_forms(self):
        rows = [{"site": "https://oldtenant.sharepoint.com/sites/Example", "list": "Travel Requests",
                 "PowerAppFormProperties": '{"appId":"00000000-0000-0000-0000-000000000001"}'},
                {"site": "https://oldtenant.sharepoint.com/sites/Example", "list": "No Form"}]
        res = scan_property_bags(rows)
        self.assertEqual(len(res.of_kind("list-form")), 1)
        self.assertEqual(res.of_kind("list-form")[0].name, "Travel Requests")


class ClassifyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="reformer_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.res = scan_package(Container.load(build_package(self.tmp / "Demo.zip")))

    def test_a_form_with_a_flow_behind_it_becomes_a_list(self):
        item = [i for i in classify(self.res) if i.kind == "microsoft-form"][0]
        self.assertEqual(item.treatment, CONVERT)
        self.assertTrue(any("responses do not migrate" in f for f in item.flags))

    def test_a_form_with_nothing_downstream_is_recreated_instead(self):
        item = [i for i in classify(self.res, drives_a_process=False) if i.kind == "microsoft-form"][0]
        self.assertEqual(item.treatment, RECREATE)

    def test_each_question_read_adds_to_the_upper_estimate(self):
        with_qs = [i for i in classify(self.res) if i.kind == "microsoft-form"][0]
        bare = self.res
        bare.questions = {}
        without = [i for i in classify(bare) if i.kind == "microsoft-form"][0]
        self.assertGreater(with_qs.high_hours, without.high_hours)

    def test_a_list_form_takes_the_route_and_warns_about_preconditions(self):
        item = [i for i in classify(self.res) if i.kind == "list-form"][0]
        self.assertEqual(item.treatment, ROUTE)
        self.assertTrue(any("internal column names" in f for f in item.flags))

    def test_a_property_bag_form_warns_about_the_stale_binding(self):
        res = scan_property_bags([{"site": "s", "list": "Travel", "PowerAppFormProperties": "x"}])
        item = classify(res)[0]
        self.assertTrue(any("clear the property bag" in f for f in item.flags))

    def test_a_plumsail_form_travels_with_the_content_but_flags_the_licence(self):
        res = scan_site_listing(
            [{"ServerRelativeUrl": "/sites/E/SitePages/PlumsailForms/A_Item_New.designer.json"}], "E")
        item = classify(res)[0]
        self.assertEqual(item.treatment, CONTENT)
        self.assertTrue(any("licence" in f for f in item.flags))
        self.assertTrue(any("classic add-in" in f for f in item.flags))

    def test_one_form_found_in_several_places_is_one_row(self):
        """The binding repeats in the app JSON and inside the .msapp. Counting
        both would overstate the inventory and double the effort figure."""
        bindings = [f for f in self.res.of_kind("list-form")]
        self.assertGreater(len(bindings), 1, "fixture should find the binding twice")
        rows = [i for i in classify(self.res) if i.kind == "list-form"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].name, "Travel Requests")   # the richer occurrence won

    def test_totals_convert_hours_to_days(self):
        t = totals(classify(self.res))
        self.assertEqual(t["forms"], len(classify(self.res)))
        self.assertGreater(t["days_high"], 0)
        self.assertLessEqual(t["days_low"], t["days_high"])


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="reformer_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.res = scan_package(Container.load(build_package(self.tmp / "Demo.zip")))
        self.items = classify(self.res)

    def test_json_carries_the_items_and_totals(self):
        j = to_json(self.res, self.items, ["Demo.zip"])
        self.assertEqual(j["sources"], ["Demo.zip"])
        self.assertIn("microsoft-form", j["summary"])
        self.assertEqual(j["totals"]["forms"], len(self.items))

    def test_html_states_the_floor_caveat_and_escapes_content(self):
        html = to_html(self.res, self.items, ["Demo.zip"])
        self.assertIn("is a floor, not a total", html)
        self.assertIn("--forms-listing", html)
        self.assertIn("Microsoft Forms", html)
        self.assertIn("Customised list forms", html)

    def test_html_is_honest_when_nothing_was_found(self):
        empty = scan_package(Container.load(
            build_package(self.tmp / "Empty.zip", with_form_app=False, with_flow=False)))
        html = to_html(empty, classify(empty), ["Empty.zip"])
        self.assertIn("only if the inputs covered", html)


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="reformer_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.zip = build_package(self.tmp / "Demo.zip")

    def run_cli(self, argv) -> tuple[int, str]:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            code = cli.main(argv)
        return code, buf.getvalue()

    def test_scan_writes_both_reports_and_exits_2_when_work_was_found(self):
        j, h = self.tmp / "r.json", self.tmp / "r.html"
        code, out = self.run_cli(["scan", str(self.zip), "--json", str(j), "--html", str(h)])
        self.assertEqual(code, 2, out)
        self.assertTrue(j.exists() and h.exists())
        self.assertEqual(json.loads(j.read_text())["totals"]["forms"], 2)

    def test_scan_of_a_clean_package_exits_0(self):
        clean = build_package(self.tmp / "Clean.zip", with_form_app=False, with_flow=False)
        code, out = self.run_cli(["scan", str(clean)])
        self.assertEqual(code, 0, out)

    def test_a_folder_of_packages_works(self):
        code, out = self.run_cli(["scan", str(self.tmp)])
        self.assertEqual(code, 2, out)

    def test_captures_can_be_scanned_without_any_package(self):
        cap = self.tmp / "listing.json"
        cap.write_text(json.dumps({"value": [
            {"ServerRelativeUrl": "/sites/E/SitePages/PlumsailForms/A_Item_New.designer.json"}]}))
        code, out = self.run_cli(["scan", "--site-listing", str(cap)])
        self.assertEqual(code, 2, out)
        self.assertIn("Plumsail list forms", out)

    def test_nothing_to_scan_is_a_tool_error(self):
        code, out = self.run_cli(["scan"])
        self.assertEqual(code, 1)
        self.assertIn("nothing to scan", out)

    def test_a_bad_zip_is_a_tool_error_not_a_crash(self):
        bad = self.tmp / "bad.zip"
        bad.write_bytes(b"this is not a zip")
        code, out = self.run_cli(["scan", str(bad)])
        self.assertEqual(code, 1)

    def test_the_cli_reminds_you_the_forms_count_is_a_floor(self):
        _, out = self.run_cli(["scan", str(self.zip)])
        self.assertIn("only the ones a flow names", out)
        self.assertIn("--forms-listing", out)


class FormsListingTests(unittest.TestCase):
    """A tenant enumeration turns the Forms floor into a real count."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="reformer_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_a_listing_supplies_forms_no_package_names(self):
        rows = [{"id": FORM_B, "title": "Staff survey", "owner": "someone@example.invalid"},
                {"id": FORM_OTHER, "title": "Kit request", "ownerContext": "groups"}]
        res = scan_forms_listing(rows, "tenant.json")
        self.assertEqual({f.identity for f in res.of_kind("microsoft-form")}, {FORM_B, FORM_OTHER})
        self.assertEqual(res.of_kind("microsoft-form")[0].name, "Staff survey")
        self.assertEqual(res.of_kind("microsoft-form")[0].detail["owner"], "someone@example.invalid")

    def test_a_row_with_no_id_is_skipped(self):
        self.assertEqual(scan_forms_listing([{"title": "no id"}], "t.json").findings, [])

    def test_the_report_says_the_count_is_real_once_enumerated(self):
        res = scan_forms_listing([{"id": FORM_B, "title": "Staff survey"}], "tenant.json")
        html = to_html(res, classify(res), ["tenant.json"], enumerated=True)
        self.assertIn("Counted from a tenant enumeration", html)
        self.assertIn("group", html)            # the gap that survives it
        self.assertNotIn("is a floor, not a total", html)

    def test_the_cli_stops_calling_it_a_floor_when_given_a_listing(self):
        cap = self.tmp / "tenant.json"
        cap.write_text(json.dumps([{"id": FORM_B, "title": "Staff survey"}]))
        j = self.tmp / "r.json"
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            code = cli.main(["scan", "--forms-listing", str(cap), "--json", str(j)])
        self.assertEqual(code, 2)
        self.assertNotIn("only the ones a flow names", buf.getvalue())
        self.assertTrue(json.loads(j.read_text())["forms_count_is_complete"])


class MergeTests(unittest.TestCase):
    def test_merging_keeps_one_row_per_thing(self):
        rows = [{"ServerRelativeUrl": "/sites/E/SitePages/PlumsailForms/A_Item_New.designer.json"}]
        a, b = scan_site_listing(rows, "E"), scan_site_listing(rows, "E")
        self.assertEqual(len(merge(a, b).findings), 1)


if __name__ == "__main__":
    unittest.main()
