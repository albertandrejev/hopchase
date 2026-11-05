"""Shared helpers: HTTP with backoff, env-based API keys, label registry."""
import json, os, sys, time, urllib.request, urllib.error, datetime

HELIUS = os.environ.get("HELIUS_API_KEY", "").strip()
ETHERSCAN = os.environ.get("ETHERSCAN_API_KEY", "").strip()
TRONGRID = os.environ.get("TRONGRID_API_KEY", "").strip()

SOL_RPC = f"https://mainnet.helius-rpc.com/?api-key={HELIUS}" if HELIUS else "https://api.mainnet-beta.solana.com"
SOL_SLEEP = 0.05 if HELIUS else 0.45

BLOCKSCOUT = {
    "eth": "https://eth.blockscout.com", "base": "https://base.blockscout.com",
    "polygon": "https://polygon.blockscout.com", "arbitrum": "https://arbitrum.blockscout.com",
    "optimism": "https://optimism.blockscout.com", "gnosis": "https://gnosis.blockscout.com",
    "bsc": None,  # no public Blockscout; use etherscan v2 chainid=56 when ETHERSCAN_API_KEY is set
}
ETHERSCAN_CHAINIDS = {"eth": 1, "bsc": 56, "polygon": 137, "base": 8453, "arbitrum": 42161, "optimism": 10, "avalanche": 43114}

USDT_TRON = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"

SOL_MINTS = {
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": ("USDC", 6),
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB": ("USDT", 6),
    "So11111111111111111111111111111111111111112": ("wSOL", 9),
    "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN": ("JUP", 6),
}

# Solana program labels. Bridges/aggregators first — these are the exits to watch.
SOL_PROGRAMS = {
    "FDF8AxHB8UK7RS6xay6aBvwS3h7kez9gozqz14JyfKsg": "BRIDGE:Bridgers/SWFT",
    "RangohQxaWip6i1twAAnRVLmob9j88fid7sq2DMAATW": "BRIDGE:Rango",
    "wormDTUJ6AWPNvk59vGQbDvGJmqbDTdgWgAqcLBCgUb": "BRIDGE:Wormhole core",
    "wormqW2zTPwNcDeK7uWpJyq8dqTqJxJzqk8yMquc4A": "BRIDGE:Wormhole token bridge",
    "DEbrdGj3HsRsAzx6uH4MKyREKxVAfBydijLUF3ygsFfh": "BRIDGE:deBridge DLN dst",
    "src5qyZHqTqecJV4aY6Cb6zDZLMDzrDKKezs22MPHr4": "BRIDGE:deBridge DLN src",
    "BrdgN2RPzEMWF96ZbnnJaUtQDQx7VRXYaHHbYCBvceWB": "BRIDGE:Allbridge",
    "FUDEbQKfMTfAaKS3dGdPEacfpLHgXgsxtSgwR9Dn8Pdv": "BRIDGE:Mayan Swift",
    "MAYANM7SwJrGEVmVjYT7hpyjPoP8XoekYU4XXUHXvA": "BRIDGE:Mayan",
    "CCTPiPYPc6AsJuwueEnWgSgucamXDZwBd53dQ11YiKX3": "BRIDGE:Circle CCTP",
    "CCTPmbSD7gX1bxKPAmg77w8oFzNFpaQiQUWD43TKaecd": "BRIDGE:CCTP transmitter",
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4": "DEX:Jupiter v6",
    "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc": "DEX:Orca Whirlpool",
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8": "DEX:Raydium AMM",
    "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK": "DEX:Raydium CLMM",
    "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo": "DEX:Meteora DLMM",
    "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P": "DEX:pump.fun",
    "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr": "Memo",
    "Memo1UhkJRfHyvLMcVucJwxXeuD728EqVDDwQDxFMNo": "Memo v1",
    "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA": "SPL Token",
    "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb": "Token-2022",
    "11111111111111111111111111111111": "System",
    "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL": "ATA",
    "ComputeBudget111111111111111111111111111111": "ComputeBudget",
}

# EVM contracts (lowercase) — bridges/aggregators used by Trust Wallet-style operators.
EVM_CONTRACTS = {
    "0xc1d13492285eb664951e201bf7c80c7c6318a1b5": "BRIDGE:SwftSwap (Bridgers)",
    "0x69460570c93f9de5e2edbc3052bf10125f0ca22d": "BRIDGE:RangoDiamond",
    "0x3ee18b2214aff97000d974cf647e7c347e8fa585": "BRIDGE:Wormhole Portal",
    "0xef4fb24ad0916217251f553c0596f8edc630eb66": "BRIDGE:deBridge DLN",
    "0xbd3fa81b58ba92a82136038b25adec7066af3155": "BRIDGE:CCTP TokenMessenger",
    "0x1231deb6f5749ef6ce6943a275a1d3e7486f4eae": "BRIDGE:LI.FI Diamond",
    "0x6131b5fae19ea4f9d964eac0408e4408b66337b5": "DEX:KyberSwap",
    "0x1111111254eeb25477b68fb85ed929f73a960582": "DEX:1inch v5",
    "0x9008d19f58aabd9ed0d60971565aa8510560ab41": "DEX:CoW GPv2",
    "0xd9e1ce17f2641f24ae83637ab66a2cca9c378b9f": "DEX:SushiSwap",
}
# Addresses are Ethereum mainnet. The same bytecode is often deployed at other addresses on other
# chains — always prefer the `name` Blockscout returns and record the full address from the chain.

TRON_LABELS = {
    "TJ4KeiGTvTX4wRUgLARiwr8rGLaurmVkdZ": "BRIDGE-PAYOUT:SWFT/Bridgers",
    "TX5XiRXdyz7sdFwF5mnhT1QoGCpbkncpke": "BRIDGE-PAYOUT:Rango",
}


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def http(url, data=None, headers=None, tries=8, timeout=30):
    """GET/POST JSON with backoff on 429/5xx. Returns parsed JSON or None."""
    h = {"Content-Type": "application/json", "User-Agent": "hopchase/0.1"}
    if headers:
        h.update(headers)
    body = json.dumps(data).encode() if data is not None else None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, data=body, headers=h)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 502, 503, 504):
                time.sleep(min(60, 5 * (i + 1)))
                continue
            log(f"HTTP {e.code} {url[:80]}")
            return None
        except Exception as e:  # noqa
            time.sleep(3)
    return None


def sol_rpc(method, params):
    for i in range(8):
        r = http(SOL_RPC, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
        if r is None:
            return None
        if "error" in r:
            if r["error"].get("code") == 429 or "429" in str(r["error"]):
                time.sleep(15)
                continue
            return None
        return r.get("result")
    return None


def ts(unix_s):
    return datetime.datetime.fromtimestamp(unix_s, datetime.UTC).strftime("%Y-%m-%d %H:%M")


def tron_headers():
    return {"TRON-PRO-API-KEY": TRONGRID} if TRONGRID else {}
