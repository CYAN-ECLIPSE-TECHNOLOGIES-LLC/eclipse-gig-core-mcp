# Eclipse Gig Core MCP

**Powered by Cyan Eclipse Technologies** — https://cetech.ai

**The Eclipse gig adapter family — one canonical, owner-approved Task Brief becomes a native request, offer round, booking, or prep pack on each task marketplace, according to what that platform actually sanctions. Hiring happens only inside an Eclipse Procure / Agent Wallet mandate. It never diverts a hire off-platform, never invents a sanctioned surface that does not exist, and never posts a brief the owner has not approved.**

## Why this exists

Task marketplaces do not agree with each other: Thumbtack runs a lead/request model, Airtasker runs post-and-offers, TaskRabbit's partner surface is fixed-price booking, Fiverr is a gig catalog, Upwork is contract/proposal. There is no universal "post" and no universal "price." The gig core is the one place the family agrees: a single hash-bound Task Brief, one quote normalization to an all-in total, one hire gate, one completion standard, one review discipline. Each platform adapter (Compass for Thumbtack is the first) renders the brief natively and never flattens how its hire happens. This family is Eclipse Procure's human-services supply side.

## Status — honest labels

v0.1.0, phase **G0 (shared core, fixtures + evaluation only)**. Local stdio transport, Python stdlib only. **No live platform call exists in the code, no hire is executed, no payment moves, no review is submitted, and no certification is claimed — bench pending.** Live request/hire surfaces belong to the adapters at G1, behind owner partner-access gates.

## The Task Brief

One immutable, versioned object per job: category + service, scope statement (what done looks like), ZIP-tier location (exact address is released only inside a platform's own post-hire flow — a brief carrying exact-address precision is refused), timing window, **one ALL-IN budget ceiling**, photo refs with the EXIF-strip status recorded on each photo record, `license_required` (`unknown` | `no` | `yes:<type>`), a safety + access block, intended/prohibited platforms, and a details bag adapters draw native form answers from.

Approval binds the brief's SHA-256 content hash and the per-platform variant hashes approved with it. **Any post-approval edit creates a new version and invalidates the approval** — approval binds hashes, not vibes.

## Quote normalization — all-in or it is not a quote

Every quote normalizes to one record: pro identity with license claims surfaced verbatim (never asserted valid), face price, itemized fees with bearers, platform-stated tax, and one `ALL_IN_TOTAL`. Fees stay separate fields forever; comparisons and the ceiling test run on the all-in only. Pro-borne fees (the Thumbtack lead fee) are itemized because they explain quote levels, but they are not charged to the buyer and stay out of the buyer's all-in. Hourly quotes are rate × the owner-approved hour cap; overruns return to review.

A quote whose fees the platform does not expose is `UNEXPOSED` and **cannot be hired under a ceiling**. The only lift is a written, per-quote owner exception recorded in the approval pack; with owner-supplied fee figures the all-in is computed from that itemization and labeled as such — the status stays UNEXPOSED, because the platform never exposed them.

## The hire gate

`hire_check` executes nothing; it evaluates a hire against a live Eclipse Procure / Agent Wallet mandate: brief approved at its current hash, mandate present and unexpired, all-in vs mandate cap and vs brief ceiling, category + platform allowlists, approval threshold (above it, an owner token for *this exact quote* — token form `approve-quote-<quote_id>`), quote expiry, fee exposure. Every check, ALLOW or DENY, is receipted.

**Person-selection is owner-confirmed in v1, mandate or not:** a mandate ALLOW without the owner-confirm token (`confirm-person-<quote_id>`) returns `MANDATE_ALLOW_PERSON_PENDING` with `hireable: false`. Selecting a person to enter the owner's home does not ride on a budget rule.

## Completion + reviews

Platform-done is not verified. `completion_verify` checks each scope item (done / partial / not done, with owner attestation) and stores the platform's state **verbatim in its own field**; a platform-completed claim the owner does not attest opens an `exception` record — never a silent edit.

`review_draft` writes from the verification record only: what was hired, what was verified, and timeliness / communication / quality strictly as recorded. A record without quality notes produces a draft with **no quality claims at all**. Leverage language ("refund or…") is refused at draft time. Drafts never submit themselves; the owner approves the exact text.

## Tools (10)

| Tool | What it does |
|---|---|
| `brief_create` | Create a Task Brief; validates completeness + ZIP-tier precision; issues the version-1 hash. |
| `brief_update` | New version from content changes; invalidates any approval. |
| `brief_approve` | Record owner approval of the exact current hash + variant hashes. |
| `brief_read` | Read a brief with approval validity. |
| `quote_normalize` | Normalize any model (lead / stated-budget / fixed-price / hourly) to face + itemized fees + all-in; optional ceiling test. |
| `quote_read` | Read a normalized quote; optional ceiling re-test. |
| `hire_check` | The mandate gate: ALLOW / MANDATE_ALLOW_PERSON_PENDING / DENY, named reasons, receipted. Executes nothing. |
| `completion_verify` | Scope-by-scope verification record; platform state separate; mismatch = exception. |
| `review_draft` | Record-bound review draft; no unrecorded sentiment; leverage language refused. |
| `receipt_list` | List the append-only receipt chain and verify it. |

The denylist is stated in code: no `request_submit`, `hire_execute`, `payment_execute`, `review_submit`, and no session/scraping route (`session_login`, `cookie_reuse`, `scrape_*`) exists at any tier (spec §8.6).

## Run it

```bash
python3 server.py            # MCP over stdio, stdlib only, no dependencies
python3 smoke.py             # end-to-end smoke over real stdio (temp state)
python3 -m unittest discover tests
python3 make_icon.py         # regenerate icon-512.png
```

State persists in `data/state.json` beside the server (override with `ECLIPSE_GIG_CORE_STATE`). `data/` is gitignored.

## Roadmap (per spec)

- **G0** — this core + the Compass (Thumbtack) fixture adapter.
- **G1** — Compass live modes behind owner-obtained Thumbtack partner access.
- **G2** — Airtasker surface verification sprint (Eclipse Tender stays prep-only until a sanctioned route is confirmed).

## License / attribution

A Cyan Eclipse Technologies product. The "Powered by Cyan Eclipse Technologies" attribution travels with it.
