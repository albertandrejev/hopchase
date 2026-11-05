#!/usr/bin/env python3
"""EVM address tracer via Blockscout (no key) or Etherscan v2 (ETHERSCAN_API_KEY).

Usage:
  evm_trace.py <ADDRESS> [--chain eth|base|polygon|arbitrum|optimism|gnosis|bsc|avalanche] [--all-chains]

Prints: balance, native txs (with contract names), token transfers, bridge/aggregator interactions.
Flags look-alike (unicode-spoofed) token symbols as poisoning spam.
"""
import sys, re, json
from common import http, BLOCKSCOUT, ETHERSCAN, ETHERSCAN_CHAINIDS, EVM_CONTRACTS, log

SPOOF = re.compile(r"[^\x20-\x7e]")  # non-ASCII in a symbol like 'ᑌSᗞϹ' == spoofed token


def label(addr, name):
    return name or EVM_CONTRACTS.get((addr or "").lower(), "")


def blockscout(addr, chain):
    base = BLOCKSCOUT.get(chain)
    if not base:
        return False
    B = f"{base}/api/v2/addresses/{addr}"
    info = http(B) or {}
    print(f"== {chain} {addr}  balance {int(info.get('coin_balance') or 0) / 1e18:.6f}  name={info.get('name')}  contract={info.get('is_contract')}")
    txs = (http(B + "/transactions") or {}).get("items", [])
    print(f"-- native txs ({len(txs)} shown, newest first)")
    for t in txs:
        to = t.get("to") or {}
        tag = label(to.get("hash"), to.get("name"))
        print(f"{t['timestamp'][:16]} {t['hash'][:14]} {t['from']['hash'][:10]} -> {to.get('hash', '')[:12]} {tag:<28} {int(t['value']) / 1e18:>12.6f} {t.get('method') or ''}")
    tt = (http(B + "/token-transfers") or {}).get("items", [])
    print(f"-- token transfers ({len(tt)} shown)")
    for t in tt:
        tot = t.get("total") or {}
        dec = int(tot.get("decimals") or 18)
        val = int(tot.get("value") or 0) / 10 ** dec
        sym = t["token"].get("symbol") or "?"
        spoof = " [SPOOFED-SYMBOL]" if SPOOF.search(sym) else ""
        tag = label(t["to"]["hash"], t["to"].get("name"))
        print(f"{t['timestamp'][:16]} {t['transaction_hash'][:14]} {t['from']['hash'][:10]} -> {t['to']['hash'][:12]} {tag:<28} {val:>14,.4f} {sym}{spoof}")
    exits = sorted({label(x.get('to', {}).get('hash'), x.get('to', {}).get('name')) for x in txs if label(x.get('to', {}).get('hash'), x.get('to', {}).get('name')).startswith(("BRIDGE", "DEX"))} - {""})
    if exits:
        print("-- exits used:", ", ".join(exits))
    return True


def etherscan(addr, chain):
    cid = ETHERSCAN_CHAINIDS.get(chain)
    if not (ETHERSCAN and cid):
        log(f"{chain}: no Blockscout and no ETHERSCAN_API_KEY → skipped")
        return False
    U = f"https://api.etherscan.io/v2/api?chainid={cid}&apikey={ETHERSCAN}&address={addr}"
    bal = http(U + "&module=account&action=balance") or {}
    print(f"== {chain} {addr}  balance {int(bal.get('result') or 0) / 1e18:.6f}")
    for action, title in (("txlist", "native txs"), ("tokentx", "token transfers")):
        r = http(U + f"&module=account&action={action}&sort=desc&page=1&offset=100") or {}
        rows = r.get("result") if isinstance(r.get("result"), list) else []
        print(f"-- {title} ({len(rows)} shown)")
        for t in rows:
            import datetime
            when = datetime.datetime.fromtimestamp(int(t["timeStamp"]), datetime.UTC).strftime("%Y-%m-%dT%H:%M")
            if action == "txlist":
                print(f"{when} {t['hash'][:14]} {t['from'][:10]} -> {t['to'][:12]} {label(t['to'], ''):<28} {int(t['value']) / 1e18:>12.6f} {t.get('functionName', '')[:30]}")
            else:
                dec = int(t.get("tokenDecimal") or 18)
                sym = t.get("tokenSymbol") or "?"
                spoof = " [SPOOFED-SYMBOL]" if SPOOF.search(sym) else ""
                print(f"{when} {t['hash'][:14]} {t['from'][:10]} -> {t['to'][:12]} {label(t['to'], ''):<28} {int(t['value']) / 10**dec:>14,.4f} {sym}{spoof}")
    return True


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    addr = a[0]
    chains = list(ETHERSCAN_CHAINIDS) if "--all-chains" in a else [a[a.index("--chain") + 1] if "--chain" in a else "eth"]
    for c in chains:
        if not blockscout(addr, c):
            etherscan(addr, c)
