#!/usr/bin/env python3
"""Cross-chain bridge order lookups (off-chain confirmation of hops). No API keys needed (RELAY_API_KEY optional).

Usage:
  bridges.py bridgers <ADDRESS>            # all Bridgers/SWFT orders where ADDRESS is the sender (any chain)
  bridges.py bridgers-order <ORDER_ID>     # one order in full
  bridges.py wormhole <ADDRESS|TXHASH>     # Wormholescan operations
  bridges.py debridge <TXHASH>             # deBridge DLN order ids for a source tx
  bridges.py mayan <SIG|TXHASH> [<SIG> …]  # Mayan order(s) for one or more txs, de-duplicated by orderId
  bridges.py mayan <ADDRESS>               # listed orders where ADDRESS is the trader (blocked orders never appear in listings)
  bridges.py relay <TXHASH|SIG|ADDRESS>    # Relay request for a tx, or all requests of a user address
  bridges.py all <ADDRESS>                 # bridgers + wormhole + mayan + relay

Bridgers is the one most often behind Trust Wallet's in-app swap ("source": "trustwallet-prod_...").
Relay: /requests/v3 with RELAY_API_KEY; without it the deprecated keyless /requests/v2 is used (sunset 2026-11-24).
"""
import sys, json, re
from datetime import datetime
from common import http, log, RELAY

BR = "https://api.bridgers.xyz/api/exchangeRecord/"
MAYAN = "https://explorer-api.mayan.finance/v3"
MAYAN_PAGE = 50  # the API rejects larger pages with LIMIT_TOO_LARGE
RELAY_API = "https://api.relay.link/requests"

HEX_HASH = re.compile(r"^0x[0-9a-fA-F]{64}$")
SOL_SIG = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{80,90}$")


def is_tx_ref(q):
    """True for an EVM tx hash or a Solana signature; False for an address."""
    return bool(HEX_HASH.match(q) or SOL_SIG.match(q))


def bridgers(addr, page_size=50):
    body = {"pageNo": 1, "pageSize": page_size, "fromAddress": addr, "equipmentNo": addr,
            "sourceType": "H5", "sourceFlag": "widget"}
    r = http(BR + "getTransData", body) or {}
    d = r.get("data") or {}
    rows = d.get("list") or []
    print(f"== Bridgers orders for {addr}: total {d.get('total', 0)}")
    for o in rows:
        print(f"{o['createTime']}  {o['fromTokenAmount']:>18} {o['fromCoinCode']:<12} -> {o['toTokenAmount']:>16} {o['toCoinCode']:<12} "
              f"to {o['toAddress']}  {o['status']}  src={o.get('source')}  orderId={o['orderId']}")
        print(f"      deposit {o.get('fromChain')} {o.get('hash')}")
        print(f"      payout  {o.get('toChain')} {o.get('toHash')}")
        if o.get("refundHash"):
            print(f"      REFUND {o.get('refundCoinAmt')} reason={o.get('refundReason')} {o.get('refundHash')}")
    return rows


def bridgers_order(order_id):
    r = http(BR + "getTransDataById", {"orderId": order_id}) or {}
    print(json.dumps(r.get("data"), indent=1, ensure_ascii=False))


def wormhole(q):
    r = http(f"https://api.wormholescan.io/api/v1/operations?address={q}&pageSize=50") or {}
    ops = r.get("operations") or []
    print(f"== Wormhole operations for {q}: {len(ops)}")
    for o in ops:
        src, dst = o.get("sourceChain") or {}, o.get("targetChain") or {}
        c = (o.get("content") or {}).get("standarizedProperties") or {}
        print(f"{src.get('timestamp', '')[:16]} chain {src.get('chainId')} -> {c.get('toChain')}  {c.get('amount')} {c.get('tokenAddress', '')[:12]}  to {c.get('toAddress')}  tx {src.get('transaction', {}).get('txHash', '')[:20]}")


def debridge(txhash):
    r = http(f"https://dln.debridge.finance/v1.0/dln/tx/{txhash}/order-ids") or {}
    print("== deBridge order ids:", r.get("orderIds"))
    for oid in r.get("orderIds") or []:
        o = http(f"https://dln.debridge.finance/v1.0/dln/order/{oid}") or {}
        print(json.dumps(o, indent=1)[:2000])


def parse_iso(s):
    """Unix seconds for a Mayan ISO timestamp ('2026-11-07T12:32:48.000Z'), None when absent/unparseable."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def fmt_lag(seconds):
    s = abs(seconds)
    if s < 120:
        return f"{s:.0f} s"
    if s < 7200:
        return f"{s / 60:.1f} min"
    return f"{s / 3600:.1f} h"


def is_refund(o):
    """The API echoes the fulfil hash into refundTxHash on completed orders; only a distinct hash is a refund."""
    return bool(o.get("refundTxHash")) and o.get("refundTxHash") != o.get("fulfillTxHash")


def deadline_lag(o):
    """(completedAt - deadline) in seconds, or None when either stamp is missing.
    Negative = settled/refunded before the deadline; positive = after it."""
    d, c = parse_iso(o.get("deadline")), parse_iso(o.get("completedAt"))
    return None if d is None or c is None else c - d


def refund_baseline(o):
    """'after deadline' / 'before deadline' / 'unknown' — Mayan refunds both expired orders and orders it could
    not fill at minAmountOut, so a refund-lag figure must say which population it describes."""
    lag = deadline_lag(o)
    if lag is None:
        return "unknown"
    return "after deadline" if lag > 0 else "before deadline"


def print_mayan_order(o):
    print(f"{(o.get('initiatedAt') or '')[:19]}  {o.get('fromAmount')} {o.get('fromTokenSymbol')} ({o.get('sourceChain')}) -> "
          f"{o.get('toAmount')} {o.get('toTokenSymbol')} ({o.get('destChain')})  status={o.get('status')}  service={o.get('service')}")
    print(f"      trader      {o.get('trader')}")
    print(f"      destAddress {o.get('destAddress')}")
    print(f"      source tx   {o.get('sourceTxHash')}")
    if o.get("fulfillTxHash"):
        print(f"      fulfill tx  {o.get('fulfillTxHash')}")
    if is_refund(o):
        print(f"      REFUND tx   {o.get('refundTxHash')}  refundAmount={o.get('refundAmount')} {o.get('refundTokenSymbol') or ''}")
    # screening: the order JSON says when Mayan blocked the address (such orders never appear in listings)
    sec = o.get("security") or {}
    sec_txt = f"security={sec.get('code')} {json.dumps(sec.get('msg'), ensure_ascii=False)}" if sec else "security=-"
    flag = "BLOCKED " if (o.get("sanctioned") or sec.get("code")) else ""
    print(f"      {flag}screening   sanctioned={o.get('sanctioned')} {sec_txt}")
    # deadline vs completion: one line answers "refunded 20.6 h after the deadline"
    if o.get("deadline") or o.get("completedAt"):
        lag = deadline_lag(o)
        what = "refunded" if is_refund(o) else "completed"
        rel = "" if lag is None else f"  ({what} {fmt_lag(lag)} {'after' if lag > 0 else 'before'} deadline)"
        print(f"      deadline    {(o.get('deadline') or '?')[:19]}  completedAt {(o.get('completedAt') or '?')[:19]}{rel}")
    if o.get("minAmountOut") is not None:
        print(f"      minAmountOut {o.get('minAmountOut')}")
    if o.get("stateAddr"):
        print(f"      stateAddr   {o.get('stateAddr')}")
    if o.get("sourceStateAddr"):
        print(f"      sourceStateAddr {o.get('sourceStateAddr')}")
    if o.get("orderHash"):
        print(f"      orderHash   {o.get('orderHash')}")


def order_key(o):
    return o.get("orderId") or o.get("orderHash") or o.get("sourceTxHash")


def dedupe_orders(rows):
    """One row per order: /swap/trx/<sig> resolves a refund or fulfil tx to the order it belongs to, so
    iterating over an address's Mayan transactions returns the same order more than once."""
    seen, out = set(), []
    for o in rows:
        k = order_key(o)
        if k in seen:
            continue
        seen.add(k); out.append(o)
    return out


def mayan_tx(q):
    """One order by source/fulfil/refund tx. Returns the order dict, {} when not a Mayan swap, None when the lookup failed."""
    o = http(f"{MAYAN}/swap/trx/{q}")
    if o is None:  # outage / 429 exhausted / 401 — not evidence of anything
        return None
    if not isinstance(o, dict) or not (o.get("trader") or o.get("status")):  # {} = HTTP 404
        return {}
    return o


def mayan(*qs):
    """Mayan (Swift / MCTP / Wormhole-based) swaps: orders for one or more txs (de-duplicated by orderId),
    or every order of a trader address."""
    if not qs:
        return None
    q = qs[0]
    if is_tx_ref(q):
        found, failed, missing = [], [], []
        for ref in qs:
            o = mayan_tx(ref)
            if o is None:
                failed.append(ref)
            elif not o:
                missing.append(ref)
            else:
                found.append(o)
        if len(qs) == 1:
            if failed:
                print(f"== Mayan: lookup failed for {q} (see stderr), status unknown")
                return None
            if missing:
                print(f"== Mayan: {q} is not a Mayan swap")
                return None
            print(f"== Mayan order for tx {q}")
            print_mayan_order(found[0])
            return found
        orders = dedupe_orders(found)
        print(f"== Mayan: {len(orders)} orders from {len(qs)} transactions "
              f"({len(found)} resolved, {len(missing)} not Mayan, {len(failed)} lookups failed)")
        for o in orders:
            print_mayan_order(o)
        for line in mayan_summary(orders):
            print(line)
        for trader in sorted({o.get("trader") for o in orders if o.get("trader")}):
            listed = mayan_listing_count(trader)
            print(f"-- listing ?trader={trader}: {'?' if listed is None else listed} orders listed vs "
                  f"{sum(1 for o in orders if o.get('trader') == trader)} found by tx hash"
                  + ("" if listed is None else "  (the difference is blocked/sanctioned orders, which listings never show)"))
        return orders
    rows, offset, listed = [], 0, None
    while True:
        r = http(f"{MAYAN}/swaps?trader={q}&limit={MAYAN_PAGE}&offset={offset}") or {}
        page = r.get("data") or []
        if listed is None:
            listed = (r.get("metadata") or {}).get("count")
        rows += page
        if len(page) < MAYAN_PAGE:
            break
        offset += MAYAN_PAGE
    orders = dedupe_orders(rows)
    print(f"== Mayan orders for trader {q}: {len(orders)} orders from {len(rows)} rows (listing count={listed})  "
          f"(blocked/sanctioned orders never appear in listings — in case 04 the refunded and cancelled ones were all "
          f"blocked; look them up by transaction hash: `mayan <SIG> <SIG> …`)")
    for o in orders:
        print_mayan_order(o)
    for line in mayan_summary(orders):
        print(line)
    return orders


def mayan_listing_count(trader):
    """`metadata.count` of the ?trader= listing (what Mayan shows publicly), None when the lookup failed."""
    r = http(f"{MAYAN}/swaps?trader={trader}&limit=1&offset=0")
    if not isinstance(r, dict):
        return None
    return (r.get("metadata") or {}).get("count")


def mayan_summary(orders):
    """Footer lines: blocked orders, and refunds split by baseline (before / after deadline)."""
    if not orders:
        return []
    lines = []
    blocked = [o for o in orders if o.get("sanctioned") or (o.get("security") or {}).get("code")]
    if blocked:
        lines.append(f"-- blocked by Mayan screening: {len(blocked)}/{len(orders)} orders "
                     f"({', '.join(sorted({(o.get('security') or {}).get('code') or 'sanctioned' for o in blocked}))})")
    refunds = [o for o in orders if is_refund(o)]
    if refunds:
        by = {}
        for o in refunds:
            by.setdefault(refund_baseline(o), []).append(deadline_lag(o))
        parts = []
        for k in ("after deadline", "before deadline", "unknown"):
            lags = [l for l in by.get(k, []) if l is not None]
            if k in by:
                parts.append(f"{k}: {len(by[k])}" + (f" (lag {fmt_lag(min(lags))}–{fmt_lag(max(lags))})" if lags else ""))
        lines.append(f"-- refunds: {len(refunds)}/{len(orders)}  " + "; ".join(parts)
                     + "  — refunds before the deadline are unfillable-at-minAmountOut refunds, not expiries; never pool the two")
    return lines


def relay_requests(params):
    if RELAY:
        r = http(f"{RELAY_API}/v3?{params}", headers={"x-api-key": RELAY})
    else:
        log("Relay: no RELAY_API_KEY → using deprecated /requests/v2 (retires 2026-11-24); set RELAY_API_KEY for v3")
        r = http(f"{RELAY_API}/v2?{params}")
    if r is None:
        return None
    return r.get("requests") or []


def relay(q):
    """Relay (relay.link) cross-chain requests: by deposit/fill tx hash, or every request of a user address."""
    by_user = not is_tx_ref(q)
    reqs = relay_requests(f"hash={q}" if not by_user else f"user={q}")
    if by_user:
        log("Relay: the user= listing is incomplete (known orders were missing from it in case 04) — use it to find "
            "orders, never to say 'no other orders'; prove negatives on chain")
    if reqs is None:
        print(f"== Relay: lookup failed for {q} (see stderr), status unknown")
        return None
    if not reqs:
        print(f"== Relay: no Relay request for {q}")
        return []
    print(f"== Relay requests for {q}: {len(reqs)}")
    for r in reqs:
        d = r.get("data") or {}
        print(f"{(r.get('createdAt') or '')[:19]}  id={r.get('id')}  status={r.get('status')}"
              + (f"  failReason={d.get('failReason') or r.get('failReason')}" if (d.get('failReason') or r.get('failReason')) else ""))
        print(f"      user      {r.get('user')}")
        print(f"      recipient {r.get('recipient')}")
        for k in ("inTxs", "outTxs"):
            for t in (d.get(k) or r.get(k) or []):
                print(f"      {k:<7} chain {t.get('chainId')}  {t.get('hash')}  {t.get('timestamp') or ''}")
    return reqs


COMMANDS = {
    "bridgers": bridgers, "bridgers-order": bridgers_order, "wormhole": wormhole, "debridge": debridge,
    "mayan": mayan, "relay": relay,
    "all": lambda x: (bridgers(x), wormhole(x), mayan(x), relay(x)),
}


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) < 2:
        sys.exit(__doc__)
    cmd, arg = a[0], a[1]
    if cmd == "mayan":
        mayan(*a[1:])
    else:
        COMMANDS.get(cmd, lambda x: sys.exit(__doc__))(arg)
