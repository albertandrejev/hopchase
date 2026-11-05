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

## Allbridge / Mayan

- Allbridge Solana `BrdgN2RPzEMWF96ZbnnJaUtQDQx7VRXYaHHbYCBvceWB`; explorer https://explorer.allbridge.io
- Mayan Solana `FUDEbQKfMTfAaKS3dGdPEacfpLHgXgsxtSgwR9Dn8Pdv`, `MAYANM7SwJrGEVmVjYT7hpyjPoP8XoekYU4XXUHXvA`; explorer https://explorer.mayan.finance

## EVM aggregators that are not bridges (swap only, same chain)

1inch v5 `0x1111111254EEB25477B68fb85Ed929f73A960582`, CoW GPv2 `0x9008D19f58AAbD9eD0D60971565AA8510560ab41`, KyberSwap `0x6131B5fae19EA4f9D964eAc0408E4408b66337b5`, LI.FI Diamond `0x1231DEB6f5749EF6cE6943a275A1D3E7486F4EaE` (LI.FI *does* bridge — check `bridge` field in its event).

## Adding a new bridge

1. Identify the program/contract from the hop-1 history (`BRIDGE:` label missing → look at logs / Blockscout `name`).
2. Add it to `scripts/common.py` (`SOL_PROGRAMS`, `EVM_CONTRACTS`, `TRON_LABELS`).
3. Find its explorer API and add a function to `scripts/bridges.py`.
4. Document the row here.
