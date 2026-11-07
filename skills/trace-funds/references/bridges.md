# Bridges & aggregators registry

Identifiers to recognise an exit, and where to get off-chain confirmation of the far side.

## Bridgers (SWFT Blockchain) — most common in Trust Wallet-operated schemes

| Chain | Identifier |
|---|---|
| Solana program | `FDF8AxHB8UK7RS6xay6aBvwS3h7kez9gozqz14JyfKsg` (logs: `Instruction:: Swap`, `fromAmount`, `sender`) |
| EVM contract | `SwftSwap` — ETH `0xc1d13492285eb664951E201BF7C80c7c6318a1b5`, methods `swapEth` / `swap`; other chains: trust the Blockscout `name` |
| TRON payout wallet | `TJ4KeiGTvTX4wRUgLARiwr8rGLaurmVkdZ` |
| Order API (no key) | `POST https://api.bridgers.xyz/api/exchangeRecord/getTransData` body `{"pageNo":1,"pageSize":50,"fromAddress":A,"equipmentNo":A,"sourceType":"H5","sourceFlag":"widget"}`; one order: `POST …/getTransDataById {"orderId":…}` |
| Useful fields | `fromChain/toChain`, `toAddress`, `hash` (deposit), `toHash` (payout), `status` (`receive_complete`, `refund_complete`), `source` (`trustwallet-prod_0.007` = Trust Wallet channel), `equipmentNo`, `refundReason` (8 = "interaction with risky address" → they keep a blocklist; ask them to add the operator) |
| Contact | support@swft.pro; docs https://docs-bridgers-en.bridgers.xyz/ |

## Rango Exchange

| Chain | Identifier |
|---|---|
| Solana program | `RangohQxaWip6i1twAAnRVLmob9j88fid7sq2DMAATW` (emits a Memo = requestId, e.g. `WgdhdJRNQXaTf0tMwwSIOg1`) |
| EVM contract | `RangoDiamond` — ETH `0x69460570c93f9DE5E2edbC3052bf10125f0Ca22d`, method `genericBridge` |
| TRON payout wallet | `TX5XiRXdyz7sdFwF5mnhT1QoGCpbkncpke` |
| Order API | none public; match by amount ±1 % / time ±5 min (⭐⭐); request details from Rango support with the requestId |

## Wormhole / Portal

- Solana: core `wormDTUJ6AWPNvk59vGQbDvGJmqbDTdgWgAqcLBCgUb`, token bridge `wormqW2zTPwNcDeK7uWpJyq8dqTqJxJzqk8yMquc4A`
- ETH Portal `0x3ee18B2214AFF97000D974cf647E7C347E8fa585`
- API: `https://api.wormholescan.io/api/v1/operations?address=<addr|txhash>` → `targetChain`, `toAddress`, `amount`

## deBridge DLN

- Solana: src `src5qyZHqTqecJV4aY6Cb6zDZLMDzrDKKezs22MPHr4`, dst `DEbrdGj3HsRsAzx6uH4MKyREKxVAfBydijLUF3ygsFfh`
- ETH `0xeF4fB24aD0916217251F553c0596F8Edc630EB66`
- API: `https://dln.debridge.finance/v1.0/dln/tx/<txhash>/order-ids` → `…/dln/order/<id>`

## Circle CCTP (native USDC burn/mint)

- Solana `CCTPiPYPc6AsJuwueEnWgSgucamXDZwBd53dQ11YiKX3`; ETH TokenMessenger `0xBd3fa81B58Ba92a82136038B25aDec7066af3155`
- API: `https://iris-api.circle.com/v1/messages/<sourceDomain>/<txhash>` (domains: 0 ETH, 1 AVAX, 2 OP, 3 ARB, 5 SOL, 6 BASE, 7 POLY)

## Mayan (Swift / MCTP)

| Chain | Identifier |
|---|---|
| Solana programs | Swift v1 `BLZRi6frs4X4DNLw56V4EXai1b6QVESN1BhHBTYM9VcY` (`BRIDGE:Mayan Swift`), Swift v2 `mayan34VedncxdK2XobtvWFDXQASUTBXhUVzt2kKgny` (`BRIDGE:Mayan Swift v2`; the program `SWIFT_V2` fulfil transactions call — verified live 2026-11-07). The ids listed before (`FUDE…`, `MAYANM7S…`) do not exist on chain and were removed |
| EVM | `MayanSwift` — ETH `0xC38e4e6A15593f908255214653d3D947CA1c2338` (`BRIDGE:Mayan Swift`; this is the payout contract the case notes call "SwiftDest"), `MayanForwarder` — ETH `0x0654874eb7F59C6f5b39931FC45dC45337c967c3` (`BRIDGE:Mayan Forwarder`). Payouts come from the Swift contract as **internal transactions** (ETH value sent by the contract) — invisible in the native tx list; `evm_trace.py` prints them under `-- internal txs` |
| Order API (no key) | one order: `GET https://explorer-api.mayan.finance/v3/swap/trx/<sig or 0x hash>` (404 → not a Mayan swap); by trader: `GET …/v3/swaps?trader=<addr>&limit=50&offset=<n>` paged (`limit` ≥ 200 → `LIMIT_TOO_LARGE`) |
| Useful fields | `trader`, `destAddress`, `fromAmount`/`toAmount`, `sourceChain`/`destChain`, `status` (`ORDER_UNLOCKED` = paid out, `ORDER_REFUNDED`), `sourceTxHash`, `fulfillTxHash`, `refundTxHash`, `stateAddr` (and `sourceStateAddr` in the per-tx response): the on-chain order state account. Per-tx response only: `sanctioned` (bool), `security.code` / `security.msg` (`SWAP_BLOCKED`, "Detected blocked address"), `deadline`, `completedAt`, `minAmountOut`, `refundAmount` — `bridges.py mayan` prints a `screening` line and a `deadline … completedAt … (refunded 20.6 h after deadline)` line on every order |
| Traps | **Blocked (sanctioned) orders never appear in `?trader=` or `?destAddress=` listings** — in case 04 both listings said `count: 10` while the two refunded and three cancelled orders were missing because they were `sanctioned`, not because they were refunded. Look blocked orders up by transaction hash; `bridges.py mayan <SIG> …` prints the listing count next to the per-hash count so the gap is visible. **Refund lag needs two baselines**: Mayan also refunds orders it cannot fill at `minAmountOut`, and 5 of 9 sampled refunds landed *before* their deadline, so `-- refunds:` splits "before deadline" from "after deadline"; never pool them into one lag figure. Per-tx lookups **double-count**: `/swap/trx/<sig>` resolves a refund or fulfil tx to its order, so N Mayan-program transactions can be fewer orders; `bridges.py mayan <SIG> <SIG> …` de-duplicates by `orderId` and prints "15 orders from 17 transactions". The `trader` is the Solana account that signed the deposit, which for wallet-app and relayer flows is a **program-controlled deposit account**, not the person; check its `history` footer (signers) before naming it as the operator |
| Explorer | https://explorer.mayan.finance |
| Script | `bridges.py mayan <SIG|TXHASH|ADDRESS>` |

## Relay (relay.link)

| Chain | Identifier |
|---|---|
| Solana program | `99vQwtBwYtrqqD9YSXbdum3KBdxPAVxYTaQ3cfnJSrN2` (`BRIDGE:Relay`); depository wallet `7uTT8Xi5RWXzy7h9XL244GRgEycDYDhLjr3ZyNdXi8pZ` (`BRIDGE:Relay depository` in `SOL_LABELS`) |
| EVM | solver-filled; the recipient receives a plain transfer from a Relay solver EOA — match by `outTxs` hash from the API |
| Order API | `GET https://api.relay.link/requests/v3?hash=<tx>` or `?user=<addr>` with header `x-api-key: $RELAY_API_KEY`; keyless `GET …/requests/v2?…` is deprecated, sunset 2026-11-24 |
| Useful fields | `status` (`success`, `refund`, `failure`), `data.failReason`, `user`, `recipient`, `data.inTxs[]` / `data.outTxs[]` (`hash`, `chainId`, `timestamp`) |
| Traps | `hash=` matches deposit **or** fill hashes; `user=` lists the depositor, not the recipient. The `user=` (and `recipient=`) listing is **incomplete**: in case 04 an order found by `hash=` was absent from `user=`, so use listings to find orders and prove negatives on chain (the address signed exactly N transactions). No request → "no Relay request" (the tx may still be a Relay solver transfer; check the solver EOA's other fills) |
| Script | `bridges.py relay <TXHASH|SIG|ADDRESS>` |

## Allbridge

- Allbridge Solana `BrdgN2RPzEMWF96ZbnnJaUtQDQx7VRXYaHHbYCBvceWB`; explorer https://explorer.allbridge.io

## EVM aggregators that are not bridges (swap only, same chain)

1inch v5 `0x1111111254EEB25477B68fb85Ed929f73A960582`, CoW GPv2 `0x9008D19f58AAbD9eD0D60971565AA8510560ab41`, KyberSwap `0x6131B5fae19EA4f9D964eAc0408E4408b66337b5`, LI.FI Diamond `0x1231DEB6f5749EF6cE6943a275A1D3E7486F4EaE` (LI.FI *does* bridge — check `bridge` field in its event).

## Adding a new bridge

1. Identify the program/contract from the hop-1 history (`BRIDGE:` label missing → look at logs / Blockscout `name`).
2. Add it to `scripts/common.py` (`SOL_PROGRAMS`, `EVM_CONTRACTS`, `TRON_LABELS`; known deposit wallets go in `SOL_LABELS`).
3. Find its explorer API and add a function to `scripts/bridges.py`.
4. Document the row here.
