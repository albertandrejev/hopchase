# Action pack — contacts and request templates

Verify contact channels before sending; they change. Every request must quote exact addresses, token accounts, tx hashes, amounts, UTC times and the police case number once available.

## Issuers (freeze)

| Issuer | Asset | Channel | Notes |
|---|---|---|---|
| Circle | USDC (Solana, EVM) | Law-enforcement request form on circle.com (Legal → Law Enforcement); victim duplicate via support | Circle freezes the **token account** on Solana — quote it, not just the owner. Acts mainly on LE requests; a victim's own request opens a ticket. |
| Tether | USDT (TRON, EVM) | legal@tether.to; Law Enforcement Request form on tether.to | Tether blacklists addresses; quote balance and that funds are at rest. Faster with a case number. |

Template (EN):
> Subject: Urgent freeze request — stolen funds at rest — [asset] [amount] — [chain]
> On [date UTC] [amount asset] were transferred without authorisation from victim wallet [addr] (tx [hash]) to [addr] (token account [ta]). As of [date time UTC, slot/block] the funds remain unspent at that address (balance [x]). The receiving address is a collection wallet of a multi-victim scheme (see attached HopChase report, sections 4–5). We request an immediate administrative freeze pending law-enforcement process. Police report: [number / "being filed on <date>"]. Contact: [name, role, e-mail, phone].

## Police

- File where the victim resides; attach the report (sections 1, 3, 4, 7 are what investigators use) and the exhibits (bridge API output, explorer links).
- Explain in the statement that issuers and bridges release data only against a case number — ask for the number in writing the same day.
- Estonia: cyber.politsei.ee / local prefecture; EU cross-border: mention Europol EC3 and that assets sit with US issuers (Circle) and BVI/El Salvador issuer (Tether).

## Bridges / aggregators (data request + blocklist)

| Service | Channel | Ask for |
|---|---|---|
| SWFT / Bridgers | support@swft.pro, compliance via swft.pro | For each `orderId`: IP, user-agent, `equipmentNo`, session timestamps, wallet app channel; add operator addresses to their risk list (their `refundReason 8`) |
| Rango Exchange | support via rango.exchange / Discord ticket | Request by memo/requestId and tx hash: destination details, IP, client |
| Wormhole | Wormhole Foundation security contact | Usually nothing off-chain; use Wormholescan record as exhibit |
| deBridge | support@debridge.finance | Order details by orderId |
| Mayan | support@mayan.finance (from their compliance page); no dedicated channel for blocked funds | Orders by `orderId`/`orderHash`; the `screening` line (`sanctioned`, `SWAP_BLOCKED`) shows they already block the address — ask what happens to refunded blocked funds and for the screening provider's reference |
| Relay | no public contact found; their quote API refuses blocked addresses, which is the only visible blocklist | Request by request `id` / deposit hash; expect to go through law enforcement |
| SEAL 911 (Security Alliance) | Telegram `@seal_911_bot`; e-mail on securityalliance.org/sos | Accepts third-party tips; fastest route to issuer and bridge security teams when the victim is unknown or unreachable |

Circle acts on law-enforcement requests, so the victim's police report comes first; a bridge or SEAL 911 contact buys time, it does not replace the case number.

Template (EN):
> We are investigating theft of [amount asset] from [victim addr] on [date]. Your order(s) [orderIds / tx hashes] moved proceeds from [chain] to [chain] address [addr]. Please (1) preserve all logs for these orders, (2) provide available metadata to the investigating authority [police unit, case no.], and (3) add the following addresses to your risk/blocklist to prevent further laundering: [list].

## Wallet apps

- Trust Wallet (channel `trustwallet-prod` in Bridgers orders): abuse report via support.trustwallet.com; they hold swap telemetry and device data.
- Phantom / Solflare: security@ addresses; useful when the victim's seed was phished through a fake site (report the domain too).

## Exchanges (when the endpoint is a CEX deposit)

- Compliance/LE portals: Binance (LE portal), OKX, Bybit, HTX, KuCoin, Kraken, Coinbase — all require a case number; send the deposit address, tx hash, amount, time and ask for an account hold.
- Send the same day: deposits are swept and withdrawn within hours.

## Outreach when the victim is unknown

No identified operator or victim contact (case 04): the trace still has to reach someone who can act.

1. Find the victim's own treasury from pre-incident outflows: `sol_trace.py history <victim> --cap 300`, `-- top value recipients` footer — the recurring recipient of the months before the theft (weekly sweeps, a CEX deposit) is the owner's wallet until shown otherwise.
2. Channels, in order: (a) the bridge holding the funds (Mayan/Relay rows above — they can hold a refund), (b) SEAL 911, (c) a public reply in the alert thread (quote hashes, no speculation about identity), (d) last, an on-chain memo to the treasury with a short pointer to the report. A memo is public and reaches the thief too: never put the freeze plan, contacts or amounts the thief does not already know into it.
3. Record every attempt (channel, UTC time, what was sent) in the report's action pack so a second volunteer does not repeat it.

## Monitoring

- Scheduled task every 60 min: `python3 ${CLAUDE_PLUGIN_ROOT}/scripts/recheck.py case.json`; alert on any new outgoing from the frozen-candidate address or a new Bridgers order.
- On first movement: run `bridges.py bridgers <addr>` immediately — the payout address appears within 1–3 minutes — and forward it to the issuer of the destination asset.

## Victim hygiene (always include)

- Treat the seed as burned: move remaining assets on **every** chain derived from it to a new seed on a clean device.
- Revoke token approvals/delegations (revoke.cash for EVM; Solana: check delegates via `getTokenAccountsByOwner`).
- Do not open links from memo transactions or airdropped tokens; do not respond to "recovery agents" who contact first.
- Keep a timeline of what was signed and where in the 72 h before the theft — it narrows the phishing vector.
