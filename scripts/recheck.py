#!/usr/bin/env python3
"""Live re-verification of a case before writing/updating the report.

Usage:
  recheck.py case.json

case.json:
{
  "solana": {"wallets": ["A9a6..."], "token_accounts": ["J98K..."]},
  "evm":    {"addresses": ["0xDF60..."], "chains": ["eth"]},
  "tron":   {"addresses": ["TXLoz..."]},
  "bridgers": ["A9a6...", "0xDF60..."]
}
Prints current balances, the latest 5 signatures/txs per address, and new Bridgers orders —
compare with the report's "as of" values. Designed to be run by a scheduled task as a monitor.
"""
import sys, json, time
from common import sol_rpc, http, tron_headers, USDT_TRON, BLOCKSCOUT, SOL_SLEEP, ts


def main(path):
    c = json.load(open(path))
    print("# recheck", time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()))
    for ta in c.get("solana", {}).get("token_accounts", []):
        r = sol_rpc("getTokenAccountBalance", [ta])
        print(f"SOL token acct {ta}: {r['value']['uiAmountString'] if r else '?'}")
        time.sleep(SOL_SLEEP)
    for w in c.get("solana", {}).get("wallets", []) + c.get("solana", {}).get("token_accounts", []):
        r = sol_rpc("getSignaturesForAddress", [w, {"limit": 5}]) or []
        print(f"SOL latest {w}:")
        for s in r:
            print(f"   {ts(s['blockTime'])} {s['signature'][:24]} {'ERR' if s['err'] else ''}")
        time.sleep(SOL_SLEEP)
    for a in c.get("evm", {}).get("addresses", []):
        for ch in c.get("evm", {}).get("chains", ["eth"]):
            base = BLOCKSCOUT.get(ch)
            if not base:
                continue
            info = http(f"{base}/api/v2/addresses/{a}") or {}
            txs = (http(f"{base}/api/v2/addresses/{a}/transactions") or {}).get("items", [])[:5]
            print(f"EVM {ch} {a}: balance {int(info.get('coin_balance') or 0) / 1e18:.6f}")
            for t in txs:
                print(f"   {t['timestamp'][:16]} {t['hash'][:14]} -> {(t.get('to') or {}).get('name') or (t.get('to') or {}).get('hash', '')[:12]} {t.get('method') or ''}")
    for a in c.get("tron", {}).get("addresses", []):
        H = tron_headers()
        acc = ((http(f"https://api.trongrid.io/v1/accounts/{a}", headers=H) or {}).get("data") or [{}])[0]
        usdt = next((int(x[USDT_TRON]) / 1e6 for x in acc.get("trc20", []) if USDT_TRON in x), 0)
        out = (http(f"https://api.trongrid.io/v1/accounts/{a}/transactions/trc20?only_from=true&limit=5", headers=H) or {}).get("data") or []
        print(f"TRON {a}: TRX {acc.get('balance', 0) / 1e6:,.2f} USDT {usdt:,.2f} | outgoing TRC-20: {len(out)}")
        for t in out:
            print(f"   {ts(t['block_timestamp'] // 1000)} {int(t['value']) / 1e6:,.2f} {t['token_info'].get('symbol')} -> {t['to']}")
    for a in c.get("bridgers", []):
        r = http("https://api.bridgers.xyz/api/exchangeRecord/getTransData",
                 {"pageNo": 1, "pageSize": 20, "fromAddress": a, "equipmentNo": a, "sourceType": "H5", "sourceFlag": "widget"}) or {}
        d = r.get("data") or {}
        print(f"Bridgers {a}: {d.get('total', 0)} orders; latest: " +
              "; ".join(f"{o['createTime']} {o['fromTokenAmount']} {o['fromCoinCode']}→{o['toCoinCode']} {o['status']}" for o in (d.get('list') or [])[:3]))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1])
