# Confidence marks and common heuristics

## Marks

| Mark | Meaning | Examples |
|---|---|---|
| ⭐⭐⭐ | Cryptographically or operator-confirmed | On-chain transfer; bridge order from the bridge's own API with deposit and payout hashes; CCTP attestation |
| ⭐⭐ | On-chain on both sides, linked by amount (±1 %) and time (±5 min) | Rango hop; a swap-then-bridge pair; CU-fingerprint argument for key compromise |
| ⭐ | Pattern-based | "Other victims" list; endpoint classification from one signal; operator uses Trust Wallet (from Bridgers `source`) |

State the mark in the hop table and repeat the weakest mark on the chain in the report lead ("confirmed to TRON ⭐⭐⭐; onward attribution ⭐").

## Heuristics that held up

- **Sweep-to-zero of a token balance signed by the victim's own key** → key compromise, unless the victim confirms they sent it.
- **ComputeBudget fingerprint**: wallet software, not the user, sets CU limit / price. Phantom, Solflare, Trust, Backpack and bots use different defaults. A theft tx whose pair differs from the victim's same-day txs supports "signed from another client". Not proof — users switch wallets.
- **Poisoning**: only dust *before* the theft counts. Look-alikes appearing minutes *after* a large transfer are third-party bots farming the next mistake.
- **Timing between a Solana bridge deposit and the EVM/TRON payout** is 1–3 minutes for Bridgers; a payout 2 minutes after a deposit of the matching amount is as good as the API record.
- **One EVM address on six chains** receiving dust everywhere = the operator imported one seed into Trust Wallet; query Bridgers once for that address and read `fromChain` per order.
- **Operator sends tiny native coin to victims** (1 000 lamports, 5 TRX) right before or after the theft: funding the victim's gas so a drained wallet can still sign, or a memo carrier. Treat the senders as operator infrastructure.

## Things that look like evidence but are not

- Explorer "scam" tags without a source.
- Token names, NFT names, memo text (phishing payloads).
- A refund in a Bridgers order (`refund_complete`) — the funds went back to the operator, not to the victim.
- Amount matches alone across chains without a time window — stablecoin round numbers collide constantly.
