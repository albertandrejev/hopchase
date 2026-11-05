# HopChase

A Claude plugin for crypto fund-tracing investigations: from a theft/scam transaction to the endpoint wallet across Solana, EVM chains and TRON, through bridges and swap aggregators, ending in a structured **case report** that lawyers, issuers and police can act on.

Built from a real case (Oct 2026): 90.5k USDC swept from a Solana wallet → collector wallet → Bridgers/SWFT and Rango → Ethereum → USDT on TRON, 197k USDT accumulated across six chains' worth of victims.

## What's inside

| Skill | Trigger | Does |
|---|---|---|
| `trace-funds` | "trace this tx", "where did the funds go", "follow the money" | 7-step pipeline: decode seed tx → classify incident → hop 1 → bridges → target chains → operator profile → live re-check |
| `address-profile` | "check this wallet", "what is this address" | 5-minute role profile of one address (victim / collector / accumulator / exchange / poisoning bot) |
| `case-report` | "write the case report", "case report" | 8-section report as an editable doc + PDF, with confidence marks and an action pack |

| Script | Purpose |
|---|---|
| `scripts/sol_trace.py` | `tx` decode (incl. ComputeBudget client fingerprint), `history`, `balances`, `poison` check |
| `scripts/evm_trace.py` | Blockscout (no key) / Etherscan v2 (key) — txs, token transfers, spoofed-token detection, exits used |
| `scripts/tron_trace.py` | TronGrid — balances, in/out TRC-20, gas-hand-out pattern, endpoint hint |
| `scripts/bridges.py` | Bridgers/SWFT order API (no key), Wormholescan, deBridge DLN |
| `scripts/recheck.py` | Live re-verification of a `case.json`; also the hourly monitor |

References: `skills/trace-funds/references/{bridges,endpoints,confidence}.md`, `skills/case-report/references/action-pack.md`.

## API keys (all optional)

Set as environment variables; never put them in reports or commits. Copy `.env.example` to `.env` and `source` it, or export in the session.

| Variable | Effect |
|---|---|
| `HELIUS_API_KEY` | Solana RPC without 429s (public RPC works but a 300-tx history takes ~10 min) |
| `ETHERSCAN_API_KEY` | Etherscan v2 for chains without public Blockscout (BSC, Avalanche) |
| `TRONGRID_API_KEY` | Higher TronGrid limits |

## Quick start

Python 3.10+, no third-party packages. Inside a Claude session the skills write raw outputs to `$SCRATCH/trace/` (the session scratchpad); by hand, pick any folder:

```bash
export SCRATCH=/tmp/hopchase && mkdir -p "$SCRATCH/trace"
cd scripts
python3 sol_trace.py tx <SIGNATURE>
python3 sol_trace.py history <RECIPIENT> > "$SCRATCH/trace/hop1.txt"
python3 bridges.py bridgers <RECIPIENT>
python3 evm_trace.py <0x…> --all-chains
python3 tron_trace.py <T…>
python3 recheck.py case.json
```

## Install

**Claude Code (CLI / desktop Code tab)** — load the checkout directly:

```bash
claude --plugin-dir /path/to/hopchase
```

Or add it to a marketplace you control and run `/plugin install hopchase@<marketplace>`.

**Claude Desktop / Cowork** — package and upload:

```bash
zip -r hopchase.plugin . -x ".git/*" -x "*.pyc" -x ".claude/*"
```

then add the `.plugin` file in the app's plugin settings. Skills are auto-discovered from `skills/`; scripts are reached through `${CLAUDE_PLUGIN_ROOT}/scripts/`.

Offline check: `python3 tests/test_smoke.py`.

## Roadmap

- Address-label enrichment (Arkham / Chainalysis / OXT) behind optional keys
- Bitcoin branch (mempool.space API)
- Letter generators: police statement (ET/RU/EN), issuer freeze, bridge data request
- `case.json` → monitor as a one-command scheduled task

## License

MIT
