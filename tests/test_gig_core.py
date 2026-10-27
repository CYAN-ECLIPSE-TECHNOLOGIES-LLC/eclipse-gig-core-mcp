#!/usr/bin/env python3
# Eclipse Gig Core MCP
# Copyright © 2026 Cyan Eclipse Technologies LLC · cetech.ai
# Eclipse Gig Core v0.1 (G0) tests.

"""Eclipse Gig Core v0.1 (G0) tests.
Run: python3 -m unittest discover tests"""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import server as S  # noqa: E402

AS_OF = "2026-10-25T12:00:00Z"


def make_brief(state, **overrides):
    args = {
        "brief_id": "brief-clean",
        "category": "house_cleaning",
        "service": "Deep clean, 2 bed / 1 bath",
        "scope": {
            "statement": "Kitchen, bathroom, floors, and surfaces "
                         "cleaned; trash out.",
            "items": ["kitchen", "bathroom", "floors"],
        },
        "location": {"precision": "zip", "zip": "94110"},
        "timing": {"window_start": "2026-10-28T09:00:00Z",
                   "window_end": "2026-10-28T13:00:00Z",
                   "flexible": True},
        "ceiling_all_in": 250,
        "tip_policy": {"mode": "owner_policy", "max": 30},
        "photos": [{"ref": "kitchen.jpg", "exif_stripped": True}],
        "license_required": "no",
        "safety_access": {"adult_present": True, "pets": "one dog",
                          "entry": "platform post-hire channel only"},
        "intended_platforms": ["thumbtack"],
        "prohibited_platforms": [],
        "details": {"bedrooms": 2, "frequency": "one_time"},
    }
    args.update(overrides)
    return S.t_brief_create(state, args)["brief"]


def approve(state, brief):
    return S.t_brief_approve(state, {
        "brief_id": brief["brief_id"], "brief_hash": brief["hash"],
        "approver": "owner", "approved_at": AS_OF})


def make_quote(state, **overrides):
    args = {
        "platform": "thumbtack",
        "pro": {"platform_id": "tt-pro-1", "display_name": "Sparkle Co",
                "rating": 4.9, "hires": 212, "license_claims": [],
                "badges": ["Exceptional"]},
        "model": "lead_model",
        "job_price": 180,
        "fees": [{"name": "lead fee (pro)", "amount": 24.50,
                  "bearer": "pro"}],
        "fees_exposed": True,
        "tax": 0,
        "valid_until": "2026-10-27T00:00:00Z",
        "raw_quote_ref": "fixture:thumbtack_requests#q1",
    }
    args.update(overrides)
    return S.t_quote_normalize(state, args)["quote"]


def make_mandate(**overrides):
    mandate = {
        "mandate_id": "mandate-1", "cap": 250,
        "categories": ["house_cleaning"], "platforms": ["thumbtack"],
        "approval_threshold": 200, "expires_at": "2026-11-30T00:00:00Z",
    }
    mandate.update(overrides)
    return mandate


class TestBrief(unittest.TestCase):
    def test_create_hashes_and_validates(self):
        state = S.empty_state()
        brief = make_brief(state)
        self.assertEqual(brief["version"], 1)
        self.assertTrue(brief["hash"])
        self.assertEqual(brief["status"], "draft")
        self.assertEqual(brief["photos"][0]["exif_stripped"], True)
        self.assertIn("stripped", brief["photos"][0]["exif_note"])
        with self.assertRaises(S.ToolError):
            make_brief(state, brief_id="b2", ceiling_all_in=None)

    def test_exact_address_precision_rejected(self):
        state = S.empty_state()
        with self.assertRaises(S.ToolError) as ctx:
            make_brief(state, location={
                "precision": "exact", "zip": "94110",
                "street": "1 Example St"})
        self.assertIn("LOCATION_PRECISION", str(ctx.exception))

    def test_approval_binds_exact_hash(self):
        state = S.empty_state()
        brief = make_brief(state)
        with self.assertRaises(S.ToolError):
            S.t_brief_approve(state, {"brief_id": "brief-clean",
                                      "brief_hash": "0" * 64})
        out = approve(state, brief)
        self.assertEqual(out["brief"]["status"], "approved")
        self.assertTrue(out["brief"]["approval_valid"])

    def test_post_approval_edit_invalidates_approval(self):
        state = S.empty_state()
        brief = approve(state, make_brief(state))["brief"]
        self.assertTrue(brief["approval_valid"])
        updated = S.t_brief_update(state, {
            "brief_id": "brief-clean",
            "changes": {"ceiling_all_in": 260}})
        self.assertTrue(updated["approval_invalidated"])
        self.assertEqual(updated["brief"]["version"], 2)
        self.assertIsNone(updated["brief"]["approval"])
        self.assertFalse(updated["brief"]["approval_valid"])
        self.assertNotEqual(updated["brief"]["hash"], brief["hash"])


class TestQuotes(unittest.TestCase):
    def test_lead_model_fees_separate_pro_fee_not_in_all_in(self):
        state = S.empty_state()
        quote = make_quote(state)
        self.assertEqual(quote["job_price_face"], 180.0)
        self.assertEqual(quote["fees"][0]["bearer"], "pro")
        self.assertEqual(quote["buyer_fees_total"], 0.0)
        self.assertEqual(quote["all_in_total"], 180.0)
        self.assertEqual(quote["fees_status"], "EXPOSED")

    def test_buyer_fees_and_tax_enter_all_in(self):
        state = S.empty_state()
        quote = make_quote(
            state, job_price=100, tax=8,
            fees=[{"name": "service fee", "amount": 12,
                   "bearer": "buyer"}])
        self.assertEqual(quote["all_in_total"], 120.0)
        self.assertEqual(quote["fee_bearer"], "buyer")

    def test_hourly_model_is_rate_times_owner_cap(self):
        state = S.empty_state()
        quote = make_quote(state, model="hourly", job_price=None,
                           hourly_rate=55, hour_cap=4)
        self.assertEqual(quote["job_price_face"], 220.0)
        self.assertEqual(quote["hourly"]["hour_cap"], 4.0)
        with self.assertRaises(S.ToolError):
            make_quote(state, model="hourly", job_price=None,
                       hourly_rate=55)

    def test_unexposed_fees_cannot_be_hireable_under_ceiling(self):
        state = S.empty_state()
        out = S.t_quote_normalize(state, {
            "platform": "thumbtack",
            "pro": {"platform_id": "tt-pro-2"},
            "model": "lead_model", "job_price": 100,
            "fees": [], "fees_exposed": False,
            "ceiling_all_in": 250})
        quote = out["quote"]
        self.assertEqual(quote["fees_status"], "UNEXPOSED")
        self.assertIsNone(quote["all_in_total"])
        self.assertFalse(out["ceiling_test"]["hireable_under_ceiling"])
        self.assertIn("UNEXPOSED", out["ceiling_test"]["reason"])

    def test_unexposed_with_written_owner_exception(self):
        state = S.empty_state()
        out = S.t_quote_normalize(state, {
            "platform": "thumbtack",
            "pro": {"platform_id": "tt-pro-2"},
            "model": "lead_model", "job_price": 100,
            "fees": [{"name": "service fee", "amount": 10,
                      "bearer": "buyer"}],
            "fees_exposed": False,
            "owner_fee_exception": {
                "by": "owner", "note": "approval pack 2026-10-25: "
                                       "fee schedule confirmed in-app"},
            "ceiling_all_in": 250})
        # The written exception lets the ceiling test run on the
        # owner-supplied itemization; the status stays UNEXPOSED
        # (the platform never exposed the fees) and the exception
        # itself is on the record.
        self.assertEqual(out["quote"]["fees_status"], "UNEXPOSED")
        self.assertIsNotNone(out["quote"]["owner_fee_exception"])
        self.assertEqual(out["quote"]["all_in_total"], 110.0)
        self.assertTrue(out["ceiling_test"]["hireable_under_ceiling"])
        self.assertIn("exception", out["ceiling_test"]["reason"])


class TestHireGate(unittest.TestCase):
    def setUp(self):
        self.state = S.empty_state()
        self.brief = approve(self.state, make_brief(self.state))["brief"]
        self.quote = make_quote(self.state)

    def check(self, **overrides):
        args = {"brief_id": "brief-clean",
                "quote_id": self.quote["quote_id"],
                "mandate": make_mandate(), "as_of": AS_OF}
        args.update(overrides)
        return S.t_hire_check(self.state, args)

    def test_allow_with_person_token_under_threshold(self):
        out = self.check(person_confirm_token=S.expected_person_token(
            self.quote["quote_id"]))
        self.assertEqual(out["decision"], "ALLOW")
        self.assertTrue(out["hireable"])

    def test_mandate_allow_without_person_token_not_hireable(self):
        out = self.check()
        self.assertEqual(out["decision"], "MANDATE_ALLOW_PERSON_PENDING")
        self.assertFalse(out["hireable"])
        self.assertTrue(any("PERSON_CONFIRM_REQUIRED" in n
                            for n in out["notes"]))

    def test_no_mandate_denies(self):
        out = self.check(mandate=None)
        self.assertEqual(out["decision"], "DENY")
        self.assertTrue(any("NO_MANDATE" in r for r in out["reasons"]))

    def test_expired_mandate_denies(self):
        out = self.check(mandate=make_mandate(
            expires_at="2026-10-01T00:00:00Z"))
        self.assertEqual(out["decision"], "DENY")
        self.assertTrue(any("expired" in r for r in out["reasons"]))

    def test_over_cap_and_over_ceiling_deny(self):
        rich = make_quote(self.state, job_price=240,
                          pro={"platform_id": "tt-pro-9"})
        out = self.check(quote_id=rich["quote_id"],
                         mandate=make_mandate(cap=200))
        self.assertEqual(out["decision"], "DENY")

    def test_allowlists_deny(self):
        out = self.check(mandate=make_mandate(categories=["plumbing"]))
        self.assertEqual(out["decision"], "DENY")
        out = self.check(mandate=make_mandate(platforms=["airtasker"]))
        self.assertEqual(out["decision"], "DENY")

    def test_above_threshold_needs_quote_token(self):
        pricey = make_quote(self.state, job_price=220,
                            pro={"platform_id": "tt-pro-7"})
        out = self.check(quote_id=pricey["quote_id"],
                         person_confirm_token=S.expected_person_token(
                             pricey["quote_id"]))
        self.assertEqual(out["decision"], "DENY")
        self.assertTrue(any("threshold" in r for r in out["reasons"]))
        out = self.check(
            quote_id=pricey["quote_id"],
            quote_approval_token=S.expected_quote_token(
                pricey["quote_id"]),
            person_confirm_token=S.expected_person_token(
                pricey["quote_id"]))
        self.assertEqual(out["decision"], "ALLOW")

    def test_unapproved_brief_denies(self):
        state = S.empty_state()
        make_brief(state)  # never approved
        quote = make_quote(state)
        out = S.t_hire_check(state, {
            "brief_id": "brief-clean", "quote_id": quote["quote_id"],
            "mandate": make_mandate(), "as_of": AS_OF,
            "person_confirm_token": S.expected_person_token(
                quote["quote_id"])})
        self.assertEqual(out["decision"], "DENY")
        self.assertTrue(any("not approved" in r for r in out["reasons"]))

    def test_unexposed_quote_denies_at_gate(self):
        hidden = S.t_quote_normalize(self.state, {
            "platform": "thumbtack", "pro": {"platform_id": "tt-pro-3"},
            "model": "lead_model", "job_price": 100, "fees": [],
            "fees_exposed": False})["quote"]
        out = self.check(quote_id=hidden["quote_id"],
                         person_confirm_token=S.expected_person_token(
                             hidden["quote_id"]))
        self.assertEqual(out["decision"], "DENY")
        self.assertTrue(any("UNEXPOSED" in r for r in out["reasons"]))

    def test_every_check_is_receipted(self):
        before = len(self.state["receipts"])
        self.check()
        self.check(mandate=None)
        checks = [r for r in self.state["receipts"]
                  if r["type"] == "hire_check"]
        self.assertEqual(len(self.state["receipts"]), before + 2)
        self.assertEqual(len(checks), 2)


class TestCompletionAndReview(unittest.TestCase):
    def setUp(self):
        self.state = S.empty_state()
        make_brief(self.state)

    def verify(self, **overrides):
        args = {
            "brief_id": "brief-clean", "platform": "thumbtack",
            "pro_display_name": "Sparkle Co",
            "platform_state": "completed",
            "scope_results": [
                {"item": "kitchen", "status": "done",
                 "attestation": "owner inspected"},
                {"item": "bathroom", "status": "done",
                 "attestation": "owner inspected"},
                {"item": "floors", "status": "done",
                 "attestation": "owner inspected"},
            ],
            "verified_at": AS_OF,
        }
        args.update(overrides)
        return S.t_completion_verify(self.state, args)["verification"]

    def test_platform_done_is_not_owner_verified_by_itself(self):
        record = self.verify(scope_results=[
            {"item": "kitchen", "status": "done", "attestation": "ok"},
            {"item": "bathroom", "status": "not_done",
             "attestation": "mirror streaks, owner photo filed"},
            {"item": "floors", "status": "done", "attestation": "ok"},
        ])
        # States stay separate: platform says completed, the
        # verification record says exception, and both are on record.
        self.assertEqual(record["platform_state"], "completed")
        self.assertEqual(record["verification_status"], "exception")
        self.assertTrue(record["platform_owner_mismatch"])

    def test_full_attestation_verifies(self):
        record = self.verify()
        self.assertEqual(record["verification_status"], "owner_verified")
        self.assertFalse(record["platform_owner_mismatch"])

    def test_review_draft_carries_no_unrecorded_sentiment(self):
        record = self.verify()  # no quality/timeliness/communication
        draft = S.t_review_draft(
            self.state, {"verification_id": record["verification_id"]})
        text = draft["review_draft"]["text"].lower()
        for word in S.QUALITY_CLAIM_WORDS:
            self.assertNotIn(word, text)
        self.assertIn("3 of 3 scope items done", text)
        self.assertIn("draft", draft["review_draft"]["status"].lower())

    def test_review_draft_uses_recorded_notes_verbatim(self):
        record = self.verify(
            timeliness="arrived inside the stated window",
            quality_notes="corners and baseboards done thoroughly")
        draft = S.t_review_draft(
            self.state, {"verification_id": record["verification_id"]})
        text = draft["review_draft"]["text"]
        self.assertIn("arrived inside the stated window", text)
        self.assertIn("corners and baseboards done thoroughly", text)

    def test_leverage_language_refused_at_draft_time(self):
        record = self.verify(
            quality_notes="fine, but refund or I post more")
        with self.assertRaises(S.ToolError) as ctx:
            S.t_review_draft(
                self.state, {"verification_id": record["verification_id"]})
        self.assertIn("leverage", str(ctx.exception))


class TestReceiptsAndDenylist(unittest.TestCase):
    def test_chain_valid_and_tamper_detected(self):
        state = S.empty_state()
        brief = approve(state, make_brief(state))["brief"]
        make_quote(state)
        out = S.t_receipt_list(state, {})
        self.assertTrue(out["chain_valid"])
        tampered = copy.deepcopy(state["receipts"])
        tampered[0]["detail"]["category"] = "forged"
        self.assertFalse(S.verify_receipt_chain(tampered))

    def test_forbidden_tools_rejected_by_transport(self):
        for name in ("hire_execute", "review_submit", "session_login",
                     "scrape_profiles"):
            resp = S.handle({"jsonrpc": "2.0", "id": 1,
                             "method": "tools/call",
                             "params": {"name": name, "arguments": {}}})
            self.assertIn("error", resp)
            self.assertIn("G0-forbidden", resp["error"]["message"])
        listed = {t["name"] for t in S.tool_list()}
        self.assertTrue(listed.isdisjoint(S.FORBIDDEN_TOOL_NAMES))


if __name__ == "__main__":
    unittest.main()

# Eclipse Gig Core MCP · © 2026 Cyan Eclipse Technologies LLC · cetech.ai
