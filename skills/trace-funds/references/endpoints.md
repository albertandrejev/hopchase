# Endpoint classification

Decide what the last address in a branch *is* before recommending action. Use at least two signals.

| Pattern | Signals | Classification | Recovery path |
|---|---|---|---|
| Accumulator / operator wallet | Many inflows over weeks, zero or rare token outflows, tiny native-coin transfers out (TRX 1–60, ETH ≤ 0.0001) to many addresses = gas hand-outs; inflows from several bridge payout wallets | Operator-controlled | Issuer freeze (Tether `legal@tether.to`, Circle law-enforcement form). Realistic while balance stays. Monitor hourly. |
| CEX deposit address | Blockscout / TronGrid label or `name`; one inflow then sweep to a known hot wallet within minutes–hours; near-zero resting balance | Exchange custody | Exchange compliance request **with police case number**; ask for KYC hold. Time-critical. |
| CEX hot wallet | Thousands of txs/day, labelled | Exchange | Same as above; identify the deposit address that fed it. |
| OTC / P2P desk | Round-number outflows to many fresh addresses, inflows from many sources, no label | Cash-out broker | Issuer freeze may still work; report to analytics vendors. |
| Mixer / privacy | Tornado, Railgun, Wasabi-style, Monero swap via instant exchanger | Laundering | Record and stop the branch; note amounts for the loss statement. |
| Cross-chain non-custodial swap | Thorchain, Maya, Chainflip, SimpleSwap/ChangeNOW/FixedFloat deposit | Instant exchanger | Request from the exchanger with tx hash — many respond to victims directly. |
| Dormant | No activity for >30 days after receipt | Parked | Freeze request still valid; set a long-interval monitor. |

## Telling an accumulator from an exchange (TRON USDT, the common case)

- Exchange deposit addresses on TRON are swept within minutes; an address holding six figures for days is **not** an exchange.
- Exchanges do not send 5–60 TRX to random addresses; operators do (funding victims' or mules' gas).
- First-seen date close to the first inflow from a bridge payout wallet = created for this scheme.

## Confidence of the endpoint call

- ⭐⭐⭐ label from two independent sources, or issuer/exchange confirmed
- ⭐⭐ pattern match on ≥2 signals above
- ⭐ single signal; say "likely" in the report
