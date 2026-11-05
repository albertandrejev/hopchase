#!/usr/bin/env python3
"""Solana address / transaction tracer.

Usage:
  sol_trace.py tx <SIGNATURE>                 # decode one transaction (signer, instructions, deltas, CU fingerprint)
  sol_trace.py history <ADDRESS> [--cap N]    # full history: per-tx programs, token deltas by owner, SOL deltas
  sol_trace.py balances <ADDRESS>             # current SOL + all token accounts
  sol_trace.py poison <TOKEN_ACCOUNT> <RECIPIENT> [--before UNIX_TS]
                                              # look-alike senders in victim's history before the theft
  sol_trace.py --json ...                     # machine-readable output (history/tx)

Reads HELIUS_API_KEY from env (optional). Output goes to stdout; progress to stderr.
"""
import sys, json, time, re
from common import sol_rpc, SOL_SLEEP, SOL_PROGRAMS, SOL_MINTS, ts, log

B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def b58decode(s):
    n = 0
    for c in s:
        n = n * 58 + B58.index(c)
    return n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b"\x00"


def compute_budget(ins_list):
    """Return {'cu_limit':..,'cu_price':..} from ComputeBudget instructions (wallet-client fingerprint)."""
    out = {}
    for ins in ins_list:
        if ins.get("programId") != "ComputeBudget111111111111111111111111111111" or "data" not in ins:
            continue
        b = b58decode(ins["data"])
        tag, v = b[0], int.from_bytes(b[1:], "little")
        if tag == 2:
            out["cu_limit"] = v
        elif tag == 3:
            out["cu_price"] = v
    return out


def get_tx(sig):
    return sol_rpc("getTransaction", [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}])


def summarize(t):
    m, msg = t["meta"], t["transaction"]["message"]
    keys = [k["pubkey"] for k in msg["accountKeys"]]
    signers = [k["pubkey"] for k in msg["accountKeys"] if k.get("signer")]
    progs = {i["programId"] for i in msg["instructions"]}
    for ii in m.get("innerInstructions", []):
        progs |= {i["programId"] for i in ii["instructions"]}
    bal = {}
    for b in m.get("preTokenBalances", []):
        k = (b.get("owner"), b["mint"]); bal[k] = bal.get(k, 0) - int(b["uiTokenAmount"]["amount"])
    for b in m.get("postTokenBalances", []):
        k = (b.get("owner"), b["mint"]); bal[k] = bal.get(k, 0) + int(b["uiTokenAmount"]["amount"])
    deltas = [{"owner": o, "mint": mi, "raw": d} for (o, mi), d in bal.items() if d]
    sol = [{"account": k, "lamports": m["postBalances"][i] - m["preBalances"][i]}
           for i, k in enumerate(keys) if abs(m["postBalances"][i] - m["preBalances"][i]) > 100000]
    memo = None
    for l in m.get("logMessages", []):
        if l.startswith("Program log: Memo"):
            memo = l[len("Program log: "):][:200]
    return {
        "sig": t["transaction"]["signatures"][0], "time": ts(t["blockTime"]), "unix": t["blockTime"], "slot": t["slot"],
        "ok": t["meta"]["err"] is None, "signers": signers,
        "programs": sorted(SOL_PROGRAMS.get(p, p) for p in progs if p != "ComputeBudget111111111111111111111111111111"),
        "token_deltas": deltas, "sol_deltas": sol, "cu": compute_budget(msg["instructions"]), "memo": memo,
    }


def fmt_amount(mint, raw):
    sym, dec = SOL_MINTS.get(mint, (mint[:6] + "…", None))
    return f"{sym} {raw / 10**dec:+,.6f}".rstrip("0").rstrip(".") if dec is not None else f"{sym} {raw:+,}"


def print_summary(s):
    print(f"\n[{s['time']}] {'' if s['ok'] else 'FAIL '}{s['sig']}" + (f"  memo: {s['memo']}" if s["memo"] else ""))
    print("   programs:", ", ".join(s["programs"]), "| cu:", s["cu"] or "-")
    for d in sorted(s["token_deltas"], key=lambda x: -abs(x["raw"])):
        print(f"   {d['owner']} {fmt_amount(d['mint'], d['raw'])}")
    for d in sorted(s["sol_deltas"], key=lambda x: -abs(x["lamports"])):
        print(f"   {d['account']} SOL {d['lamports'] / 1e9:+.4f}")


def signatures(addr, cap=5000, until_unix=None):
    out, before = [], None
    while True:
        p = {"limit": 1000}
        if before:
            p["before"] = before
        r = sol_rpc("getSignaturesForAddress", [addr, p]) or []
        out += r
        if len(r) < 1000 or len(out) >= cap:
            return out
        before = r[-1]["signature"]


def cmd_tx(sig, as_json):
    t = get_tx(sig)
    if not t:
        sys.exit("transaction not found / RPC error")
    s = summarize(t)
    s["instructions"] = [{"program": SOL_PROGRAMS.get(i["programId"], i["programId"]),
                          "parsed": i.get("parsed")} for i in t["transaction"]["message"]["instructions"]]
    print(json.dumps(s, indent=1, ensure_ascii=False) if as_json else "", end="")
    if not as_json:
        print_summary(s)
        print("   signers:", ", ".join(s["signers"]), "| slot:", s["slot"])
        for i in s["instructions"]:
            if isinstance(i["parsed"], dict):
                print(f"   ins {i['program']}: {i['parsed'].get('type')} {json.dumps(i['parsed'].get('info'), ensure_ascii=False)[:300]}")


def cmd_history(addr, cap, as_json):
    ss = signatures(addr, cap)
    log(f"{addr}: {len(ss)} signatures")
    rows = []
    for n, s in enumerate(reversed(ss), 1):
        t = get_tx(s["signature"])
        if not t:
            log("  ?? no tx", s["signature"]); continue
        sm = summarize(t)
        rows.append(sm)
        if not as_json:
            print_summary(sm)
        if n % 50 == 0:
            log(f"  {n}/{len(ss)}")
        time.sleep(SOL_SLEEP)
    if as_json:
        print(json.dumps(rows, ensure_ascii=False))


def cmd_balances(addr):
    lam = sol_rpc("getBalance", [addr])
    print(f"SOL {lam['value'] / 1e9:.6f}" if lam else "SOL ?")
    for pid in ("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"):
        r = sol_rpc("getTokenAccountsByOwner", [addr, {"programId": pid}, {"encoding": "jsonParsed"}])
        for a in (r or {}).get("value", []):
            i = a["account"]["data"]["parsed"]["info"]
            sym = SOL_MINTS.get(i["mint"], (i["mint"], None))[0]
            print(f"{a['pubkey']}  {sym:<44} {i['tokenAmount']['uiAmountString']}")


def cmd_poison(token_account, recipient, before_unix):
    """Address poisoning check: senders whose address shares prefix/suffix with the recipient, BEFORE the theft."""
    pre, suf = recipient[:4], recipient[-4:]
    ss = signatures(token_account)
    hits = []
    for s in ss:
        if before_unix and s["blockTime"] >= before_unix:
            continue
        t = get_tx(s["signature"])
        if not t:
            continue
        for d in summarize(t)["token_deltas"]:
            o = d["owner"] or ""
            if o != recipient and (o.startswith(pre) or o.endswith(suf)):
                hits.append((ts(t["blockTime"]), o, d["raw"], s["signature"]))
        time.sleep(SOL_SLEEP)
    if hits:
        print("LOOK-ALIKE SENDERS BEFORE THEFT (poisoning likely):")
        for h in hits:
            print("  ", *h)
    else:
        print("No look-alike senders before the theft → address poisoning excluded.")


if __name__ == "__main__":
    args = sys.argv[1:]
    as_json = "--json" in args
    args = [a for a in args if a != "--json"]
    if not args:
        sys.exit(__doc__)
    cmd = args[0]
    if cmd == "tx":
        cmd_tx(args[1], as_json)
    elif cmd == "history":
        cap = int(args[args.index("--cap") + 1]) if "--cap" in args else 5000
        cmd_history(args[1], cap, as_json)
    elif cmd == "balances":
        cmd_balances(args[1])
    elif cmd == "poison":
        before = int(args[args.index("--before") + 1]) if "--before" in args else None
        cmd_poison(args[1], args[2], before)
    else:
        sys.exit(__doc__)
