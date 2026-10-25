#!/usr/bin/env python3
"""Eclipse Gig Core MCP — v0.1.0, phase G0 (shared Task Brief core).

Powered by Cyan Eclipse Technologies (cetech.ai).

The Eclipse gig adapter family — one canonical, owner-approved Task
Brief becomes a native request, offer round, booking, or prep pack on
each task marketplace, according to what that platform actually
sanctions. Hiring happens only inside an Eclipse Procure / Agent
Wallet mandate. It never diverts a hire off-platform, never invents
a sanctioned surface that does not exist, and never posts a brief
the owner has not approved.

This server is the SHARED CORE (spec eclipse-gig-family-spec-20261025
sections 5-7). It owns:
  * the canonical Task Brief object — versioned, SHA-256 hash-bound,
    owner-approved; any post-approval edit invalidates approval;
  * the quote normalization engine — every platform model (lead,
    stated-budget, fixed-price, hourly) normalizes to one record with
    face price and itemized fees FOREVER separate and one ALL-IN
    total; a quote whose fees are UNEXPOSED cannot be hireable under
    a ceiling;
  * the hire gate — a mandate evaluation (cap, category + platform
    allowlists, approval threshold, expiry) returning ALLOW/DENY,
    receipted either way. In v1, selecting a PERSON requires an
    owner-confirm token even when a mandate allows the money;
  * completion verification records — platform state and owner
    verification are separate fields and are never merged;
  * review drafts generated ONLY from a verification record.

G0 SCOPE: fixtures and evaluation only. NO live platform call exists
in this file, no hire is executed, no review is submitted, and no
payment moves. The platform is merchant of record on every real hire
(spec section 6); this core only evaluates and records.

Transport: MCP over stdio (newline-delimited JSON-RPC 2.0), stdlib only.
State: $ECLIPSE_GIG_CORE_STATE or ./data/state.json beside this file.
"""
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
STATE_PATH = Path(os.environ.get(
    "ECLIPSE_GIG_CORE_STATE", HERE / "data" / "state.json"))

BRIEF_CONTENT_FIELDS = [
    "category", "service", "scope", "location", "timing",
    "ceiling_all_in", "tip_policy", "photos", "license_required",
    "safety_access", "intended_platforms", "prohibited_platforms",
    "details",
]

QUOTE_MODELS = {"lead_model", "stated_budget", "fixed_price", "hourly"}

# Words a review draft may only contain when the verification record
# itself carries quality notes (spec 7.3: no sentiment not in record).
QUALITY_CLAIM_WORDS = ["excellent", "great", "superb", "outstanding",
                       "fantastic", "quality", "wonderful", "amazing"]

# Prohibited leverage language, filtered at draft time (spec 7.3).
LEVERAGE_PATTERNS = ["refund or", "or i will post", "or i'll post",
                     "take this down", "or else i", "one star unless",
                     "1 star unless", "negative review unless"]


class ToolError(Exception):
    pass


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def parse_time(value):
    if value is None:
        return None
    text = str(value).strip()
    if len(text) == 10:
        text += "T00:00:00+00:00"
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def money(value) -> float:
    return round(float(value), 2)


# --------------------------------------------------------------------- state
def empty_state() -> dict:
    return {"briefs": {}, "quotes": {}, "verifications": {},
            "receipts": []}


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return empty_state()


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=1))


# ------------------------------------------------------------------ receipts
def emit_receipt(state: dict, rtype: str, detail: dict) -> dict:
    """Append-only, hash-chained (house pattern)."""
    prev = state["receipts"][-1]["hash"] if state["receipts"] else "GENESIS"
    entry = {"seq": len(state["receipts"]) + 1, "ts": int(time.time()),
             "type": rtype, "prev_hash": prev, "detail": detail}
    entry["hash"] = sha(prev + canon(
        {k: v for k, v in entry.items() if k != "hash"}))
    state["receipts"].append(entry)
    return entry


def verify_receipt_chain(receipts) -> bool:
    prev = "GENESIS"
    for entry in receipts:
        if entry.get("prev_hash") != prev:
            return False
        expected = sha(prev + canon(
            {k: v for k, v in entry.items() if k != "hash"}))
        if entry.get("hash") != expected:
            return False
        prev = entry["hash"]
    return True


# --------------------------------------------------------------------- briefs
def brief_content(brief: dict) -> dict:
    return {k: brief.get(k) for k in BRIEF_CONTENT_FIELDS}


def brief_hash(brief: dict) -> str:
    return sha(canon(brief_content(brief)))


def validate_brief_content(content: dict) -> None:
    if not str(content.get("category") or "").strip():
        raise ToolError("brief requires a category")
    if not str(content.get("service") or "").strip():
        raise ToolError("brief requires a service")
    scope = content.get("scope") or {}
    if not str(scope.get("statement") or "").strip():
        raise ToolError("brief requires scope.statement "
                        "(what done looks like)")
    location = content.get("location") or {}
    precision = str(location.get("precision") or "zip").lower()
    if precision != "zip":
        raise ToolError(
            "LOCATION_PRECISION: briefs carry ZIP-tier location only; "
            "the exact address is released only inside a platform's "
            "own post-hire flow (spec 5.1/8.4)")
    if not str(location.get("zip") or "").strip():
        raise ToolError("brief requires location.zip (ZIP-tier)")
    timing = content.get("timing") or {}
    if not timing.get("window_start") or not timing.get("window_end"):
        raise ToolError("brief requires timing.window_start/window_end")
    ceiling = content.get("ceiling_all_in")
    if ceiling is None or float(ceiling) <= 0:
        raise ToolError("brief requires a positive ceiling_all_in "
                        "(one ALL-IN number the owner authorizes)")
    license_required = content.get("license_required")
    if license_required not in ("unknown", "no") and not (
            isinstance(license_required, str)
            and license_required.startswith("yes:")):
        raise ToolError("license_required must be 'unknown', 'no', or "
                        "'yes:<type>' (spec 5.1)")


def public_brief(brief: dict) -> dict:
    out = json.loads(json.dumps(brief))
    out["approval_valid"] = bool(
        brief.get("approval")
        and brief["approval"].get("brief_hash") == brief["hash"])
    return out


def t_brief_create(state, args):
    content = {k: args.get(k) for k in BRIEF_CONTENT_FIELDS}
    content["photos"] = content.get("photos") or []
    content["intended_platforms"] = content.get("intended_platforms") or []
    content["prohibited_platforms"] = \
        content.get("prohibited_platforms") or []
    content["details"] = content.get("details") or {}
    validate_brief_content(content)
    photos = []
    for photo in content["photos"]:
        photos.append({
            "ref": str(photo.get("ref", "")),
            # EXIF/geolocation stripping is recorded on the photo
            # record itself; unstripped photos are flagged, and an
            # adapter must not use them (spec 5.1).
            "exif_stripped": bool(photo.get("exif_stripped", False)),
            "exif_note": ("EXIF/geolocation stripped before adapter use"
                          if photo.get("exif_stripped")
                          else "NOT stripped — adapter use blocked"),
        })
    content["photos"] = photos
    brief_id = str(args.get("brief_id") or "")
    if not brief_id:
        brief_id = "brief_" + sha(canon(content) + now_iso())[:12]
    if brief_id in state["briefs"]:
        raise ToolError(f"brief already exists: {brief_id}")
    brief = dict(content)
    brief.update({"brief_id": brief_id, "version": 1,
                  "status": "draft", "approval": None})
    brief["hash"] = brief_hash(brief)
    state["briefs"][brief_id] = brief
    receipt = emit_receipt(state, "brief_created", {
        "brief_id": brief_id, "version": 1, "hash": brief["hash"],
        "category": brief["category"],
        "ceiling_all_in": money(brief["ceiling_all_in"])})
    return {"brief": public_brief(brief), "receipt_seq": receipt["seq"]}


def t_brief_update(state, args):
    brief_id = str(args.get("brief_id") or "")
    brief = state["briefs"].get(brief_id)
    if not brief:
        raise ToolError(f"unknown brief: {brief_id}")
    changes = args.get("changes") or {}
    unknown = set(changes) - set(BRIEF_CONTENT_FIELDS)
    if unknown:
        raise ToolError(f"not brief content fields: {sorted(unknown)}")
    was_approved = bool(brief.get("approval"))
    old_hash = brief["hash"]
    for key, value in changes.items():
        brief[key] = value
    validate_brief_content(brief_content(brief))
    brief["version"] += 1
    brief["hash"] = brief_hash(brief)
    # Any post-approval edit invalidates the approval for the changed
    # brief (spec 5.1: approval binds hashes, not vibes).
    brief["approval"] = None
    brief["status"] = "draft"
    receipt = emit_receipt(state, "brief_version_created", {
        "brief_id": brief_id, "version": brief["version"],
        "old_hash": old_hash, "new_hash": brief["hash"],
        "changed_fields": sorted(changes),
        "approval_invalidated": was_approved})
    return {"brief": public_brief(brief), "receipt_seq": receipt["seq"],
            "approval_invalidated": was_approved}


def t_brief_approve(state, args):
    brief_id = str(args.get("brief_id") or "")
    brief = state["briefs"].get(brief_id)
    if not brief:
        raise ToolError(f"unknown brief: {brief_id}")
    claimed = str(args.get("brief_hash") or "")
    if claimed != brief["hash"]:
        raise ToolError(
            "approval binds the exact brief hash: supplied "
            f"{claimed or '(none)'} != current {brief['hash']}")
    approval = {
        "approver": str(args.get("approver") or "owner"),
        "approved_at": str(args.get("approved_at") or now_iso()),
        "brief_hash": brief["hash"],
        "variant_hashes": args.get("variant_hashes") or {},
    }
    brief["approval"] = approval
    brief["status"] = "approved"
    receipt = emit_receipt(state, "brief_approved", {
        "brief_id": brief_id, "version": brief["version"],
        "brief_hash": brief["hash"], "approver": approval["approver"],
        "variant_hashes": approval["variant_hashes"]})
    return {"brief": public_brief(brief), "receipt_seq": receipt["seq"]}


def t_brief_read(state, args):
    brief = state["briefs"].get(str(args.get("brief_id") or ""))
    if not brief:
        raise ToolError(f"unknown brief: {args.get('brief_id')}")
    return {"brief": public_brief(brief)}


# --------------------------------------------------------------------- quotes
def normalize_quote(raw: dict) -> dict:
    """Normalize any platform model to one quote record (spec 5.3).

    Face price and itemized fees stay separate forever. The ALL-IN
    total counts the face plus buyer-borne fees plus platform-stated
    tax. Pro-borne fees are itemized (they explain quote levels) but
    are not charged to the buyer. If the platform does not expose its
    fees, the quote is UNEXPOSED and carries no all-in total at all.
    """
    model = str(raw.get("model") or "")
    if model not in QUOTE_MODELS:
        raise ToolError(f"unknown quote model: {model or '(none)'}; "
                        f"expected one of {sorted(QUOTE_MODELS)}")
    pro = raw.get("pro") or {}
    if not pro.get("platform_id"):
        raise ToolError("quote requires pro.platform_id")
    hourly = None
    if model == "hourly":
        rate = raw.get("hourly_rate")
        cap = raw.get("hour_cap")
        if rate is None or cap is None:
            raise ToolError("hourly quotes require hourly_rate and the "
                            "owner-approved hour_cap (spec 5.3)")
        face = money(float(rate) * float(cap))
        hourly = {"rate": money(rate), "hour_cap": float(cap),
                  "basis": "rate x owner-approved hour cap; overruns "
                           "return to review, never auto-extend"}
    else:
        if raw.get("job_price") is None:
            raise ToolError(f"model {model} requires job_price")
        face = money(raw["job_price"])
    fees = []
    for fee in raw.get("fees") or []:
        bearer = str(fee.get("bearer") or "")
        if bearer not in ("buyer", "pro", "split"):
            raise ToolError("each fee requires bearer: buyer|pro|split")
        fees.append({"name": str(fee.get("name") or "fee"),
                     "amount": money(fee["amount"]), "bearer": bearer})
    bearers = {f["bearer"] for f in fees}
    fee_bearer = ("split" if len(bearers) > 1
                  else (bearers.pop() if bearers else "none"))
    fees_exposed = bool(raw.get("fees_exposed", False))
    tax = money(raw.get("tax") or 0)
    buyer_fees = money(sum(f["amount"] for f in fees
                           if f["bearer"] in ("buyer", "split")))
    exception = raw.get("owner_fee_exception") or None
    if fees_exposed:
        all_in = money(face + buyer_fees + tax)
        fees_status = "EXPOSED"
    elif exception and fees:
        # Written per-quote owner exception (spec 5.3): the platform
        # does not expose its fees, but the owner supplied the figures
        # (e.g. confirmed on the platform's own hire screen) in the
        # approval pack. The status stays UNEXPOSED — the platform
        # never exposed them — and the all-in is labeled as computed
        # from the owner-supplied itemization under exception.
        all_in = money(face + buyer_fees + tax)
        fees_status = "UNEXPOSED"
    else:
        # No silent incompletes: an unexposed-fee quote with nothing
        # to total has no all-in and cannot be hired under a ceiling.
        all_in = None
        fees_status = "UNEXPOSED"
    quote = {
        "platform": str(raw.get("platform") or ""),
        "pro": {
            "platform_id": str(pro["platform_id"]),
            "display_name": pro.get("display_name"),
            "rating": pro.get("rating"),
            "hires": pro.get("hires"),
            # License claims are surfaced verbatim with provenance;
            # the core never asserts a claim is valid (spec 8.3).
            "license_claims": pro.get("license_claims") or [],
            "badges": pro.get("badges") or [],
        },
        "model": model,
        "job_price_face": face,
        "hourly": hourly,
        "fees": fees,
        "fee_bearer": fee_bearer,
        "buyer_fees_total": buyer_fees,
        "tax": tax,
        "tip": raw.get("tip") or {"mode": "n/a"},
        "all_in_total": all_in,
        "fees_status": fees_status,
        "owner_fee_exception": exception,
        "currency": str(raw.get("currency") or "USD"),
        "valid_until": raw.get("valid_until"),
        "raw_quote_ref": raw.get("raw_quote_ref"),
    }
    quote["quote_id"] = "quote_" + sha(canon(quote))[:12]
    return quote


def ceiling_test(quote: dict, ceiling) -> dict:
    ceiling = money(ceiling)
    if quote["fees_status"] == "UNEXPOSED" and \
            not quote.get("owner_fee_exception"):
        return {"ceiling_all_in": ceiling, "hireable_under_ceiling": False,
                "reason": "fees UNEXPOSED: a quote whose fees the "
                          "platform does not expose cannot be hired "
                          "under a ceiling (spec 5.3); only a written "
                          "per-quote owner exception in the approval "
                          "pack can lift this"}
    if quote["all_in_total"] is None:
        return {"ceiling_all_in": ceiling, "hireable_under_ceiling": False,
                "reason": "no all-in total could be computed (fees "
                          "UNEXPOSED and no owner-supplied itemization "
                          "under a written exception)"}
    ok = quote["all_in_total"] <= ceiling
    reason = ("all-in total is within the ceiling"
              if ok else "all-in total exceeds the ceiling")
    if quote["fees_status"] == "UNEXPOSED":
        reason += " (owner fee exception on record)"
    return {"ceiling_all_in": ceiling, "hireable_under_ceiling": ok,
            "reason": reason}


def t_quote_normalize(state, args):
    quote = normalize_quote(args)
    if quote["quote_id"] not in state["quotes"]:
        state["quotes"][quote["quote_id"]] = quote
        emit_receipt(state, "quote_normalized", {
            "quote_id": quote["quote_id"], "platform": quote["platform"],
            "pro_id": quote["pro"]["platform_id"], "model": quote["model"],
            "all_in_total": quote["all_in_total"],
            "fees_status": quote["fees_status"]})
    out = {"quote": quote}
    if args.get("ceiling_all_in") is not None:
        out["ceiling_test"] = ceiling_test(quote, args["ceiling_all_in"])
    return out


def t_quote_read(state, args):
    quote = state["quotes"].get(str(args.get("quote_id") or ""))
    if not quote:
        raise ToolError(f"unknown quote: {args.get('quote_id')}")
    out = {"quote": quote}
    if args.get("ceiling_all_in") is not None:
        out["ceiling_test"] = ceiling_test(quote, args["ceiling_all_in"])
    return out


# ------------------------------------------------------------------ hire gate
def expected_quote_token(quote_id: str) -> str:
    return f"approve-quote-{quote_id}"


def expected_person_token(quote_id: str) -> str:
    return f"confirm-person-{quote_id}"


def t_hire_check(state, args):
    """The hire gate (spec 6 + 7.4): pure mandate evaluation.

    Executes nothing. Returns a decision and whether the quote is
    hireable RIGHT NOW. In v1 the selection of a person requires an
    owner-confirm token even when every mandate check passes.
    """
    brief = state["briefs"].get(str(args.get("brief_id") or ""))
    quote = state["quotes"].get(str(args.get("quote_id") or ""))
    as_of = parse_time(str(args.get("as_of") or now_iso()))
    reasons, notes = [], []

    if not brief:
        reasons.append(f"unknown brief: {args.get('brief_id')}")
    if not quote:
        reasons.append(f"unknown quote: {args.get('quote_id')}")

    mandate = args.get("mandate")
    approval_ok = False
    person_ok = False
    if brief and quote:
        approval = brief.get("approval")
        if not approval or approval.get("brief_hash") != brief["hash"]:
            reasons.append("brief is not approved at its current hash "
                           "(approval binds hashes; spec 5.1)")
        if not mandate:
            reasons.append("NO_MANDATE: no mandate, no hire (spec 6.1)")
        else:
            expires = parse_time(mandate.get("expires_at"))
            if expires is None or expires <= as_of:
                reasons.append("mandate expired or has no expiry "
                               "(spec 6.1)")
            if quote["platform"] not in \
                    (mandate.get("platforms") or []):
                reasons.append(
                    f"platform {quote['platform']!r} not in mandate "
                    "platform allowlist")
            if brief["category"] not in \
                    (mandate.get("categories") or []):
                reasons.append(
                    f"category {brief['category']!r} not in mandate "
                    "category allowlist")
            cet = ceiling_test(quote, mandate.get("cap", 0)) \
                if mandate.get("cap") is not None else None
            brief_cet = ceiling_test(quote, brief["ceiling_all_in"])
            if cet and not cet["hireable_under_ceiling"]:
                reasons.append("mandate cap: " + cet["reason"])
            if not brief_cet["hireable_under_ceiling"]:
                reasons.append("brief ceiling: " + brief_cet["reason"])
            threshold = mandate.get("approval_threshold")
            if threshold is not None and quote["all_in_total"] is not None \
                    and quote["all_in_total"] > float(threshold):
                if args.get("quote_approval_token") == \
                        expected_quote_token(quote["quote_id"]):
                    approval_ok = True
                    notes.append("above-threshold quote approved by "
                                 "owner token for THIS quote (spec 6.2)")
                else:
                    reasons.append(
                        "all-in total exceeds the mandate approval "
                        "threshold; an owner approval token for this "
                        "exact quote is required (spec 6.2)")
            valid_until = parse_time(quote.get("valid_until"))
            if valid_until is not None and valid_until <= as_of:
                reasons.append("quote has expired (valid_until passed)")
        # Person-selection rule (spec 7.4): v1 default is
        # owner-confirmed, mandate or not.
        if args.get("person_confirm_token") == \
                expected_person_token(quote["quote_id"]):
            person_ok = True
        else:
            notes.append("PERSON_CONFIRM_REQUIRED: in v1 the selection "
                         "of a person is owner-confirmed even under a "
                         "mandate (spec 7.4)")

    if reasons:
        decision, hireable = "DENY", False
    elif not person_ok:
        decision, hireable = "MANDATE_ALLOW_PERSON_PENDING", False
    else:
        decision, hireable = "ALLOW", True
    detail = {"brief_id": args.get("brief_id"),
              "quote_id": args.get("quote_id"), "decision": decision,
              "hireable": hireable, "reasons": reasons, "notes": notes,
              "mandate_id": (mandate or {}).get("mandate_id"),
              "executes": "nothing — evaluation only (G0)"}
    emit_receipt(state, "hire_check", detail)
    return detail


# ------------------------------------------------------- completion + reviews
def t_completion_verify(state, args):
    brief = state["briefs"].get(str(args.get("brief_id") or ""))
    if not brief:
        raise ToolError(f"unknown brief: {args.get('brief_id')}")
    scope_items = (brief.get("scope") or {}).get("items") or []
    results = args.get("scope_results") or []
    by_item = {r.get("item"): r for r in results}
    checked = []
    for item in scope_items:
        result = by_item.get(item)
        if result is None:
            checked.append({"item": item, "status": "unattested",
                            "attestation": None})
        else:
            status = str(result.get("status") or "")
            if status not in ("done", "partial", "not_done"):
                raise ToolError("scope result status must be done | "
                                "partial | not_done")
            checked.append({"item": item, "status": status,
                            "attestation": result.get("attestation")})
    platform_state = str(args.get("platform_state") or "unknown")
    incomplete = [c for c in checked if c["status"] != "done"]
    # Platform state and owner verification are separate fields and
    # are never merged (spec 7.2). A platform that claims completion
    # the owner does not attest opens an exception, not an edit.
    mismatch = bool(incomplete) and \
        platform_state.strip().lower() in ("completed", "complete",
                                           "done", "paid", "released")
    if mismatch:
        verification_status = "exception"
    elif incomplete:
        verification_status = "partial"
    else:
        verification_status = "owner_verified"
    record = {
        "brief_id": brief["brief_id"],
        "brief_hash": brief["hash"],
        "quote_id": args.get("quote_id"),
        "platform": args.get("platform"),
        "pro_display_name": args.get("pro_display_name"),
        "platform_state": platform_state,
        "platform_state_basis": "read back verbatim; never smoothed "
                                "(spec 7.2)",
        "scope_check": checked,
        "verification_status": verification_status,
        "platform_owner_mismatch": mismatch,
        "timeliness": args.get("timeliness"),
        "communication": args.get("communication"),
        "quality_notes": args.get("quality_notes"),
        "verified_at": str(args.get("verified_at") or now_iso()),
    }
    record["verification_id"] = \
        "verify_" + sha(canon(record))[:12]
    state["verifications"][record["verification_id"]] = record
    receipt = emit_receipt(state, "completion_verified", {
        "verification_id": record["verification_id"],
        "brief_id": brief["brief_id"],
        "verification_status": verification_status,
        "platform_owner_mismatch": mismatch})
    return {"verification": record, "receipt_seq": receipt["seq"]}


def t_review_draft(state, args):
    record = state["verifications"].get(
        str(args.get("verification_id") or ""))
    if not record:
        raise ToolError(
            f"unknown verification: {args.get('verification_id')}")
    notes_blob = " ".join(str(record.get(k) or "") for k in
                          ("quality_notes", "timeliness",
                           "communication")).lower()
    for pattern in LEVERAGE_PATTERNS:
        if pattern in notes_blob:
            raise ToolError(
                "prohibited leverage language in the verification "
                f"record ({pattern!r}); review drafts are factual and "
                "record-bound only (spec 7.3)")
    brief = state["briefs"].get(record["brief_id"]) or {}
    done = sum(1 for c in record["scope_check"] if c["status"] == "done")
    total = len(record["scope_check"])
    lines = [
        f"Hired for {brief.get('category', 'a task')} "
        f"({brief.get('service', 'service')}) via "
        f"{record.get('platform') or 'the platform'}.",
        f"Completion verified against the brief: {done} of {total} "
        "scope items done.",
    ]
    if record["verification_status"] != "owner_verified":
        lines.append(
            f"Verification status: {record['verification_status']}.")
    if record.get("timeliness"):
        lines.append(f"Timeliness: {record['timeliness']}.")
    if record.get("communication"):
        lines.append(f"Communication: {record['communication']}.")
    # Sentiment enters ONLY from the record's own quality notes.
    if record.get("quality_notes"):
        lines.append(f"Quality: {record['quality_notes']}.")
    text = " ".join(lines)
    draft = {
        "verification_id": record["verification_id"],
        "brief_id": record["brief_id"],
        "pro_display_name": record.get("pro_display_name"),
        "text": text,
        "basis": "verification record only (spec 7.3)",
        "status": "DRAFT — owner approves the exact text before any "
                  "submission; drafts never submit themselves",
    }
    emit_receipt(state, "review_drafted", {
        "verification_id": record["verification_id"],
        "draft_hash": sha(text)})
    return {"review_draft": draft}


def t_receipt_list(state, args):
    limit = args.get("limit")
    receipts = state["receipts"]
    if limit is not None:
        receipts = receipts[-int(limit):]
    return {"receipts": receipts, "count": len(state["receipts"]),
            "chain_valid": verify_receipt_chain(state["receipts"])}


TOOLS = {
    "brief_create": (
        t_brief_create,
        "Create a canonical Task Brief: category, service, scope "
        "{statement, items[]}, ZIP-tier location, timing window, "
        "ALL-IN ceiling, tip policy, photos (EXIF-strip status "
        "recorded per photo), license_required (unknown|no|yes:<type>), "
        "safety/access block, intended/prohibited platforms, and a "
        "details bag adapters draw native form answers from. Issues "
        "the version-1 hash an approval binds to.",
        {"brief_id": {"type": "string"}, "category": {"type": "string"},
         "service": {"type": "string"}, "scope": {"type": "object"},
         "location": {"type": "object"}, "timing": {"type": "object"},
         "ceiling_all_in": {"type": "number"},
         "tip_policy": {"type": "object"},
         "photos": {"type": "array", "items": {"type": "object"}},
         "license_required": {"type": "string"},
         "safety_access": {"type": "object"},
         "intended_platforms": {"type": "array",
                                "items": {"type": "string"}},
         "prohibited_platforms": {"type": "array",
                                  "items": {"type": "string"}},
         "details": {"type": "object"}},
        ["category", "service", "scope", "location", "timing",
         "ceiling_all_in", "license_required"]),
    "brief_update": (
        t_brief_update,
        "Create a new brief version from content-field changes. Any "
        "post-approval edit invalidates the approval and returns the "
        "brief to draft (approval binds hashes, spec 5.1).",
        {"brief_id": {"type": "string"}, "changes": {"type": "object"}},
        ["brief_id", "changes"]),
    "brief_approve": (
        t_brief_approve,
        "Record the owner's approval of the EXACT current brief hash, "
        "plus the per-platform variant hashes approved with it. A "
        "hash mismatch is refused.",
        {"brief_id": {"type": "string"}, "brief_hash": {"type": "string"},
         "approver": {"type": "string"},
         "approved_at": {"type": "string"},
         "variant_hashes": {"type": "object"}},
        ["brief_id", "brief_hash"]),
    "brief_read": (
        t_brief_read,
        "Read a brief with its version, hash, and approval validity.",
        {"brief_id": {"type": "string"}}, ["brief_id"]),
    "quote_normalize": (
        t_quote_normalize,
        "Normalize a quote from any platform model (lead_model, "
        "stated_budget, fixed_price, hourly) into one record: face "
        "price, itemized fees with bearers, tax, and ALL-IN total "
        "kept separate forever. Fees the platform does not expose "
        "mark the quote UNEXPOSED with no all-in. Optional "
        "ceiling_all_in runs the ceiling test.",
        {"platform": {"type": "string"}, "pro": {"type": "object"},
         "model": {"type": "string"}, "job_price": {"type": "number"},
         "hourly_rate": {"type": "number"},
         "hour_cap": {"type": "number"},
         "fees": {"type": "array", "items": {"type": "object"}},
         "fees_exposed": {"type": "boolean"},
         "tax": {"type": "number"}, "tip": {"type": "object"},
         "currency": {"type": "string"},
         "valid_until": {"type": "string"},
         "raw_quote_ref": {"type": "string"},
         "owner_fee_exception": {"type": "object"},
         "ceiling_all_in": {"type": "number"}},
        ["platform", "pro", "model"]),
    "quote_read": (
        t_quote_read,
        "Read a normalized quote; optional ceiling_all_in re-runs the "
        "ceiling test.",
        {"quote_id": {"type": "string"},
         "ceiling_all_in": {"type": "number"}}, ["quote_id"]),
    "hire_check": (
        t_hire_check,
        "Evaluate a hire against a live Procure/Agent Wallet mandate: "
        "approved brief hash, mandate presence + expiry, cap vs "
        "all-in, brief ceiling, category + platform allowlists, "
        "approval threshold (above = owner token for THIS quote), "
        "quote expiry, fee exposure. v1 person-selection always "
        "needs an owner-confirm token. Returns ALLOW / "
        "MANDATE_ALLOW_PERSON_PENDING / DENY with named reasons. "
        "Executes nothing; receipted either way.",
        {"brief_id": {"type": "string"}, "quote_id": {"type": "string"},
         "mandate": {"type": "object"},
         "quote_approval_token": {"type": "string"},
         "person_confirm_token": {"type": "string"},
         "as_of": {"type": "string"}}, ["brief_id", "quote_id"]),
    "completion_verify": (
        t_completion_verify,
        "Verify completion against the brief's scope statement: each "
        "scope item done/partial/not_done with owner attestation. "
        "Platform state is stored verbatim and separately; a "
        "platform-completed claim the owner does not attest opens "
        "an exception record (spec 7.2).",
        {"brief_id": {"type": "string"}, "quote_id": {"type": "string"},
         "platform": {"type": "string"},
         "pro_display_name": {"type": "string"},
         "platform_state": {"type": "string"},
         "scope_results": {"type": "array",
                           "items": {"type": "object"}},
         "timeliness": {"type": "string"},
         "communication": {"type": "string"},
         "quality_notes": {"type": "string"},
         "verified_at": {"type": "string"}}, ["brief_id"]),
    "review_draft": (
        t_review_draft,
        "Draft review text from a verification record ONLY: what was "
        "hired, what was verified, and timeliness/communication/"
        "quality strictly as recorded. No sentiment the record does "
        "not carry; leverage language is refused at draft time. "
        "The draft never submits itself.",
        {"verification_id": {"type": "string"}}, ["verification_id"]),
    "receipt_list": (
        t_receipt_list,
        "List the append-only, hash-chained gig-core receipts and "
        "verify the chain.",
        {"limit": {"type": "integer"}}, []),
}

# Capability denylist, stated in code: G0 evaluates and records only.
# Live submission, live hiring, payment movement, and review
# submission are adapter/G1 surfaces behind owner gates — and
# session/scraping routes are prohibited at any tier (spec 8.6).
FORBIDDEN_TOOL_NAMES = {
    "request_submit", "hire_execute", "payment_execute",
    "review_submit", "pro_contact_export", "session_login",
    "cookie_reuse", "scrape_quotes", "scrape_profiles",
}


def tool_list():
    return [{"name": name, "description": description,
             "inputSchema": {"type": "object", "properties": props,
                             "required": required}}
            for name, (_, description, props, required) in TOOLS.items()]


def handle(req: dict):
    method, rid = req.get("method", ""), req.get("id")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": rid, "result": {
            "protocolVersion": req.get("params", {}).get(
                "protocolVersion", "2025-03-26"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "eclipse-gig-core", "version": "0.1.0"}}}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": rid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": rid,
                "result": {"tools": tool_list()}}
    if method == "tools/call":
        name = req["params"]["name"]
        args = req["params"].get("arguments", {})
        if name in FORBIDDEN_TOOL_NAMES or name not in TOOLS:
            return {"jsonrpc": "2.0", "id": rid, "error": {
                "code": -32602,
                "message": f"unknown or G0-forbidden tool {name}"}}
        state = load_state()
        try:
            out = TOOLS[name][0](state, args)
            save_state(state)
            return {"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text",
                             "text": json.dumps(out, indent=1)}]}}
        except ToolError as exc:
            return {"jsonrpc": "2.0", "id": rid, "result": {
                "content": [{"type": "text",
                             "text": json.dumps({"error": str(exc)})}],
                "isError": True}}
    if rid is not None:
        return {"jsonrpc": "2.0", "id": rid, "error": {
            "code": -32601, "message": f"method not found: {method}"}}
    return None


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            response = handle(json.loads(line))
        except Exception as exc:  # never crash the transport
            response = {"jsonrpc": "2.0", "id": None, "error": {
                "code": -32603, "message": str(exc)}}
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
