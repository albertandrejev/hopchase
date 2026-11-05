#!/usr/bin/env python3
"""Cross-chain bridge order lookups (off-chain confirmation of hops). No API keys needed.

Usage:
  bridges.py bridgers <ADDRESS>            # all Bridgers/SWFT orders where ADDRESS is the sender (any chain)
  bridges.py bridgers-order <ORDER_ID>     # one order in full
  bridges.py wormhole <ADDRESS|TXHASH>     # Wormholescan operations
  bridges.py debridge <TXHASH>             # deBridge DLN order ids for a source tx
  bridges.py all <ADDRESS>                 # bridgers + wormhole

Bridgers is the one most often behind Trust Wallet's in-app swap ("source": "trustwallet-prod_...").
"""
import sys, json
from common import http

BR = "https://api.bridgers.xyz/api/exchangeRecord/"


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


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) < 2:
        sys.exit(__doc__)
    cmd, arg = a[0], a[1]
    {"bridgers": bridgers, "bridgers-order": bridgers_order, "wormhole": wormhole, "debridge": debridge,
     "all": lambda x: (bridgers(x), wormhole(x))}.get(cmd, lambda x: sys.exit(__doc__))(arg)
