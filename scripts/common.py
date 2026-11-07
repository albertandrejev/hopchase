"""Shared helpers: HTTP with backoff, env-based API keys, label registry."""
import json, os, sys, time, urllib.request, urllib.error, datetime

HELIUS = os.environ.get("HELIUS_API_KEY", "").strip()
ETHERSCAN = os.environ.get("ETHERSCAN_API_KEY", "").strip()
TRONGRID = os.environ.get("TRONGRID_API_KEY", "").strip()
ANKR = os.environ.get("ANKR_API_KEY", "").strip()      # Solana RPC fallback + EVM eth_call; enable networks per key in the Ankr dashboard
RELAY = os.environ.get("RELAY_API_KEY", "").strip()    # Relay /requests/v3 (v2 is keyless but retires 2026-11-24)

# Solana RPC priority: Helius > Ankr > public.
if HELIUS:
    SOL_RPC = f"https://mainnet.helius-rpc.com/?api-key={HELIUS}"
elif ANKR:
    SOL_RPC = f"https://rpc.ankr.com/solana/{ANKR}"
else:
    SOL_RPC = "https://api.mainnet-beta.solana.com"
SOL_SLEEP = 0.05 if (HELIUS or ANKR) else 0.45

BLOCKSCOUT = {
    "eth": "https://eth.blockscout.com", "base": "https://base.blockscout.com",
    "polygon": "https://polygon.blockscout.com", "arbitrum": "https://arbitrum.blockscout.com",
    "optimism": "https://optimism.blockscout.com", "gnosis": "https://gnosis.blockscout.com",
    "bsc": None,  # no public Blockscout; use etherscan v2 chainid=56 when ETHERSCAN_API_KEY is set
}
ETHERSCAN_CHAINIDS = {"eth": 1, "bsc": 56, "polygon": 137, "base": 8453, "arbitrum": 42161, "optimism": 10, "avalanche": 43114}

USDT_TRON = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"

# Ethereum mainnet stablecoins and their blacklist getters (used by `evm_trace.py freeze`).
USDC_ETH = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
USDT_ETH = "0xdac17f958d2ee523a2206206994597c13d831ec7"
SEL_USDC_IS_BLACKLISTED = "0xfe575a87"  # isBlacklisted(address)
SEL_USDT_IS_BLACKLISTED = "0xe47d6060"  # isBlackListed(address)

SOL_MINTS = {
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": ("USDC", 6),
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB": ("USDT", 6),
    "So11111111111111111111111111111111111111112": ("wSOL", 9),
    "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN": ("JUP", 6),
    "USD1ttGY1N17NEEHLmELoaybftRBUSErhqYiQzvEmuB": ("USD1", 6),
    "2b1kV6DkPAnxd5ixfnxCpjxmKwqjjaYmCZfHsFu24GXo": ("PYUSD", 6),
    "USDSwr9ApdHk5bvJKMjzff41FfuX8bSxdKcR81vTwcA": ("USDS", 6),
    "cbbtcf3aa214zXHbiAZQwf4122FBYbraNdFqgw4iMij": ("cbBTC", 8),
    "7vfCXTUXx5WJV5JADk17DUJ4ksgau7utNKj4b963voxs": ("wETH", 8),
}

# Known Solana wallets (not programs): bridge depositories, payout accounts.
SOL_LABELS = {
    "7uTT8Xi5RWXzy7h9XL244GRgEycDYDhLjr3ZyNdXi8pZ": "BRIDGE:Relay depository",
}

# Mint freeze authorities: who can freeze a token account of that mint (issuer freeze requests go here).
SOL_FREEZE_AUTHORITIES = {
    "7dGbd2QZcCKcTndnHcTL8q7SMVXAkp688NTQYwrRCrar": "Circle (USDC)",
    "Q6XprfkF8RQQKoQVG33xT88H7wi8Uk1B1CC7YAs69Gi": "Tether (USDT)",
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
    "BLZRi6frs4X4DNLw56V4EXai1b6QVESN1BhHBTYM9VcY": "BRIDGE:Mayan Swift",   # Swift v1 program
    "mayan34VedncxdK2XobtvWFDXQASUTBXhUVzt2kKgny": "BRIDGE:Mayan Swift v2",  # SWIFT_V2: the program fulfil txs call (verified live 2026-11-07)
    "CCTPiPYPc6AsJuwueEnWgSgucamXDZwBd53dQ11YiKX3": "BRIDGE:Circle CCTP",
    "CCTPmbSD7gX1bxKPAmg77w8oFzNFpaQiQUWD43TKaecd": "BRIDGE:CCTP transmitter",
    "99vQwtBwYtrqqD9YSXbdum3KBdxPAVxYTaQ3cfnJSrN2": "BRIDGE:Relay",
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
    "0xc38e4e6a15593f908255214653d3d947ca1c2338": "BRIDGE:Mayan Swift",      # MayanSwift: pays out ETH as internal txs
    "0x0654874eb7f59c6f5b39931fc45dc45337c967c3": "BRIDGE:Mayan Forwarder",
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


def redact(url):
    """Replace every configured API key in a URL (query string or path) with *** before logging it."""
    for key in (HELIUS, ANKR, RELAY, ETHERSCAN, TRONGRID):
        if key:
            url = url.replace(key, "***")
    return url


def http(url, data=None, headers=None, tries=8, timeout=30):
    """GET/POST JSON with backoff on 429/5xx. Returns parsed JSON, {} on HTTP 404 (logged), None on other failures."""
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
            log(f"HTTP {e.code} {redact(url).split('?')[0][:80]}")  # query strings and paths can carry API keys
            return {} if e.code == 404 else None
        except Exception as e:  # noqa
            time.sleep(3)
    return None


def sol_rpc(method, params):
    """Solana JSON-RPC call. Returns `result`, or None after logging the RPC error to stderr."""
    for i in range(8):
        r = http(SOL_RPC, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
        if r is None:
            log(f"RPC {method}: no response")
            return None
        if "error" in r:
            if r["error"].get("code") == 429 or "429" in str(r["error"]):
                time.sleep(15)
                continue
            log(f"RPC {method} error: {json.dumps(r['error'], ensure_ascii=False)[:300]}")
            return None
        return r.get("result")
    log(f"RPC {method}: gave up after repeated 429")
    return None


def _jsonrpc(url, method, params):
    """One JSON-RPC call. Returns (result, error); error is a string when the call failed."""
    r = http(url, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    if r is None:
        return None, "no response"
    if "error" in r:
        return None, json.dumps(r["error"], ensure_ascii=False)[:300]
    return r.get("result"), None


def evm_rpc(chain, method, params):
    """EVM JSON-RPC (e.g. eth_call). Ankr with ANKR_API_KEY first; on error (network not enabled for the key,
    no key) falls back to the chain's keyless Blockscout `/api/eth-rpc`. Returns result or None."""
    if ANKR:
        res, err = _jsonrpc(f"https://rpc.ankr.com/{chain}/{ANKR}", method, params)
        if err is None:
            return res
        log(f"Ankr {chain} {method}: {err} → falling back to Blockscout eth-rpc")
    base = BLOCKSCOUT.get(chain)
    if not base:
        log(f"{chain}: no Blockscout eth-rpc endpoint and Ankr unavailable → {method} skipped")
        return None
    res, err = _jsonrpc(f"{base}/api/eth-rpc", method, params)
    if err is not None:
        log(f"Blockscout {chain} {method}: {err}")
        return None
    return res


def ts(unix_s):
    return datetime.datetime.fromtimestamp(unix_s, datetime.UTC).strftime("%Y-%m-%d %H:%M")


def tron_headers():
    return {"TRON-PRO-API-KEY": TRONGRID} if TRONGRID else {}
