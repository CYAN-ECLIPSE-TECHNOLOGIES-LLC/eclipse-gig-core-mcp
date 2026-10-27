# eclipse-gig-core

mcp-name: io.github.CYAN-ECLIPSE-TECHNOLOGIES-LLC/gig-core

**What this is:** the MCP server for **Eclipse Gig Core** — the shared
core of Cyan Eclipse Technologies' Eclipse gig adapter family. One
canonical, owner-approved Task Brief becomes a native request, offer
round, booking, or prep pack on each task marketplace, according to
what that platform actually sanctions.

**What this is not:** phase G0 is fixtures and evaluation only. **No
live platform call exists in this code, no hire is executed, no review
is submitted, and no payment moves.** Hiring happens only inside an
Eclipse Procure / Agent Wallet mandate, evaluated — never executed —
by this core.

## Run it

```console
$ pip install eclipse-gig-core
$ eclipse-gig-core           # MCP over stdio, Python stdlib only
```

MCP client config:

```json
{ "mcpServers": { "eclipse-gig-core": { "command": "uvx", "args": ["eclipse-gig-core"] } } }
```

## Tools (10)

`brief_create` · `brief_update` · `brief_approve` · `brief_read` ·
`quote_normalize` · `quote_read` · `hire_check` · `completion_verify` ·
`review_draft` · `receipt_list`

## Honest scope

- The Task Brief is versioned and SHA-256 hash-bound; any
  post-approval edit invalidates the approval. Quotes normalize every
  platform model (lead, stated-budget, fixed-price, hourly) to face
  price and itemized fees — forever separate — plus one all-in total;
  a quote whose fees are unexposed cannot be hireable under a ceiling.
- The hire gate returns ALLOW / DENY with named reasons, receipted
  either way; in v1, selecting a person requires an owner-confirm
  token even when a mandate allows the money.
- State persists in `data/state.json` beside the server (override with
  `ECLIPSE_GIG_CORE_STATE`).
- Certified (local) by the Eclipse Test Bench at v0.1.0; the listing
  status in the Eclipse Bazaar catalog is in-development.

Powered by Cyan Eclipse Technologies LLC (cetech.ai) — a Veteran-Owned
Small Business. MIT licensed.
