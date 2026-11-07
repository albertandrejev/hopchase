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
- **Off-curve address = PDA.** `sol_trace.py` prints `OFF-CURVE` in the `history`/`balances` header when the 32 bytes are not a valid ed25519 point: no private key can exist, the account is driven by a program. Stronger than "it never signed".
- **Sweep loop** (`-- sweep loop` footer): an inbound deposit forwarded out within seconds, repeatedly, is a script. Settles "person or script" for the drain phase; the script's signer is operator infrastructure.
- **Lot-size histogram** (`-- outgoing lots`): dozens of identical small swaps followed by a few large ones is a mistyped chunk size — a human at a keyboard, useful for timeline and for "same operator" arguments.
- **Co-signed transactions** (`[CO-SIGNED]`): two keys signing one transaction means the same party controls both; a treasury that co-signs the victim's clean-up is the victim's own wallet, not a suspect.
- **Post-theft activity is not "the bot kept running"** unless the `-- programs` footer shows the bot's program still being called; closing thousands of token/nonce accounts with rent to a treasury is clean-up by the owner.
- **Time range per instruction type** (`-- instruction types` footer): `closeAccount ×2208 12:07 → 12:38 (90 % by 12:09)` and `-- last tx 16:46:43` keep a burst and the wallet's last activity apart — a write-up must not say the burst "ran until" the last transaction. The co-signed footer lists the programs those transactions call, so a clean-up that also touches a DEX is visible.
- **Base rate before "reaction"**: before reading any post-incident event (an upgrade, a withdrawal, a memo) as a reaction to the theft, print how often it happened before. `sol_trace.py program <PROGRAM_ID>` prints every deploy/upgrade/setAuthority with its date and the upgrade rate; a program upgraded four times in the ten days before the theft makes a post-theft upgrade mean nothing on its own.
- **Memo deadlines**: when a memo states a term ("within 48 hours"), the `-- memo deadline` footer prints the expiry computed from the transaction time and whether the other party sent a memo or value back before it. The report carries the expiry and the (missing) reply, not only the offer.
- **Refund lag has two populations**: Mayan refunds expired orders *and* orders unfillable at `minAmountOut`; the latter land before the deadline. Quote "refunded N h after the deadline" only for the first group (`bridges.py mayan` `-- refunds:` footer).
- **Program-controlled deposit account**: `sol_trace.py history` ends with a `-- signers` footer. If the wallet itself signed 0 of its transactions and one other key signed 100 % of them (with one or two fixed `(cu_limit, cu_price)` pairs), the address is a depository/escrow driven by a program or relayer (bridge deposit account, Mayan state account, exchange sub-account), not a person's wallet. Name the controlling key and program in the hop table; attribution to a person through such an account is ⭐ at most. Known depositories are labelled in `common.SOL_LABELS`.

## Price basis

- Stablecoins (USDC, USDT, USD1, PYUSD, USDS) count at face value.
- Every other asset (SOL, ETH, wETH, cbBTC, …) is valued at **the operator's own swap rates at the time** when the trace contains them (e.g. seven 50,000 USDC sales → $/SOL; USDC→ETH orders → $/ETH) — those are the prices the funds actually moved at. Otherwise use a named oracle's price **on the day of the transaction** (e.g. "CoinGecko daily close"). Name the basis once and keep it for the whole report.
- Never mix bases in one total and never value a past theft at today's price. If the victim needs a current figure (for a freeze request), give it as a second, clearly labelled number.

## Things that look like evidence but are not

- Explorer "scam" tags without a source.
- Characterisations from the alert or the press ("one of the oldest bots", "$7.2M lifetime PnL"): quotes, attributed in the sentence that uses them, with the chain facts that bear on them (first funding date, program-data date) next to them.
- Token names, NFT names, memo text (phishing payloads).
- A refund in a Bridgers order (`refund_complete`) — the funds went back to the operator, not to the victim.
- Amount matches alone across chains without a time window — stablecoin round numbers collide constantly.
