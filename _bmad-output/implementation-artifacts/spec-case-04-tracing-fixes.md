---
title: 'Case 04 tracing fixes: versioned txs, decimals, internal txs, Mayan/Relay, freeze checks'
type: 'bugfix'
created: '2026-11-07'
status: 'done'
route: 'dispatch'
review_loop_iteration: 0
baseline_commit: 'f1e91a445a5d507ab5b30a2a3dadabadea696d72'
context: ['{project-root}/AGENTS.md']
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Tracing case 04 showed the plugin silently drops version-1 Solana transactions (986 of 1,000 missing), prints unknown mints as raw integers, misses EVM internal transfers (a 251 ETH bridge payout was invisible), has no lookups for Mayan and Relay, never checks freeze/blacklist status, and gives no signer or compute-budget summary per wallet.

**Approach:** Fix the decoders and RPC error reporting in `sol_trace.py`/`common.py`, add internal transactions to `evm_trace.py`, add `mayan` and `relay` commands to `bridges.py`, add `freeze` subcommands and escrow support to the tracers and `recheck.py`, and document the method changes in the skills and references. All 13 items ship together on branch `fix/new-improvements-1`; nothing is committed by the agent.

## Boundaries & Constraints

**Always:** Standard library only; HTTP through `common.http`/`common.sol_rpc`; results to stdout, progress/errors to stderr via `common.log`; API keys read only from env in `common.py` and never printed. Keep `tests/` offline. Keep existing CLI commands and their output shape backward-compatible (only add lines/fields). Run `python3 tests/test_smoke.py` before finishing.

**Never:** Touch `tools/solana_util.py` (lives in the case repository, not here). No new dependencies, no install step. Do not commit, push or branch.

**Decisions (recorded from investigation):**
- Mayan API field is `stateAddr` (the `/v3/swap/trx/<sig>` response also has `sourceStateAddr`); print both when present. `limit` max is below 200 (API returns `LIMIT_TOO_LARGE`); use 50.
- Relay `GET /requests/v2` is deprecated (sunset 2026-11-24); `/requests/v3` requires an `x-api-key` header. Add optional `RELAY_API_KEY`: use v3 with the key when set, else v2 with a stderr warning that it retires on 2026-11-24.
- `ANKR_API_KEY` (networks are enabled per key in the Ankr dashboard; the user enabled Ethereum, BNB Smart Chain and Solana): Solana RPC `https://rpc.ankr.com/solana/<key>` when `HELIUS_API_KEY` is unset (priority Helius > Ankr > public RPC); EVM JSON-RPC `https://rpc.ankr.com/<chain>/<key>` for `eth_call` on every chain, falling back to `<blockscout>/api/eth-rpc` (keyless, verified on eth) when Ankr returns an error for a chain that is not enabled. README lists which networks to enable for the key and that others fall back automatically.
- Skills reference scripts as `${CLAUDE_PLUGIN_ROOT}/scripts/` in both skills, with one line telling the agent to fall back to the `scripts/` folder next to `skills/` when the variable is unset.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| v1 transaction | `sol_trace.py history <bot wallet>` | every signature decoded; `accountKeys` from lookup tables included in signer/SOL-delta logic | RPC error text logged to stderr once per failure, not swallowed |
| unknown mint | token delta on USD1 (6 dec) / wrapped ETH (8 dec) | `USD1 -7,173.929438`, `wETH -0.04106158`, using `uiTokenAmount.decimals` | raw integer only when balance arrays missing |
| program-controlled wallet | all txs signed by another key | `history` footer: `signers: <key> 100% (N txs) — program-controlled deposit account?` plus `(cu_limit, cu_price)` pairs per signer | – |
| EVM internal payout | `evm_trace.py 0x…` on address paid by Mayan SwiftDest | `-- internal txs (value > 0)` lines with caller contract name; included in `exits used` | missing endpoint → section shows 0 |
| Mayan order | `bridges.py mayan <SIG>` / `<ADDRESS>` | trader, destAddress, amounts, status, fulfill/refund tx, stateAddr | 404 → `not a Mayan swap`; trader listing notes cancelled/refunded orders are omitted |
| Relay order | `bridges.py relay <TX>` / `<ADDRESS>` | status, failReason, recipient, inTxs/outTxs | no key → v2 with warning; missing → `no Relay request` |
| Solana freeze | `sol_trace.py freeze <TOKEN_ACCOUNT|WALLET>` | per token account: `state`, mint symbol, mint `freezeAuthority` | RPC None → `?` and stderr line |
| EVM blacklist | `evm_trace.py freeze <0x…> [--chain eth]` | `USDC isBlacklisted: no/YES`, `USDT isBlackListed: no/YES` | RPC error → `?` |
| recheck escrow | `case.json` with `solana.escrows` | balance + latest sigs for each escrow; freeze line per token account | `getTokenAccountsByOwner`/`getSignaturesForAddress` None → `?`, no crash |

</frozen-after-approval>

## Code Map

- `scripts/common.py` -- `sol_rpc` (returns None on error: add `log` of `r["error"]`), `SOL_MINTS` (add USD1 `USD1ttGY…EmuB` 6, PYUSD `2b1kV6Dk…4GXo` 6, USDS `USDSwr9A…TwcA` 6, cbBTC `cbbtcf3a…iMij` 8, wETH `7vfCXTUX…voxs` 8), `SOL_PROGRAMS` (add Relay program `99vQwtBwYtrqqD9YSXbdum3KBdxPAVxYTaQ3cfnJSrN2` → `BRIDGE:Relay`), new `SOL_LABELS` for depository `7uTT8Xi5RWXzy7h9XL244GRgEycDYDhLjr3ZyNdXi8pZ`; new `ANKR`, `RELAY` env reads; new `evm_rpc(chain, method, params)`; constants `USDC_ETH 0xa0b86991…eb48`, `USDT_ETH 0xdac17f95…1ec7`, selectors `0xfe575a87`, `0xe47d6060`.
- `scripts/sol_trace.py` -- `get_tx` (version 0 → 1), `summarize` (decimals from `uiTokenAmount.decimals`; add `signers` already present), `fmt_amount` (accept decimals), `print_summary` (print signers), `cmd_history` (footer: signer stats + CU pairs), new `cmd_freeze`, docstring usage.
- `scripts/evm_trace.py` -- `blockscout()` add `/internal-transactions` section (fields `value`, `from.hash`, `from.name`, `to`, `transaction_hash`, `timestamp`, `success`); new `freeze` subcommand using `common.evm_rpc`; main arg parsing (`freeze` as first arg).
- `scripts/bridges.py` -- new `mayan(q)` (`/v3/swap/trx/<sig>` when arg is a Solana signature or 0x hash, else `/v3/swaps?trader=&limit=50&offset=` paged), `relay(q)` (`?hash=` vs `?user=`), register in dispatch dict and docstring.
- `scripts/recheck.py` -- guard None from `sol_rpc`; read `solana.escrows`; print token-account `state` via `getAccountInfo` jsonParsed; docstring `case.json` example.
- `skills/trace-funds/SKILL.md` -- ground rules (env vars list + RELAY/ANKR), step 2 freeze command, step 3 mayan/relay commands, step 1 signer note, price-basis rule, path fallback line.
- `skills/address-profile/SKILL.md` -- same env var list, path fallback line, freeze command.
- `skills/trace-funds/references/bridges.md` -- Mayan and Relay rows with API URLs and traps; "trader is the deposit account" note.
- `skills/trace-funds/references/confidence.md` -- price basis convention; program-controlled deposit account heuristic.
- `README.md`, `.env.example` -- `ANKR_API_KEY`, `RELAY_API_KEY`, new script commands.
- `tests/test_smoke.py` -- offline tests for `fmt_amount` with decimals, signer footer helper, Mayan/Relay command registration, `sol_rpc` error logging; keep lists current.

## Tasks & Acceptance

**Execution:**
- [x] `scripts/common.py` -- env reads, mint/program labels, `sol_rpc` error logging, `evm_rpc` -- shared by all tracers
- [x] `scripts/sol_trace.py` -- version 1, decimals, signer/CU footer, `freeze` -- items 1, 2, 8, 10, 11
- [x] `scripts/evm_trace.py` -- internal txs, `freeze` -- items 3, 8
- [x] `scripts/bridges.py` -- `mayan`, `relay` -- items 4, 5
- [x] `scripts/recheck.py` -- None guards, escrows, freeze line -- items 6, 8, 9
- [x] `skills/*/SKILL.md`, `references/*.md`, `README.md`, `.env.example` -- method and docs -- items 7, 12, 13
- [x] `tests/test_smoke.py` -- offline tests for the matrix rows that need no network

**Acceptance Criteria:**
- Given the live RPC, when `sol_trace.py history` runs on a wallet with version-1 transactions, then no `?? no tx` lines appear for valid signatures and errors print their RPC message.
- Given `python3 tests/test_smoke.py`, when run, then every test prints `ok`.
- Given any script, when an API key is missing, then it falls back to the keyless endpoint and keeps working.

## Implementation Notes

- Implemented by a step-03 subagent; verified by the orchestrator against the diff. 23 offline smoke tests pass; live checks passed for: Mayan order by signature, Relay v2 keyless path, EVM blacklist via Ankr and via keyless Blockscout eth-rpc (USDT 0x…01 = YES), Solana `freeze`, `recheck.py` escrow, `history --cap 15` on the Relay depository (0 `?? no tx`, footer flags program control).
- Orchestrator corrections after the subagent: price-basis rule now says operator's own swap rates first, else a named oracle (as the case-04 notes ask); Relay depository label is `BRIDGE:Relay depository`; deposit-account flag printed once in the footer header instead of on every signer line; pre-existing bug fixed in passing — `history --cap N` fetched up to 1000 signatures and decoded all of them, now slices to N; four offline tests added (Mayan parsing, EVM internal txs, Solana freeze, recheck escrows with RPC None).
- Field names confirmed live: Mayan `stateAddr` + `sourceStateAddr`; Blockscout internal tx `from.name`; Ankr key enabled for eth, bsc, solana (others 403 → fallback).

- `sol_trace.py`: `maxSupportedTransactionVersion` 0 → 1; `summarize` carries `uiTokenAmount.decimals` per delta and `fmt_amount(mint, raw, decimals=None)` prefers them over the registry (raw integer only when both are missing). `print_summary` prints a `signers:` line (`cmd_tx` keeps its own `signers … | slot:` line, so it passes `signers=False`). `history` text mode ends with a `-- signers` footer from `signer_footer(addr, rows)`; JSON mode output shape is unchanged (list of rows). New `freeze` command accepts a token account or a wallet.
- `common.py`: `sol_rpc` logs every RPC error / no-response to stderr; `evm_rpc` tries Ankr first and falls back to `<blockscout>/api/eth-rpc`; Solana RPC priority Helius > Ankr > public. `SOL_LABELS` is a new wallet-label registry (depository `7uTT…`), shown as `[DEPOSITORY:…]` next to owners in `print_summary`.
- `evm_trace.py`: `-- internal txs (value > 0)` section; named internal callers join `exits used` (as `PAYOUT:<name>` when they are not registry-labelled BRIDGE/DEX, so a Mayan `SwiftDest` payout is visible without a registry entry). `freeze` registers blacklist getters for `eth` only; other chains log "skipped".
- `bridges.py`: `mayan` (per-tx `/v3/swap/trx/<ref>`, trader paging with limit 50) and `relay` (v3 + `x-api-key` when `RELAY_API_KEY` set, else v2 with stderr warning). `all` now also runs mayan + relay. Live check showed the Mayan API echoing `fulfillTxHash` into `refundTxHash` on `ORDER_UNLOCKED` orders, so `REFUND tx` prints only when the hash differs.
- `recheck.py`: `solana.escrows` (SOL balance, token accounts with freeze line, latest sigs); every `token_accounts` entry gets a `freeze … state=` line; all `sol_rpc` None results print `?`.
- Live verification 2026-11-07 (HELIUS + ANKR keys set, no RELAY key): `bridges.py mayan 3TdF…J2F` → `ORDER_UNLOCKED` with `stateAddr`/`sourceStateAddr`; `evm_trace.py freeze 0x…01` → USDC no / USDT YES (also with `ANKR_API_KEY=` unset via Blockscout eth-rpc); `sol_trace.py tx 3TdF…J2F` decoded; `sol_trace.py history 8iN2…2NQu` footer flags the Mayan state account as program-controlled; `recheck.py` with escrows `8iN2…`, `7uTT…` printed balances + freeze lines; `bridges.py relay <hash>` printed the v2 warning and `no Relay request`.

- Second pass (notes 14–22, same day, done directly after the spec was closed, 45 tests): `history` header prints on-curve / OFF-CURVE (pure ed25519 point check in `sol_trace.on_curve`), memos are collected from parsed Memo instructions (log fallback) and printed as `memo(data, not fact)`, `[CO-SIGNED]` flag, new `activity_footer` (programs per tx, top value recipients, outgoing lot histogram, sweep-loop detection within 60 s, co-signed count, memo count); `bridges.py mayan` takes several txs and de-duplicates by `orderId` ("N orders from M transactions"), the trader listing is de-duplicated too; `relay()` warns that the `user=` listing is incomplete; `evm_trace.py` prints UTF-8 text found in plain-transfer calldata as data; skills and references updated (victim counterparties pass, PDA row, sweep-loop / lot-size / co-signer heuristics, "post-theft activity is not the bot running"). Live check on the Relay depository: header OFF-CURVE, sweep loop 8/25 within ≤25 s by the solver key, 8 co-signed, 4 memos; Mayan source+fulfil txs of one order → "1 orders from 3 transactions".

- Third pass (audit notes 30–42, 2026-11-07, done directly, 55 tests): `bridges.py mayan` prints a `screening` line (`sanctioned`, `security.code/msg`, `BLOCKED` prefix) and a `deadline … completedAt … (refunded 20.6 h after deadline)` line on every order plus `minAmountOut`/`refundAmount`; `-- refunds:` footer splits before-/after-deadline refunds; listings print `metadata.count` and the per-hash mode prints the `?trader=` listing count next to the per-hash count; docstring/trap text now says blocked orders never appear in listings. `sol_trace.py`: `summarize` carries `ins_types`; new footers `-- instruction types` (count, first → last, 90 % mark), `-- last tx` (seconds), `-- memo deadline` (expiry from the memo term, reply before expiry), co-signed footer lists programs; new `program <PROGRAM_ID>` command (programData, upgrade authority, dated loader events, upgrade rate). `recheck.py` groups output into `## <section> (read <time>)` blocks and ends with `## as-of stamps`. Registry fix found while verifying: the two Mayan Solana program ids (`FUDE…` has no account, `MAYANM7S…` decodes to 31 bytes) replaced by `BLZR…` (Swift v1) and `mayan34…` (Swift v2, the program a live SWIFT_V2 fulfil tx calls). Docs: alert-thread reading + parallel-analysis read time (trace-funds), two as-of stamps / quotes-not-facts / prose-must-not-outrun-the-check (case-report), program upgrade base rate (address-profile, confidence), Mayan/Relay/SEAL 911 contacts and the outreach-when-victim-unknown section (action-pack). Live checks: Mayan order by hash shows screening + deadline lines and `1 orders listed vs 1 found`; `program 99vQ…` (Relay) lists deploy + 3 upgrades + 2 extendProgram + setAuthority with rate; `recheck.py` prints section stamps; `history --cap 25` on the Relay depository prints instruction-type ranges, last tx with seconds and co-signed programs. Not verified live: a memo that states a term (covered offline), a `sanctioned` order (field shape taken from the audit notes; `security` is `null` on clean orders live).

## Spec Change Log

## Review Triage Log

Review pass 1 (blind-hunter BH, edge-case-hunter EC, verification-gap VG). Route: all surviving entries are `patch`; no intent_gap / bad_spec.

| # | Finding | Verdict | Evidence / route |
|---|---|---|---|
| BH1 | `ANKR_API_KEY` leaks into stderr: `http` logs `url.split('?')[0][:80]`, Ankr key is in the URL path | high | `common.py:122` confirmed; `rpc.ankr.com/solana/` is 28 chars so 52 key chars print on any 4xx. patch: redact key values before logging + test |
| BH2/EC5 | `mayan`/`relay` print "not a Mayan swap" / "no Relay request" when `http` returns None (outage, 401, 429 exhaustion) | medium | confirmed: `http` returns None for both 404 and failures. patch: `http` returns `{}` on 404 (callers already `or {}`), callers print "lookup failed" on None |
| BH3 | Relay v2 sunset 2026-11-24 → false negatives afterwards | medium | same root cause as BH2 (None → negative); docs to say keyless mode is temporary. grouped with BH2 |
| BH4 | Docs tell users to enable BSC on Ankr but nothing uses it (`BLACKLIST_GETTERS` eth only) | medium | confirmed. patch: docs say Solana + Ethereum required, BSC unused today; `.env.example` fallback wording fixed |
| BH5 | Mayan EVM contracts missing from `EVM_CONTRACTS`; bridges.md gives no address | medium | verified live on Blockscout: `0xC38e4e6A15593f908255214653d3D947CA1c2338` = MayanSwift, `0x0654874eb7F59C6f5b39931FC45dC45337c967c3` = MayanForwarder. patch: add both + document |
| BH6 | freezeAuthority printed as bare pubkey | medium | SKILL promises "Circle for USDC, Tether for USDT"; authorities seen live: USDC `7dGbd2…Crar`, USDT `Q6Xprf…9Gi`. patch: `SOL_FREEZE_AUTHORITIES` map, label in output |
| BH7 | Price-basis rule not in `case-report/SKILL.md` | medium | confirmed: report skill defines sections, no price basis line. patch: one line in incident summary |
| BH8/EC-recheck | recheck escrow loop indexes parsed info directly | low | rejected: jsonParsed token accounts always carry `info`; guard for undemonstrated state |
| BH9/EC8 | `--chain` as last arg → IndexError | low | rejected: pre-existing CLI pattern, adds branches |
| BH10 | test gaps | — | superseded by VG entries |
| BH11 | doc inconsistencies (`.env.example` fallback wording, `SOL_LABELS` not in balances/recheck) | low | `.env.example` wording patched with BH4; labels in balances rejected (cosmetic) |
| EC1 | no public-RPC fallback when Ankr Solana fails | low | rejected: failure is now loud (`sol_rpc` logs every error); fallback adds branches |
| EC2 | RPC dict without result/error treated as success | low | rejected: not observed from any provider |
| EC3 | Mayan paging infinite loop if offset ignored | false | verified live: `offset=0` and `offset=2` return different orders |
| EC4/EC6/EC10 | non-dict / list bodies, `items: null` | low | rejected: not observed; guards for undemonstrated states |
| EC7 | bare 64-hex hash without 0x | low | rejected: Mayan/Relay hashes are 0x-prefixed |
| EC9 | non-EVM address to `freeze` | low | rejected: RPC error prints `?` and stderr |
| EC11 | internal txs first page only | low | rejected: same "N shown" design as native txs and token transfers (pre-existing) |
| EC12 | `history` on a token account flags it as program-controlled | medium | confirmed: a token account never signs. patch: footer text names the token-account case |
| EC13/EC14/EC16 | freeze on a mint, Token-2022 partial failure, getBalance without value | low | rejected: rare, guard-adding |
| EC15/VG-other | closed token account prints `state=? ?…` with no message | medium | confirmed: `token_account_info` returns `{}` for `value: null`. patch: print "closed / not a token account" |
| VG1 | SOL_RPC priority untested | medium (pre-verified) | patch: subprocess test over env combinations |
| VG2 | `evm_rpc` Ankr success path untested | medium | patch: extend test |
| VG3 | `freeze` YES/no and calldata wiring untested | high | patch: side_effect test |
| VG4 | `all` not verified to call mayan/relay | medium | patch |
| VG5 | Mayan paging second page untested | medium | patch |
| VG6 | Relay result printing untested | medium | patch |
| VG7 | `print_summary` labels/signers untested | medium | patch |
| VG8 | `cmd_history` cap + footer untested | medium | patch |
| VG9 | `cmd_freeze` wallet path / `none` / empty untested | medium | patch |
| VG10 | recheck escrow happy path untested | medium | patch |
| VG11 | internal-tx `BRIDGE` label and `to: null` untested | medium | patch |

## Verification

**Commands:**
- `python3 tests/test_smoke.py` -- expected: all `ok`, no traceback
- `cd scripts && python3 sol_trace.py tx <v1 signature>` -- expected: decoded, not "not found"
- `cd scripts && python3 bridges.py mayan 3TdFvsLZe13f2HwZ54KuaHn5n8WgmoJJN2L4tbMyvcnKhaYEnYVHNsXXzrc8utmx4kU73zjtNgHh9Uuxiotk6J2F` -- expected: ORDER_UNLOCKED order printed
- `cd scripts && python3 evm_trace.py freeze 0x0000000000000000000000000000000000000001` -- expected: USDC no / USDT YES (address 0x…01 is blacklisted on USDT)
