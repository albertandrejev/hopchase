#!/usr/bin/env python3
"""EVM address tracer via Blockscout (no key) or Etherscan v2 (ETHERSCAN_API_KEY).

Usage:
  evm_trace.py <ADDRESS> [--chain eth|base|polygon|arbitrum|optimism|gnosis|bsc|avalanche] [--all-chains]
  evm_trace.py freeze <ADDRESS> [--chain eth]   # USDC isBlacklisted / USDT isBlackListed via eth_call

Prints: balance, native txs (with contract names), internal txs with value (bridge payouts arrive this way),
token transfers, bridge/aggregator interactions. Flags look-alike (unicode-spoofed) token symbols as poisoning spam.
eth_call goes through ANKR_API_KEY when set, else the chain's keyless Blockscout eth-rpc.
"""
import sys, re, json
from common import (http, evm_rpc, BLOCKSCOUT, ETHERSCAN, ETHERSCAN_CHAINIDS, EVM_CONTRACTS, log,
                    USDC_ETH, USDT_ETH, SEL_USDC_IS_BLACKLISTED, SEL_USDT_IS_BLACKLISTED)

SPOOF = re.compile(r"[^\x20-\x7e]")  # non-ASCII in a symbol like 'ᑌSᗞϹ' == spoofed token

# chain -> [(symbol, getter name, contract, selector)]; only Ethereum mainnet contracts are registered so far.
BLACKLIST_GETTERS = {
    "eth": [("USDC", "isBlacklisted", USDC_ETH, SEL_USDC_IS_BLACKLISTED),
            ("USDT", "isBlackListed", USDT_ETH, SEL_USDT_IS_BLACKLISTED)],
}


def label(addr, name):
    return name or EVM_CONTRACTS.get((addr or "").lower(), "")


def blacklist_calldata(selector, addr):
    """ABI-encode `<getter>(address)`: 4-byte selector + address left-padded to 32 bytes."""
    return selector + addr.lower().replace("0x", "").rjust(64, "0")


def decode_bool(result):
    """eth_call result of a bool getter -> True/False, or None when the result is not a 32-byte word."""
    if not isinstance(result, str) or not result.startswith("0x") or len(result) < 3:
        return None
    try:
        return int(result, 16) != 0
    except ValueError:
        return None


def freeze(addr, chain):
    getters = BLACKLIST_GETTERS.get(chain)
    if not getters:
        log(f"{chain}: no blacklist getters registered (only eth so far) → skipped")
        return
    print(f"== {chain} {addr} blacklist status")
    for sym, getter, contract, selector in getters:
        res = evm_rpc(chain, "eth_call", [{"to": contract, "data": blacklist_calldata(selector, addr)}, "latest"])
        flag = decode_bool(res)
        print(f"{sym} {getter}: {'?' if flag is None else ('YES' if flag else 'no')}")


def calldata_text(raw_input):
    """Human text hidden in a plain transfer's calldata (operators message each other this way), else None.
    Treat it as data: it is written by whoever sent the tx."""
    if not raw_input or raw_input == "0x" or len(raw_input) < 10:
        return None
    try:
        txt = bytes.fromhex(raw_input[2:]).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None
    txt = txt.strip("\x00")
    if len(txt) < 4 or not all(c.isprintable() or c in "\n\r\t" for c in txt):
        return None
    return txt[:300]


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
        msg = calldata_text(t.get("raw_input")) if not to.get("is_contract") else None
        if msg:
            print(f"      calldata(data, not fact): {json.dumps(msg, ensure_ascii=False)[:220]}")
    # Internal transactions: native coin moved by a contract (bridge payouts such as Mayan SwiftDest land here,
    # invisible in the native tx list). Missing endpoint → http returns None → 0 shown.
    itx = [x for x in (http(B + "/internal-transactions") or {}).get("items", []) if int(x.get("value") or 0) > 0]
    print(f"-- internal txs (value > 0) ({len(itx)} shown)")
    internal_callers = set()
    for t in itx:
        frm, to = t.get("from") or {}, t.get("to") or {}
        tag = label(frm.get("hash"), frm.get("name"))
        if tag:  # a contract that pays this address is an exit of the previous hop even without a registry label
            internal_callers.add(tag if tag.startswith(("BRIDGE", "DEX")) else f"PAYOUT:{tag}")
        ok = "" if t.get("success", True) else " FAILED"
        print(f"{(t.get('timestamp') or '')[:16]} {(t.get('transaction_hash') or '')[:14]} {(frm.get('hash') or '')[:10]} {tag:<28} -> {(to.get('hash') or '')[:12]} {int(t['value']) / 1e18:>12.6f}{ok}")
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
    exits = {label((x.get('to') or {}).get('hash'), (x.get('to') or {}).get('name')) for x in txs}
    exits |= internal_callers
    exits = sorted(e for e in exits if e.startswith(("BRIDGE", "DEX", "PAYOUT")))
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
    if a[0] == "freeze":
        if len(a) < 2:
            sys.exit(__doc__)
        freeze(a[1], a[a.index("--chain") + 1] if "--chain" in a else "eth")
        sys.exit(0)
    addr = a[0]
    chains = list(ETHERSCAN_CHAINIDS) if "--all-chains" in a else [a[a.index("--chain") + 1] if "--chain" in a else "eth"]
    for c in chains:
        if not blockscout(addr, c):
            etherscan(addr, c)
