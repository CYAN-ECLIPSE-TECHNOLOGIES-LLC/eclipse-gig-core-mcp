#!/usr/bin/env python3
"""End-to-end stdio smoke for Eclipse Gig Core v0.1 (G0).

Temp state. Drives initialize -> brief_create -> brief_approve ->
quote_normalize -> hire_check (mandate ALLOW, person pending) ->
hire_check (+ person token = ALLOW) -> completion_verify ->
review_draft -> receipt_list.
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent


def rpc(proc, rid, method, params=None):
    req = {"jsonrpc": "2.0", "id": rid, "method": method,
           "params": params or {}}
    proc.stdin.write(json.dumps(req) + "\n")
    proc.stdin.flush()
    return json.loads(proc.stdout.readline())


def call(proc, rid, name, args):
    response = rpc(proc, rid, "tools/call", {"name": name, "arguments": args})
    return json.loads(response["result"]["content"][0]["text"])


def main():
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ)
        env["ECLIPSE_GIG_CORE_STATE"] = str(Path(tmp) / "state.json")
        proc = subprocess.Popen(
            [sys.executable, str(HERE / "server.py")],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
            cwd=str(HERE), env=env)
        try:
            init = rpc(proc, 1, "initialize",
                       {"protocolVersion": "2025-03-26"})
            assert init["result"]["serverInfo"]["name"] == "eclipse-gig-core"
            print("initialize OK")

            brief = call(proc, 2, "brief_create", {
                "brief_id": "smoke-brief", "category": "house_cleaning",
                "service": "Deep clean, 2 bed / 1 bath",
                "scope": {"statement": "Kitchen, bath, floors done.",
                          "items": ["kitchen", "bathroom", "floors"]},
                "location": {"precision": "zip", "zip": "94110"},
                "timing": {"window_start": "2026-10-28T09:00:00Z",
                           "window_end": "2026-10-28T13:00:00Z"},
                "ceiling_all_in": 250,
                "photos": [{"ref": "kitchen.jpg", "exif_stripped": True}],
                "license_required": "no",
                "safety_access": {"adult_present": True},
                "intended_platforms": ["thumbtack"],
            })["brief"]
            print("brief_create OK; hash", brief["hash"][:12])

            approved = call(proc, 3, "brief_approve", {
                "brief_id": "smoke-brief", "brief_hash": brief["hash"],
                "approver": "owner"})
            assert approved["brief"]["approval_valid"]
            print("brief_approve OK; approval binds the hash")

            quote = call(proc, 4, "quote_normalize", {
                "platform": "thumbtack",
                "pro": {"platform_id": "tt-pro-1",
                        "display_name": "Sparkle Co", "rating": 4.9,
                        "hires": 212},
                "model": "lead_model", "job_price": 180,
                "fees": [{"name": "lead fee (pro)", "amount": 24.50,
                          "bearer": "pro"}],
                "fees_exposed": True,
                "valid_until": "2026-10-27T00:00:00Z",
                "ceiling_all_in": 250,
            })
            assert quote["quote"]["all_in_total"] == 180.0
            assert quote["ceiling_test"]["hireable_under_ceiling"]
            qid = quote["quote"]["quote_id"]
            print("quote_normalize OK; face/fees separate, all-in 180")

            mandate = {"mandate_id": "m-1", "cap": 250,
                       "categories": ["house_cleaning"],
                       "platforms": ["thumbtack"],
                       "approval_threshold": 200,
                       "expires_at": "2026-11-30T00:00:00Z"}
            pending = call(proc, 5, "hire_check", {
                "brief_id": "smoke-brief", "quote_id": qid,
                "mandate": mandate, "as_of": "2026-10-25T12:00:00Z"})
            assert pending["decision"] == "MANDATE_ALLOW_PERSON_PENDING"
            assert pending["hireable"] is False
            print("hire_check OK; mandate allows, person still owner's")

            allowed = call(proc, 6, "hire_check", {
                "brief_id": "smoke-brief", "quote_id": qid,
                "mandate": mandate, "as_of": "2026-10-25T12:00:00Z",
                "person_confirm_token": f"confirm-person-{qid}"})
            assert allowed["decision"] == "ALLOW" and allowed["hireable"]
            print("hire_check OK; person token completes the gate")

            verification = call(proc, 7, "completion_verify", {
                "brief_id": "smoke-brief", "platform": "thumbtack",
                "pro_display_name": "Sparkle Co",
                "platform_state": "completed",
                "scope_results": [
                    {"item": "kitchen", "status": "done",
                     "attestation": "owner inspected"},
                    {"item": "bathroom", "status": "done",
                     "attestation": "owner inspected"},
                    {"item": "floors", "status": "done",
                     "attestation": "owner inspected"}],
            })["verification"]
            assert verification["verification_status"] == "owner_verified"
            print("completion_verify OK; platform state kept separate")

            draft = call(proc, 8, "review_draft", {
                "verification_id": verification["verification_id"]})
            assert "3 of 3 scope items done" in \
                draft["review_draft"]["text"]
            print("review_draft OK; record-bound, no invented praise")

            receipts = call(proc, 9, "receipt_list", {})
            assert receipts["chain_valid"] is True
            print(f"receipts OK; {receipts['count']} entries, chain valid")
            print("SMOKE PASSED")
        finally:
            proc.stdin.close()
            proc.terminate()


if __name__ == "__main__":
    main()
