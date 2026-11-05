#!/usr/bin/env python3
"""TRON address tracer via TronGrid (TRONGRID_API_KEY optional).

Usage:
  tron_trace.py <ADDRESS> [--limit 50]

Prints: TRX/USDT balance, first incoming, outgoing TRC-20 (all tokens), incoming USDT (latest),
outgoing native TRX (gas-distribution pattern), and an endpoint classification hint.
"""
import sys, datetime
from common import http, tron_headers, USDT_TRON, TRON_LABELS

API = "https://api.trongrid.io/v1/accounts/"


def when(ms):
    return datetime.datetime.fromtimestamp(ms / 1000, datetime.UTC).strftime("%Y-%m-%d %H:%M")


def main(addr, limit):
    H = tron_headers()
    acc = (http(API + addr, headers=H) or {}).get("data") or [{}]
    acc = acc[0]
    usdt = 0
    for x in acc.get("trc20", []):
        if USDT_TRON in x:
            usdt = int(x[USDT_TRON]) / 1e6
    print(f"== TRON {addr}  TRX {acc.get('balance', 0) / 1e6:,.2f}  USDT {usdt:,.2f}  {TRON_LABELS.get(addr, '')}")

    first = (http(API + addr + f"/transactions/trc20?only_to=true&limit=1&order_by=block_timestamp,asc&contract_address={USDT_TRON}", headers=H) or {}).get("data") or []
    if first:
        print(f"first USDT in: {when(first[0]['block_timestamp'])}  {int(first[0]['value']) / 1e6:,.2f} from {first[0]['from']}")

    out = (http(API + addr + f"/transactions/trc20?only_from=true&limit={limit}", headers=H) or {}).get("data") or []
    print(f"-- outgoing TRC-20 (any token): {len(out)}")
    for t in out:
        print(f"{when(t['block_timestamp'])} {int(t['value']) / 10**int(t['token_info'].get('decimals', 6)):>14,.2f} {t['token_info'].get('symbol')} -> {t['to']} {TRON_LABELS.get(t['to'], '')}")

    inc = (http(API + addr + f"/transactions/trc20?only_to=true&limit={limit}&contract_address={USDT_TRON}", headers=H) or {}).get("data") or []
    print(f"-- incoming USDT (latest {len(inc)})")
    bridge_in = 0
    for t in inc:
        tag = TRON_LABELS.get(t["from"], "")
        if tag:
            bridge_in += 1
        print(f"{when(t['block_timestamp'])} {int(t['value']) / 1e6:>14,.2f} from {t['from']} {tag}")

    nat = (http(API + addr + f"/transactions?only_from=true&limit={limit}", headers=H) or {}).get("data") or []
    trx_out = []
    for t in nat:
        c = t["raw_data"]["contract"][0]
        if c["type"] == "TransferContract":
            trx_out.append(c["parameter"]["value"].get("amount", 0) / 1e6)
    print(f"-- outgoing native txs: {len(nat)}; TRX transfers: {len(trx_out)}" + (f" (min {min(trx_out):.1f}, max {max(trx_out):.1f} TRX)" if trx_out else ""))

    # classification hint
    if not out and inc:
        kind = "ACCUMULATOR (no TRC-20 outflows"
        if trx_out and max(trx_out) < 100:
            kind += ", small TRX gas hand-outs → operator wallet, not an exchange"
        kind += ")"
    elif out and len(out) < 5 and inc:
        kind = "PASS-THROUGH / possible CEX deposit (few sweeps) — check recipients' labels"
    else:
        kind = "ACTIVE / MIXED — inspect manually"
    print(f"-- endpoint hint: {kind}; {bridge_in}/{len(inc)} latest inflows came from known bridge payout wallets")


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    main(a[0], int(a[a.index("--limit") + 1]) if "--limit" in a else 50)
