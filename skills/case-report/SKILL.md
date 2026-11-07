---
name: case-report
description: Writes a HopChase case report for a crypto tracing investigation (incident summary, compromise analysis, fund-flow diagram, hop table with confidence marks, operator profile, action pack for issuers/bridges/police, reproducibility, sources) as an editable doc with optional PDF export. Use when the user asks to "write the case report", "write up the investigation", "case report", "HopChase report", "investigation report", or after trace-funds finishes.
---

# HopChase case report

The case report is written for lawyers, victim-support volunteers, exchange/issuer compliance and police — readers who will act on it, not re-derive it. Every claim carries a confidence mark and a way to reproduce it.

## Where it goes

Create it as a Claude Doc (Docs artifact type) titled `HopChase — Incident trace <first 4>…<last 4 of seed hash>` (translate the title and all headings into the user's language). Land the skeleton first (title, byline, lead, one pending block per section), then fill one section per call so the reader watches it build. Export to PDF (A4) with the docs `export` tool when asked; check one page renders before sending.

## Lead paragraph

One paragraph, the answer first: amount + asset, date, **whether the stolen funds have moved**, the endpoint, and the freeze window. Balances, freeze state and bridge-screening answers are read at different times: carry **every "as of" stamp that differs** ("balances 6 Nov 23:56 UTC; freeze state 7 Nov 09:53 UTC" — `recheck.py` prints them in its `## as-of stamps` line), never one stamp for all ("90,540.81 USDC … have not moved as of this report: they sit at … and can be frozen by Circle. The operator's route is Solana → Bridgers → USDT (TRON), where 197,351 USDT has accumulated.").

## Sections (fixed order; drop a section only when empty)

1. **Incident summary** — table: network/asset, amount, time UTC + slot/block, seed tx link, victim wallet, recipient owner **and token account**, status of stolen funds *as of* check time, incident type, scheme endpoint. State the price basis once here (the operator's own swap rates at the time of the transactions, else the named oracle and date) and never mix bases in a total. Close with the freeze-window sentence and last operator activity.
2. **Seed transaction and compromise analysis** — what the tx is, what is excluded (poisoning, approve) with the evidence, client-fingerprint table (tx / who / CU limit / CU price), confidence of the compromise call, **urgent advice to the victim** (rotate seed, move remainder, ignore memo phishing).
3. **Fund-flow map** — one diagram: victims on the left → collector (accent) → bridges → EVM twin → endpoint (critical colour); edge labels = amounts; one sentence of reading under it. Draw with the docs diagram widget (`guide topic.diagram`).
4. **Hop table** — `# | date UTC | chain | from | to | amount (in → out) | channel / orderId | status | confidence`. Hop 0 = the theft. Include pre-theft hops of the same operator when they show the route. List bridge payout wallets under the table.
5. **Operator profile** — table of operator addresses (chain, role, marks) + table of probable other victims (date, address, amount, "our case" marked) + total scheme damage estimate.
6. **Action pack** — checklist ordered by urgency, each item with the exact address/token-account/orderId to quote. Use `references/action-pack.md` for contacts and wording. Always include: issuer freeze(s), police report (and why it is needed), bridge/aggregator data requests + blocklist ask, wallet-app abuse report if a channel is known, monitoring, victim hygiene. When the victim is unknown, add the "Outreach when the victim is unknown" steps from `references/action-pack.md` (find the treasury from pre-incident outflows, then bridge → SEAL 911 → public reply in the alert thread → on-chain memo last).
7. **Reproducibility** — table `fact → how to verify` with exact endpoints and request bodies (Solana RPC methods, Bridgers API body, Blockscout/TronGrid URLs); state when each check was run; list limitations (amount/time-matched links, hypothesis lists). **Prose must not outrun the check**: where a sentence links a number to a reproduction step, that step must compute that number (not a related tuple); if it does not, the sentence is marked "read by hand".
8. **Sources** — explorer links for every hash and address, bridge docs, APIs queried with dates.

## Style

- Numbers with units and thousands separators; UTC everywhere; addresses in backticks, shortened `A9a6…KmdB` after the first full mention in a table.
- Confidence marks ⭐/⭐⭐/⭐⭐⭐ in the hop table and on the compromise call; "hypothesis" spelled out for ⭐ items.
- Characterisations taken from the alert or the press ("one of the oldest bots", "$7.2M lifetime PnL") are quotes, not facts: attribute them in the sentence that uses them and put the chain facts that bear on them next to them (first funding date, program-data date). Nothing from the alert thread is presented as the report's own finding; say what the thread contained.
- When comparing with another analysis, print its stated read time next to each count that differs ("Bitquery, read 3 Nov 09:17 UTC: 13 orders; this trace: 15 — two re-submissions after that read").
- Any post-incident event read as a reaction (an upgrade, a withdrawal) comes with its base rate before the incident (`sol_trace.py program`, `history` footers).
- No speculation about identity of the operator; no victim personal data beyond addresses; no API keys or internal paths.
- Sentences short; the reader is skimming between phone calls.

## After publishing

Say in one line what the doc is; offer PDF export and an hourly monitor (`scripts/recheck.py` with a `case.json`) as the next step. If the user asks for letters (police statement, issuer freeze request, bridge data request), draft them from `references/action-pack.md` templates as separate docs.
