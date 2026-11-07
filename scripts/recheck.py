#!/usr/bin/env python3
"""Live re-verification of a case before writing/updating the report.

Usage:
  recheck.py case.json

case.json:
{
  "solana": {"wallets": ["A9a6..."], "token_accounts": ["J98K..."],
             "escrows": ["7uTT..."]},
  "evm":    {"addresses": ["0xDF60..."], "chains": ["eth"]},
  "tron":   {"addresses": ["TXLoz..."]},
  "bridgers": ["A9a6...", "0xDF60..."]
}
`escrows` are program-controlled deposit accounts (bridge depositories, Mayan state accounts) whose balance and
token accounts are printed like a wallet's. Every token account also gets a freeze line (`state=initialized|frozen`).
Prints current balances, the latest 5 signatures/txs per address, and new Bridgers orders —
compare with the report's "as of" values. Designed to be run by a scheduled task as a monitor.
Output is grouped into `## <section> (read <time>)` blocks and ends with an `## as-of stamps` line: balances,
freeze state, latest activity and bridge orders are read at different moments, and the report lead must carry
each stamp that differs ("balances 6 Nov 23:56; freeze state 7 Nov 09:53").
Every RPC failure prints `?` on that line and a stderr message; the run continues.
"""
import sys, json, time
from common import sol_rpc, http, tron_headers, USDT_TRON, BLOCKSCOUT, SOL_SLEEP, SOL_MINTS, ts, log

TOKEN_PROGRAMS = ("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb")


def token_account_info(ta):
    """jsonParsed token-account info dict, {} when the account is not a token account, None on RPC error."""
    r = sol_rpc("getAccountInfo", [ta, {"encoding": "jsonParsed"}])
    if r is None:
        return None
    data = (r.get("value") or {}).get("data")
    parsed = data.get("parsed") if isinstance(data, dict) else None
    return (parsed or {}).get("info") or {}


def freeze_line(ta, info=None):
    if info is None:
        info = token_account_info(ta)
    if info is None:
        log(f"freeze {ta}: RPC error")
        return f"   freeze {ta}: state=?"
    if not info:
        return f"   freeze {ta}: closed / not a token account"
    sym = SOL_MINTS.get(info.get("mint", ""), (info.get("mint", "?")[:6] + "…", None))[0]
    return f"   freeze {ta}: state={info.get('state', '?')} {sym}"


def latest_sigs(addr):
    r = sol_rpc("getSignaturesForAddress", [addr, {"limit": 5}])
    print(f"SOL latest {addr}:" + ("" if r is not None else " ?"))
    for s in r or []:
        print(f"   {ts(s['blockTime']) if s.get('blockTime') else '?'} {s['signature'][:24]} {'ERR' if s.get('err') else ''}")
    time.sleep(SOL_SLEEP)


def now_utc():
    return time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())


def section(stamps, name):
    """Print a section header carrying its own read time and remember it for the as-of footer.
    Balances, freeze state, latest activity and bridge orders are read at different moments; the report lead
    must carry every stamp that differs, never one 'as of' for all of them."""
    stamps.append((name, now_utc()))
    print(f"## {name} (read {stamps[-1][1]})")


def main(path):
    c = json.load(open(path))
    sol = c.get("solana", {})
    stamps = []
    print("# recheck", now_utc())
    section(stamps, "Solana balances")
    infos = {}
    for ta in sol.get("token_accounts", []):
        r = sol_rpc("getTokenAccountBalance", [ta])
        print(f"SOL token acct {ta}: {r['value']['uiAmountString'] if r else '?'}")
        infos[ta] = token_account_info(ta)
        time.sleep(SOL_SLEEP)
    if sol.get("token_accounts"):
        section(stamps, "Solana freeze state")
        for ta in sol.get("token_accounts", []):
            print(freeze_line(ta, infos.get(ta)))
    section(stamps, "Solana latest activity")
    for w in sol.get("wallets", []) + sol.get("token_accounts", []):
        latest_sigs(w)
    if sol.get("escrows"):
        section(stamps, "Solana escrows (balances + freeze state)")
    for e in sol.get("escrows", []):
        lam = sol_rpc("getBalance", [e])
        print(f"SOL escrow {e}: SOL {lam['value'] / 1e9:.6f}" if lam else f"SOL escrow {e}: SOL ?")
        for pid in TOKEN_PROGRAMS:
            r = sol_rpc("getTokenAccountsByOwner", [e, {"programId": pid}, {"encoding": "jsonParsed"}])
            if r is None:
                print(f"   token accounts ({pid[:8]}…): ?")
                continue
            for a in r.get("value", []):
                info = a["account"]["data"]["parsed"]["info"]
                sym = SOL_MINTS.get(info["mint"], (info["mint"][:6] + "…", None))[0]
                print(f"   {a['pubkey']}  {sym:<8} {info['tokenAmount']['uiAmountString']}")
                print(freeze_line(a["pubkey"], info))
            time.sleep(SOL_SLEEP)
        latest_sigs(e)
    if c.get("evm", {}).get("addresses"):
        section(stamps, "EVM balances + latest txs")
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
    if c.get("tron", {}).get("addresses"):
        section(stamps, "TRON balances + outgoing")
    for a in c.get("tron", {}).get("addresses", []):
        H = tron_headers()
        acc = ((http(f"https://api.trongrid.io/v1/accounts/{a}", headers=H) or {}).get("data") or [{}])[0]
        usdt = next((int(x[USDT_TRON]) / 1e6 for x in acc.get("trc20", []) if USDT_TRON in x), 0)
        out = (http(f"https://api.trongrid.io/v1/accounts/{a}/transactions/trc20?only_from=true&limit=5", headers=H) or {}).get("data") or []
        print(f"TRON {a}: TRX {acc.get('balance', 0) / 1e6:,.2f} USDT {usdt:,.2f} | outgoing TRC-20: {len(out)}")
        for t in out:
            print(f"   {ts(t['block_timestamp'] // 1000)} {int(t['value']) / 1e6:,.2f} {t['token_info'].get('symbol')} -> {t['to']}")
    if c.get("bridgers"):
        section(stamps, "Bridgers orders")
    for a in c.get("bridgers", []):
        r = http("https://api.bridgers.xyz/api/exchangeRecord/getTransData",
                 {"pageNo": 1, "pageSize": 20, "fromAddress": a, "equipmentNo": a, "sourceType": "H5", "sourceFlag": "widget"}) or {}
        d = r.get("data") or {}
        print(f"Bridgers {a}: {d.get('total', 0)} orders; latest: " +
              "; ".join(f"{o['createTime']} {o['fromTokenAmount']} {o['fromCoinCode']}→{o['toCoinCode']} {o['status']}" for o in (d.get('list') or [])[:3]))
    print("## as-of stamps (quote every one that differs in the report lead): " + "; ".join(f"{n} {t}" for n, t in stamps))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1])
