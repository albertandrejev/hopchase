#!/usr/bin/env python3
"""Solana address / transaction tracer.

Usage:
  sol_trace.py tx <SIGNATURE>                 # decode one transaction (signer, instructions, deltas, CU fingerprint)
  sol_trace.py history <ADDRESS> [--cap N]    # full history: per-tx programs, signers, memos (as data), token deltas
                                              # by owner, SOL deltas; header: on-curve / PDA; footers: signer share +
                                              # (cu_limit, cu_price) pairs, programs per tx, top value recipients,
                                              # outgoing lot sizes, sweep-loop detection, co-signed txs (+ their
                                              # programs), time range per instruction type, memo deadlines
  sol_trace.py balances <ADDRESS>             # current SOL + all token accounts
  sol_trace.py freeze <TOKEN_ACCOUNT|WALLET>  # per token account: state (initialized/frozen), mint, freezeAuthority
  sol_trace.py program <PROGRAM_ID> [--cap N] # upgrade authority + dated deploy/upgrade/setAuthority history
  sol_trace.py poison <TOKEN_ACCOUNT> <RECIPIENT> [--before UNIX_TS]
                                              # look-alike senders in victim's history before the theft
  sol_trace.py --json ...                     # machine-readable output (history/tx)

Reads HELIUS_API_KEY / ANKR_API_KEY from env (optional). Output goes to stdout; progress to stderr.
"""
import sys, json, time, re
from collections import Counter
from common import sol_rpc, SOL_SLEEP, SOL_PROGRAMS, SOL_MINTS, SOL_LABELS, SOL_FREEZE_AUTHORITIES, ts, log

B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
TOKEN_PROGRAMS = ("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb")
MEMO_PROGRAMS = ("MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr", "Memo1UhkJRfHyvLMcVucJwxXeuD728EqVDDwQDxFMNo")
SWEEP_WINDOW_S = 60  # an inbound deposit forwarded out again within this window counts as a scripted sweep

# ed25519 curve parameters for the on-curve check (a 32-byte address that decodes to a valid point can have a
# private key; a PDA / program-derived address is deliberately off-curve and can never sign).
_P = 2 ** 255 - 19
_D = (-121665 * pow(121666, -1, _P)) % _P


def b58decode(s):
    n = 0
    for c in s:
        n = n * 58 + B58.index(c)
    return n.to_bytes((n.bit_length() + 7) // 8, "big") if n else b"\x00"


def on_curve(addr):
    """True when the address is a valid ed25519 point (a keypair can exist); False for PDAs and other off-curve
    byte strings. Pure integer arithmetic, no dependency."""
    b = b58decode(addr).rjust(32, b"\x00")
    if len(b) != 32:
        return False
    y = int.from_bytes(b, "little") & ((1 << 255) - 1)
    if y >= _P:
        return False
    y2 = y * y % _P
    x2 = (y2 - 1) * pow((_D * y2 + 1) % _P, -1, _P) % _P
    return x2 == 0 or pow(x2, (_P - 1) // 2, _P) == 1


def curve_label(addr):
    return "on-curve (a private key can exist)" if on_curve(addr) else "OFF-CURVE (PDA: program-derived, can never sign)"


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
    # maxSupportedTransactionVersion must be >= the tx version or the RPC returns an error instead of the tx.
    # With jsonParsed, accountKeys already contains addresses loaded from lookup tables (source: lookupTable),
    # so signer and SOL-delta logic below covers versioned transactions too.
    return sol_rpc("getTransaction", [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 1}])


def summarize(t):
    m, msg = t["meta"], t["transaction"]["message"]
    keys = [k["pubkey"] for k in msg["accountKeys"]]
    signers = [k["pubkey"] for k in msg["accountKeys"] if k.get("signer")]
    progs = {i["programId"] for i in msg["instructions"]}
    for ii in m.get("innerInstructions", []):
        progs |= {i["programId"] for i in ii["instructions"]}
    bal, decimals = {}, {}
    for b in m.get("preTokenBalances", []):
        k = (b.get("owner"), b["mint"]); bal[k] = bal.get(k, 0) - int(b["uiTokenAmount"]["amount"])
        decimals[b["mint"]] = b["uiTokenAmount"].get("decimals")
    for b in m.get("postTokenBalances", []):
        k = (b.get("owner"), b["mint"]); bal[k] = bal.get(k, 0) + int(b["uiTokenAmount"]["amount"])
        decimals[b["mint"]] = b["uiTokenAmount"].get("decimals")
    deltas = [{"owner": o, "mint": mi, "raw": d, "decimals": decimals.get(mi)} for (o, mi), d in bal.items() if d]
    sol = [{"account": k, "lamports": m["postBalances"][i] - m["preBalances"][i]}
           for i, k in enumerate(keys) if abs(m["postBalances"][i] - m["preBalances"][i]) > 100000]
    memos = []
    inner = [i for ii in m.get("innerInstructions", []) for i in ii["instructions"]]
    for i in list(msg["instructions"]) + inner:
        if i.get("programId") in MEMO_PROGRAMS and isinstance(i.get("parsed"), str):
            memos.append(i["parsed"][:300])
    if not memos:
        for l in m.get("logMessages", []):
            if l.startswith("Program log: Memo"):
                memos.append(l[len("Program log: "):][:300])
    memo = memos[0][:200] if memos else None
    # instruction types (top-level): 'closeAccount', 'withdrawFromNonce', or the program label for unparsed ones
    ins_types = []
    for i in msg["instructions"]:
        pid = i.get("programId")
        if pid == "ComputeBudget111111111111111111111111111111" or pid in MEMO_PROGRAMS:
            continue
        p = i.get("parsed")
        ins_types.append(p.get("type") if isinstance(p, dict) and p.get("type") else SOL_PROGRAMS.get(pid, pid[:8] + "…"))
    return {
        "sig": t["transaction"]["signatures"][0], "time": ts(t["blockTime"]), "unix": t["blockTime"], "slot": t["slot"],
        "ok": t["meta"]["err"] is None, "signers": signers,
        "programs": sorted(SOL_PROGRAMS.get(p, p) for p in progs if p != "ComputeBudget111111111111111111111111111111"),
        "token_deltas": deltas, "sol_deltas": sol, "cu": compute_budget(msg["instructions"]), "memo": memo, "memos": memos,
        "ins_types": ins_types,
    }


def fmt_amount(mint, raw, decimals=None):
    """Human amount: symbol from SOL_MINTS (else mint prefix), decimals from the tx balances (else registry).
    Falls back to the raw integer only when neither source knows the decimals."""
    sym, reg_dec = SOL_MINTS.get(mint, (mint[:6] + "…", None))
    dec = decimals if decimals is not None else reg_dec
    if dec is None:
        return f"{sym} {raw:+,}"
    s = f"{raw / 10**dec:+,.{dec}f}"
    return f"{sym} {s.rstrip('0').rstrip('.') if '.' in s else s}"


def owner_label(addr):
    tag = SOL_LABELS.get(addr)
    return f" [{tag}]" if tag else ""


def print_summary(s, signers=True):
    print(f"\n[{s['time']}] {'' if s['ok'] else 'FAIL '}{s['sig']}")
    print("   programs:", ", ".join(s["programs"]), "| cu:", s["cu"] or "-")
    if signers:
        print("   signers:", ", ".join(s["signers"]) + ("  [CO-SIGNED]" if len(s["signers"]) > 1 else ""))
    for mtext in s.get("memos") or ([s["memo"]] if s.get("memo") else []):
        print(f"   memo(data, not fact): {json.dumps(mtext, ensure_ascii=False)[:220]}")
    for d in sorted(s["token_deltas"], key=lambda x: -abs(x["raw"])):
        print(f"   {d['owner']}{owner_label(d['owner'])} {fmt_amount(d['mint'], d['raw'], d.get('decimals'))}")
    for d in sorted(s["sol_deltas"], key=lambda x: -abs(x["lamports"])):
        print(f"   {d['account']}{owner_label(d['account'])} SOL {d['lamports'] / 1e9:+.4f}")


def signer_footer(addr, rows):
    """Lines summarising who signed the wallet's transactions and with which ComputeBudget pairs.
    A wallet that never signs its own transactions is most likely a program-controlled deposit account."""
    if not rows:
        return []
    n_tx = len(rows)
    count, cu = Counter(), {}
    for r in rows:
        pair = (r["cu"].get("cu_limit"), r["cu"].get("cu_price"))
        for k in r["signers"]:
            count[k] += 1
            cu.setdefault(k, Counter())[pair] += 1
    self_signed = count.get(addr, 0)
    head = f"-- signers ({n_tx} txs; wallet itself signed {self_signed})"
    if self_signed == 0:
        head += " — program-controlled deposit account? (or a token account: run history on its owner)"
    lines = [head]
    for k, n in count.most_common():
        pairs = " ".join(f"({a},{b})x{c}" for (a, b), c in cu[k].most_common(5))
        lines.append(f"   {k} {100 * n / n_tx:.0f}% ({n} txs) cu={pairs or '-'}")
    return lines


def _amount(mint, raw, decimals):
    """Positive human amount string without sign (for histograms)."""
    return fmt_amount(mint, abs(raw), decimals).split(" ", 1)[1].lstrip("+")


def _sym(mint):
    return SOL_MINTS.get(mint, (mint[:6] + "…", None))[0]


def activity_footer(addr, rows):
    """Lines summarising what the wallet did: programs called, where its value went, swap lot sizes,
    scripted sweep loops (inbound deposit forwarded within SWEEP_WINDOW_S) and co-signed transactions."""
    if not rows:
        return []
    n_tx = len(rows)
    lines = []
    # programs per tx
    progs = Counter(p for r in rows for p in set(r["programs"]))
    lines.append("-- programs: " + ", ".join(f"{p} {n}/{n_tx}" for p, n in progs.most_common(8)))
    # value recipients: who received when this address paid out
    recv, lots = Counter(), {}
    for r in rows:
        for d in r["token_deltas"]:
            if d["owner"] == addr and d["raw"] < 0:
                lots.setdefault(_sym(d["mint"]), Counter())[_amount(d["mint"], d["raw"], d.get("decimals"))] += 1
                for e in r["token_deltas"]:
                    if e["mint"] == d["mint"] and e["raw"] > 0 and e["owner"] not in (addr, None):
                        recv[(e["owner"], _sym(d["mint"]))] += e["raw"] / 10 ** (e.get("decimals") or 0)
        if any(x["account"] == addr and x["lamports"] < 0 for x in r["sol_deltas"]):
            for e in r["sol_deltas"]:
                if e["lamports"] > 0 and e["account"] != addr:
                    recv[(e["account"], "SOL")] += e["lamports"] / 1e9
    if recv:
        lines.append("-- top value recipients (from this address):")
        for (who, sym), amt in recv.most_common(10):
            lines.append(f"   {who}{owner_label(who)} {sym} {amt:,.4f}")
    for sym, c in lots.items():
        if sum(c.values()) >= 3:
            lines.append(f"-- outgoing lots {sym}: " + ", ".join(f"{a} ×{n}" for a, n in c.most_common(6)))
    # sweep loop: inbound deposit of mint M forwarded out within the window
    sweeps, max_dt, sweepers = 0, 0, Counter()
    ordered = sorted(rows, key=lambda r: r["unix"])
    for i, r in enumerate(ordered):
        for d in r["token_deltas"]:
            if d["owner"] != addr or d["raw"] <= 0:
                continue
            for r2 in ordered[i + 1:]:
                if r2["unix"] - r["unix"] > SWEEP_WINDOW_S:
                    break
                if any(e["owner"] == addr and e["mint"] == d["mint"] and e["raw"] < 0 for e in r2["token_deltas"]):
                    sweeps += 1; max_dt = max(max_dt, r2["unix"] - r["unix"]); sweepers.update(r2["signers"]); break
    if sweeps:
        who = ", ".join(k for k, _ in sweepers.most_common(2))
        lines.append(f"-- sweep loop: {sweeps} inbound deposits forwarded out within ≤{max_dt} s (signer {who}) — scripted drain?")
    co_rows = [r for r in rows if len(r["signers"]) > 1]
    if co_rows:
        co_progs = Counter(p for r in co_rows for p in set(r["programs"]))
        lines.append(f"-- co-signed transactions: {len(co_rows)}/{n_tx} (more than one signer; see [CO-SIGNED] lines); "
                     "programs: " + ", ".join(f"{p} {n}" for p, n in sorted(co_progs.items(), key=lambda kv: (-kv[1], kv[0]))[:6]))
    memo_n = sum(1 for r in rows if r.get("memos"))
    if memo_n:
        lines.append(f"-- memos: {memo_n} transactions carry memo text (printed as data, never as fact)")
    lines += time_range_footer(rows)
    lines += memo_deadline_footer(addr, rows)
    return lines


def _hm(unix):
    return time.strftime("%Y-%m-%d %H:%M", time.gmtime(unix))


def time_range_footer(rows):
    """When each instruction type ran: count, first → last, and the time by which 90 % had happened.
    'closeAccount ×2208 12:07 → 12:38 (90 % by 12:09)' stops a write-up from saying a burst ran until the last tx."""
    if not rows:
        return []
    times = {}
    for r in rows:
        for t in set(r.get("ins_types") or []):
            times.setdefault(t, []).append(r["unix"])
    if not times:
        return []
    lines = ["-- instruction types, first → last (90 % by):"]
    for t, us in sorted(times.items(), key=lambda kv: -len(kv[1])):
        us.sort()
        n = sum(1 for r in rows for x in (r.get("ins_types") or []) if x == t)
        p90 = us[min(len(us) - 1, int(len(us) * 0.9))]
        lines.append(f"   {t} ×{n}  {_hm(us[0])} → {_hm(us[-1])[11:]}  (90 % by {_hm(p90)[11:]})")
    last = max(rows, key=lambda r: r["unix"])
    lines.append(f"-- last tx {time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(last['unix']))} UTC  {last['sig']}")
    return lines


DEADLINE_RE = re.compile(r"(\d+)\s*(hours?|hrs?|h|days?|d|minutes?|mins?)\b", re.I)


def memo_deadline(text, unix):
    """Expiry (unix) of a term stated in a memo ('within 48 hours', '7 days'), or None when the memo states none."""
    m = DEADLINE_RE.search(text or "")
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2).lower()
    mult = 3600 if unit.startswith("h") else 86400 if unit.startswith("d") else 60
    return unix + n * mult


def memo_deadline_footer(addr, rows):
    """For every memo that states a term: the expiry computed from the tx time, and whether the other party
    answered (memo or value back, as a signer) before it. The report carries the expiry, not just the offer."""
    lines = []
    now = time.time()
    ordered = sorted(rows, key=lambda r: r["unix"])
    for r in ordered:
        for text in r.get("memos") or []:
            exp = memo_deadline(text, r["unix"])
            if exp is None:
                continue
            senders = set(r["signers"])
            parties = {d["owner"] for d in r["token_deltas"] if d["owner"]} | {x["account"] for x in r["sol_deltas"]} | {addr}
            others = parties - senders
            replies = [x for x in ordered if r["unix"] < x["unix"] <= exp and set(x["signers"]) & others
                       and (x.get("memos") or any(d["owner"] in senders for d in x["token_deltas"])
                            or any(s["account"] in senders for s in x["sol_deltas"]))]
            state = ("still open" if exp > now else "expired") if not replies else f"{len(replies)} reply tx, first {ts(replies[0]['unix'])}"
            lines.append(f"-- memo deadline: {json.dumps(text[:70], ensure_ascii=False)} sent {ts(r['unix'])} by "
                         f"{', '.join(sorted(senders))[:44]} → expires {ts(exp)}; reply before expiry: {state}")
    return lines


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
        print_summary(s, signers=False)
        print("   signers:", ", ".join(s["signers"]), "| slot:", s["slot"])
        for i in s["instructions"]:
            if isinstance(i["parsed"], dict):
                print(f"   ins {i['program']}: {i['parsed'].get('type')} {json.dumps(i['parsed'].get('info'), ensure_ascii=False)[:300]}")


def cmd_history(addr, cap, as_json):
    ss = signatures(addr, cap)[:cap]  # newest `cap` signatures; signatures() only stops paging at the cap
    log(f"{addr}: {len(ss)} signatures")
    if not as_json:
        print(f"== {addr}{owner_label(addr)}  {curve_label(addr)}  {len(ss)} signatures")
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
    else:
        print()
        for line in signer_footer(addr, rows) + activity_footer(addr, rows):
            print(line)


def cmd_balances(addr):
    lam = sol_rpc("getBalance", [addr])
    print(f"== {addr}{owner_label(addr)}  {curve_label(addr)}")
    print(f"SOL {lam['value'] / 1e9:.6f}" if lam else "SOL ?")
    for pid in TOKEN_PROGRAMS:
        r = sol_rpc("getTokenAccountsByOwner", [addr, {"programId": pid}, {"encoding": "jsonParsed"}])
        for a in (r or {}).get("value", []):
            i = a["account"]["data"]["parsed"]["info"]
            sym = SOL_MINTS.get(i["mint"], (i["mint"], None))[0]
            print(f"{a['pubkey']}  {sym:<44} {i['tokenAmount']['uiAmountString']}")


def parsed_account(pubkey):
    """jsonParsed account info or None (RPC error already logged)."""
    r = sol_rpc("getAccountInfo", [pubkey, {"encoding": "jsonParsed"}])
    if r is None:
        return None
    return (r.get("value") or {})


def token_account_states(target):
    """[(token_account, info)] for a token account or for every token account owned by a wallet. None on RPC error."""
    acc = parsed_account(target)
    if acc is None:
        return None
    parsed = ((acc.get("data") or {}).get("parsed") or {}) if isinstance(acc.get("data"), dict) else {}
    if parsed.get("type") == "account":
        return [(target, parsed["info"])]
    out = []
    for pid in TOKEN_PROGRAMS:
        r = sol_rpc("getTokenAccountsByOwner", [target, {"programId": pid}, {"encoding": "jsonParsed"}])
        if r is None:
            return None
        for a in r.get("value", []):
            out.append((a["pubkey"], a["account"]["data"]["parsed"]["info"]))
    return out


LOADER = "BPFLoaderUpgradeab1e11111111111111111111111"
LOADER_TYPES = ("deployWithMaxDataLen", "upgrade", "setAuthority", "extendProgram", "close", "write", "initializeBuffer")


def loader_events(txs):
    """[(unix, type, authority, sig)] for every bpf-upgradeable-loader instruction in the given parsed transactions."""
    out = []
    for t in txs:
        for i in t["transaction"]["message"]["instructions"]:
            p = i.get("parsed")
            if i.get("programId") == LOADER and isinstance(p, dict):
                info = p.get("info") or {}
                out.append((t["blockTime"], p.get("type"), info.get("authority") or info.get("payerAccount"), t["transaction"]["signatures"][0]))
    return sorted(out)


def upgrade_footer(events):
    """How often the program was upgraded, so a post-incident upgrade is read against the base rate, not alone."""
    ups = [e for e in events if e[1] in ("upgrade", "deployWithMaxDataLen")]
    if not ups:
        return ["-- upgrades: none in the decoded transactions"]
    first, last = ups[0][0], ups[-1][0]
    days = max(1, (last - first) / 86400)
    recent = sum(1 for e in ups if last - e[0] <= 30 * 86400)
    return [f"-- upgrades: {len(ups)} between {ts(first)} and {ts(last)} (one every ~{days / max(1, len(ups) - 1):.1f} d); "
            f"{recent} in the 30 d before the latest — read any 'reaction' upgrade against this rate"]


def cmd_program(prog, cap):
    """Program profile: upgrade authority, program-data account, and the dated upgrade/authority history."""
    acc = parsed_account(prog)
    if acc is None:
        sys.exit("RPC error")
    if not acc:
        sys.exit(f"{prog}: no account")
    data = acc.get("data")
    parsed = data.get("parsed") if isinstance(data, dict) else None
    tag = SOL_PROGRAMS.get(prog) or SOL_LABELS.get(prog)
    print(f"== {prog}{f' [{tag}]' if tag else ''}  {curve_label(prog)}  owner {SOL_PROGRAMS.get(acc.get('owner'), acc.get('owner'))}"
          + ("  executable" if acc.get("executable") else "  NOT executable"))
    if acc.get("owner") != LOADER or not parsed or parsed.get("type") != "program":
        print("-- not an upgradeable-loader program (no upgrade history to read)")
        return
    pd = parsed["info"]["programData"]
    pda = parsed_account(pd) or {}
    pinfo = (((pda.get("data") or {}).get("parsed") or {}).get("info") or {}) if isinstance(pda.get("data"), dict) else {}
    auth = pinfo.get("authority")
    print(f"-- programData {pd}  upgrade authority {auth or 'none (immutable)'}  last deploy slot {pinfo.get('slot')}")
    sigs = signatures(pd, cap)[:cap]
    log(f"{pd}: {len(sigs)} signatures")
    txs = []
    for s in sigs:
        t = get_tx(s["signature"])
        if t:
            txs.append(t)
        time.sleep(SOL_SLEEP)
    events = loader_events(txs)
    print(f"-- loader transactions: {len(events)} of {len(sigs)} decoded signatures (cap {cap})")
    for unix, typ, who, sig in events:
        print(f"   {ts(unix)}  {typ:<20} authority={who}  {sig}")
    for line in upgrade_footer(events):
        print(line)


def cmd_freeze(target):
    """Freeze status: token-account `state` and the mint's `freezeAuthority` (who can freeze it)."""
    rows = token_account_states(target)
    if rows is None:
        log(f"freeze {target}: RPC error, status unknown")
        print(f"{target}  state=?  mint=?  freezeAuthority=?")
        return
    if not rows:
        print(f"{target}: no token accounts")
        return
    mint_cache = {}
    for ta, info in rows:
        mint = info.get("mint", "?")
        if mint not in mint_cache:
            macc = parsed_account(mint)
            if macc is None:
                log(f"freeze {target}: mint {mint} getAccountInfo failed")
                mint_cache[mint] = "?"
            else:
                minfo = (((macc.get("data") or {}).get("parsed") or {}).get("info") or {}) if isinstance(macc.get("data"), dict) else {}
                fa = minfo.get("freezeAuthority")
                mint_cache[mint] = (fa + (f" [{SOL_FREEZE_AUTHORITIES[fa]}]" if fa in SOL_FREEZE_AUTHORITIES else "")) if fa else "none"
        sym = SOL_MINTS.get(mint, (mint[:6] + "…", None))[0]
        amt = (info.get("tokenAmount") or {}).get("uiAmountString", "?")
        print(f"{ta}  state={info.get('state', '?'):<12} {sym:<8} {amt:>20}  mint={mint}  freezeAuthority={mint_cache[mint]}")


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
    elif cmd == "freeze":
        cmd_freeze(args[1])
    elif cmd == "program":
        cap = int(args[args.index("--cap") + 1]) if "--cap" in args else 300
        cmd_program(args[1], cap)
    elif cmd == "poison":
        before = int(args[args.index("--before") + 1]) if "--before" in args else None
        cmd_poison(args[1], args[2], before)
    else:
        sys.exit(__doc__)
