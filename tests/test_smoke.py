"""Offline smoke tests: no network. Run: python3 -m pytest tests/ or python3 tests/test_smoke.py"""
import contextlib, io, sys, os, json, re, urllib.error
from unittest import mock
ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import sol_trace, common, bridges, evm_trace, recheck

SKILLS = ["trace-funds", "address-profile", "case-report"]
REFERENCES = [
    "skills/trace-funds/references/bridges.md",
    "skills/trace-funds/references/endpoints.md",
    "skills/trace-funds/references/confidence.md",
    "skills/case-report/references/action-pack.md",
]
SCRIPTS = ["sol_trace.py", "evm_trace.py", "tron_trace.py", "bridges.py", "recheck.py", "common.py"]

def test_b58_compute_budget():
    ins = [{"programId": "ComputeBudget111111111111111111111111111111", "data": "HMypLP"},
           {"programId": "ComputeBudget111111111111111111111111111111", "data": "3GAG5eogvTjV"}]
    assert sol_trace.compute_budget(ins) == {"cu_limit": 400000, "cu_price": 10000}

def test_plugin_manifest():
    m = json.load(open(os.path.join(ROOT, ".claude-plugin", "plugin.json")))
    assert m["name"] == "hopchase"

def test_registry_lowercase():
    assert all(k == k.lower() for k in common.EVM_CONTRACTS)

def test_skills_exist_and_named():
    for s in SKILLS:
        path = os.path.join(ROOT, "skills", s, "SKILL.md")
        assert os.path.isfile(path), path
        head = open(path, encoding="utf-8").read(400)
        assert re.search(rf"^name:\s*{re.escape(s)}\s*$", head, re.M), f"frontmatter name != {s} in {path}"

def test_references_and_scripts_exist():
    for r in REFERENCES:
        assert os.path.isfile(os.path.join(ROOT, r)), r
    for s in SCRIPTS:
        assert os.path.isfile(os.path.join(ROOT, "scripts", s)), s

def test_readme_mentions_every_skill_and_script():
    readme = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
    for s in SKILLS:
        assert f"`{s}`" in readme, s
    for s in SCRIPTS:
        if s != "common.py":
            assert s in readme, s

def test_http_error_log_omits_api_key():
    key = "SECRETKEY1234567890"
    urls = [f"https://mainnet.helius-rpc.com/?api-key={key}",
            f"https://api.etherscan.io/v2/api?chainid=1&apikey={key}&address=0xabc"]
    for url in urls:
        err = urllib.error.HTTPError(url, 401, "Unauthorized", None, None)
        stderr = io.StringIO()
        with mock.patch("urllib.request.urlopen", side_effect=err), contextlib.redirect_stderr(stderr):
            assert common.http(url) is None
        logged = stderr.getvalue()
        assert "HTTP 401" in logged, logged
        assert key[:6] not in logged, logged

def test_fmt_amount_uses_tx_decimals():
    usd1 = "USD1ttGY1N17NEEHLmELoaybftRBUSErhqYiQzvEmuB"
    weth = "7vfCXTUXx5WJV5JADk17DUJ4ksgau7utNKj4b963voxs"
    assert sol_trace.fmt_amount(usd1, -7173929438, 6) == "USD1 -7,173.929438"
    assert sol_trace.fmt_amount(weth, -4106158, 8) == "wETH -0.04106158"
    # unknown mint: decimals from the tx balances, not a raw integer
    assert sol_trace.fmt_amount("Unknown1111111111111111111111111111111111111", 1500000, 6) == "Unknow… +1.5"
    # unknown mint and no decimals anywhere: raw integer
    assert sol_trace.fmt_amount("Unknown1111111111111111111111111111111111111", 1500000) == "Unknow… +1,500,000"
    # registry decimals still apply when the tx carries none
    assert sol_trace.fmt_amount("EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", 90500000000) == "USDC +90,500"

def test_summarize_keeps_decimals_and_signers():
    t = {"slot": 1, "blockTime": 1700000000,
         "meta": {"err": None, "preBalances": [10**9, 0], "postBalances": [10**9 - 5000, 0], "logMessages": [],
                  "preTokenBalances": [{"owner": "W", "mint": "M", "uiTokenAmount": {"amount": "100", "decimals": 2}}],
                  "postTokenBalances": [{"owner": "W", "mint": "M", "uiTokenAmount": {"amount": "0", "decimals": 2}}]},
         "transaction": {"signatures": ["S"], "message": {
             "accountKeys": [{"pubkey": "K", "signer": True}, {"pubkey": "L", "signer": False, "source": "lookupTable"}],
             "instructions": []}}}
    s = sol_trace.summarize(t)
    assert s["signers"] == ["K"]
    assert s["token_deltas"] == [{"owner": "W", "mint": "M", "raw": -100, "decimals": 2}]

def test_signer_footer_flags_program_controlled_account():
    rows = [{"signers": ["Ctrl"], "cu": {"cu_limit": 400000, "cu_price": 10000}} for _ in range(3)]
    lines = sol_trace.signer_footer("Wallet", rows)
    assert lines[0].startswith("-- signers (3 txs; wallet itself signed 0)")
    assert "program-controlled deposit account? (or a token account: run history on its owner)" in lines[0]
    assert "Ctrl 100% (3 txs)" in lines[1] and "(400000,10000)x3" in lines[1]
    # a self-signing wallet is not flagged
    rows = [{"signers": ["Wallet"], "cu": {}}, {"signers": ["Other"], "cu": {}}]
    lines = sol_trace.signer_footer("Wallet", rows)
    assert not any("program-controlled" in l for l in lines)
    assert sol_trace.signer_footer("Wallet", []) == []

def test_bridge_commands_registered():
    for cmd in ("bridgers", "bridgers-order", "wormhole", "debridge", "mayan", "relay", "all"):
        assert cmd in bridges.COMMANDS, cmd
        assert f"bridges.py {cmd}" in bridges.__doc__, cmd
    sig = "3TdFvsLZe13f2HwZ54KuaHn5n8WgmoJJN2L4tbMyvcnKhaYEnYVHNsXXzrc8utmx4kU73zjtNgHh9Uuxiotk6J2F"
    assert bridges.is_tx_ref(sig) and bridges.is_tx_ref("0x" + "ab" * 32)
    assert not bridges.is_tx_ref("A9a6xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx1") and not bridges.is_tx_ref("0x" + "ab" * 20)

def test_relay_without_key_uses_v2_with_warning():
    stderr = io.StringIO()
    with mock.patch.object(bridges, "RELAY", ""), mock.patch.object(bridges, "http", return_value={"requests": []}) as h, \
         contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(io.StringIO()):
        assert bridges.relay("0x" + "ab" * 32) == []
    assert "/requests/v2?hash=0x" in h.call_args[0][0]
    assert "2026-11-24" in stderr.getvalue()
    with mock.patch.object(bridges, "RELAY", "k"), mock.patch.object(bridges, "http", return_value=None) as h, \
         contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        bridges.relay("0xUser")
    assert "/requests/v3?user=0xUser" in h.call_args[0][0] and h.call_args[1]["headers"] == {"x-api-key": "k"}

def test_sol_rpc_logs_error():
    stderr = io.StringIO()
    err = {"jsonrpc": "2.0", "id": 1, "error": {"code": -32015, "message": "Transaction version (0) is not supported"}}
    with mock.patch.object(common, "http", return_value=err), contextlib.redirect_stderr(stderr):
        assert common.sol_rpc("getTransaction", ["sig"]) is None
    assert "getTransaction" in stderr.getvalue() and "not supported" in stderr.getvalue()

def test_get_tx_requests_version_1():
    with mock.patch.object(sol_trace, "sol_rpc", return_value=None) as r:
        sol_trace.get_tx("sig")
    assert r.call_args[0][1][1]["maxSupportedTransactionVersion"] == 1

def test_evm_rpc_falls_back_to_blockscout():
    calls = []
    def fake_http(url, data=None, headers=None, **kw):
        calls.append(url)
        if "rpc.ankr.com" in url:
            return {"jsonrpc": "2.0", "id": 1, "error": {"code": -32600, "message": "network not enabled"}}
        return {"jsonrpc": "2.0", "id": 1, "result": "0x" + "0" * 63 + "1"}
    with mock.patch.object(common, "ANKR", "key"), mock.patch.object(common, "http", side_effect=fake_http), \
         contextlib.redirect_stderr(io.StringIO()):
        assert common.evm_rpc("eth", "eth_call", [{}, "latest"]) == "0x" + "0" * 63 + "1"
    assert calls[0].startswith("https://rpc.ankr.com/eth/") and calls[1] == "https://eth.blockscout.com/api/eth-rpc"
    with mock.patch.object(common, "ANKR", ""), mock.patch.object(common, "http", side_effect=fake_http), \
         contextlib.redirect_stderr(io.StringIO()):
        assert common.evm_rpc("bsc", "eth_call", [{}, "latest"]) is None  # no Blockscout, no Ankr

def test_evm_freeze_calldata_and_decode():
    data = evm_trace.blacklist_calldata(common.SEL_USDT_IS_BLACKLISTED, "0x" + "0" * 39 + "1")
    assert data == "0xe47d6060" + "0" * 63 + "1" and len(data) == 2 + 8 + 64
    assert evm_trace.decode_bool("0x" + "0" * 63 + "1") is True
    assert evm_trace.decode_bool("0x" + "0" * 64) is False
    assert evm_trace.decode_bool(None) is None
    stdout = io.StringIO()
    with mock.patch.object(evm_trace, "evm_rpc", return_value=None), contextlib.redirect_stdout(stdout):
        evm_trace.freeze("0x" + "0" * 39 + "1", "eth")
    assert "USDC isBlacklisted: ?" in stdout.getvalue() and "USDT isBlackListed: ?" in stdout.getvalue()

def test_recheck_freeze_line_handles_rpc_none():
    with mock.patch.object(recheck, "sol_rpc", return_value=None), contextlib.redirect_stderr(io.StringIO()):
        assert recheck.freeze_line("TA").endswith("state=?")
    info = {"state": "frozen", "mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"}
    assert recheck.freeze_line("TA", info) == "   freeze TA: state=frozen USDC"
    assert "escrows" in recheck.__doc__

def test_new_registry_entries():
    assert common.SOL_MINTS["USD1ttGY1N17NEEHLmELoaybftRBUSErhqYiQzvEmuB"] == ("USD1", 6)
    assert common.SOL_PROGRAMS["99vQwtBwYtrqqD9YSXbdum3KBdxPAVxYTaQ3cfnJSrN2"] == "BRIDGE:Relay"
    assert "7uTT8Xi5RWXzy7h9XL244GRgEycDYDhLjr3ZyNdXi8pZ" in common.SOL_LABELS
    assert common.USDC_ETH == common.USDC_ETH.lower() and common.USDT_ETH == common.USDT_ETH.lower()

def test_docs_mention_new_env_vars_and_commands():
    readme = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
    env = open(os.path.join(ROOT, ".env.example"), encoding="utf-8").read()
    for var in ("ANKR_API_KEY", "RELAY_API_KEY"):
        assert var in readme and var in env, var
    for s in ("trace-funds", "address-profile"):
        skill = open(os.path.join(ROOT, "skills", s, "SKILL.md"), encoding="utf-8").read()
        assert "ANKR_API_KEY" in skill and "RELAY_API_KEY" in skill and "freeze" in skill, s
        assert "CLAUDE_PLUGIN_ROOT" in skill and "scripts/` folder next to" in skill, s
    bridges_md = open(os.path.join(ROOT, "skills/trace-funds/references/bridges.md"), encoding="utf-8").read()
    assert "explorer-api.mayan.finance" in bridges_md and "api.relay.link" in bridges_md

def test_mayan_single_order_and_not_found():
    order = {"trader": "T", "destAddress": "0xD", "fromAmount": "1", "toAmount": "0.9", "status": "ORDER_UNLOCKED",
             "sourceTxHash": "S", "fulfillTxHash": "F", "refundTxHash": "F", "stateAddr": "ST", "sourceStateAddr": "SS",
             "initiatedAt": "2026-11-06T23:32:36.000Z", "fromTokenSymbol": "USDT", "toTokenSymbol": "USDT"}
    sig = "3TdFvsLZe13f2HwZ54KuaHn5n8WgmoJJN2L4tbMyvcnKhaYEnYVHNsXXzrc8utmx4kU73zjtNgHh9Uuxiotk6J2F"
    out = io.StringIO()
    with mock.patch.object(bridges, "http", return_value=order) as h, contextlib.redirect_stdout(out):
        assert bridges.mayan(sig) == [order]
    assert h.call_args[0][0].endswith(f"/v3/swap/trx/{sig}")
    text = out.getvalue()
    assert "stateAddr   ST" in text and "sourceStateAddr SS" in text and "destAddress 0xD" in text
    assert "REFUND" not in text  # refundTxHash echoing fulfillTxHash is not a refund
    out = io.StringIO()
    with mock.patch.object(bridges, "http", return_value=None), contextlib.redirect_stdout(out):
        assert bridges.mayan(sig) is None
    assert "lookup failed" in out.getvalue() and "not a Mayan swap" not in out.getvalue()
    out = io.StringIO()
    with mock.patch.object(bridges, "http", return_value={}), contextlib.redirect_stdout(out):  # HTTP 404 → {}
        assert bridges.mayan(sig) is None
    assert "not a Mayan swap" in out.getvalue()
    # trader listing pages with limit 50 and stops on a short page
    with mock.patch.object(bridges, "http", return_value={"data": [order]}) as h, contextlib.redirect_stdout(io.StringIO()):
        assert bridges.mayan("4LkEyP9JzG2T3ttceaHhpCqLWrgm7oCPEkjzLdzLjNYJ") == [order]
    assert "limit=50&offset=0" in h.call_args[0][0]

def test_evm_internal_txs_listed_and_counted_as_exit():
    base = "https://eth.blockscout.com/api/v2/addresses/0xabc"
    itx = {"value": str(251 * 10**18), "timestamp": "2026-10-01T10:00:00.000000Z", "transaction_hash": "0x" + "1" * 64,
           "success": True, "from": {"hash": "0xSwift", "name": "SwiftDest"}, "to": {"hash": "0xabc"}}
    def fake_http(url, *a, **k):
        if url == base:
            return {"coin_balance": "0"}
        if url.endswith("/internal-transactions"):
            return {"items": [itx, dict(itx, value="0")]}
        return {"items": []}
    out = io.StringIO()
    with mock.patch.object(evm_trace, "http", side_effect=fake_http), contextlib.redirect_stdout(out):
        assert evm_trace.blockscout("0xabc", "eth")
    text = out.getvalue()
    assert "-- internal txs (value > 0) (1 shown)" in text and "SwiftDest" in text and "251.000000" in text
    assert "exits used: PAYOUT:SwiftDest" in text
    # missing endpoint → 0 shown, no crash
    out = io.StringIO()
    with mock.patch.object(evm_trace, "http", return_value=None), contextlib.redirect_stdout(out):
        evm_trace.blockscout("0xabc", "eth")
    assert "-- internal txs (value > 0) (0 shown)" in out.getvalue()

def test_sol_freeze_states_and_rpc_none():
    usdc = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    acct = {"value": {"data": {"parsed": {"type": "account", "info": {"state": "frozen", "mint": usdc,
                                                                      "tokenAmount": {"uiAmountString": "232875"}}}}}}
    mint = {"value": {"data": {"parsed": {"type": "mint", "info": {"decimals": 6, "freezeAuthority": "Circle1"}}}}}
    def fake_rpc(method, params):
        return acct if params[0] == "TA" else mint
    out = io.StringIO()
    with mock.patch.object(sol_trace, "sol_rpc", side_effect=fake_rpc), contextlib.redirect_stdout(out):
        sol_trace.cmd_freeze("TA")
    assert "state=frozen" in out.getvalue() and "USDC" in out.getvalue() and "freezeAuthority=Circle1" in out.getvalue()
    out, err = io.StringIO(), io.StringIO()
    with mock.patch.object(sol_trace, "sol_rpc", return_value=None), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        sol_trace.cmd_freeze("TA")
    assert "state=?" in out.getvalue() and "RPC error" in err.getvalue()

def test_recheck_escrows_survive_rpc_none(tmp_path=None):
    import tempfile
    case = {"solana": {"wallets": ["W"], "token_accounts": ["TA"], "escrows": ["E"]}}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(case, f)
    out = io.StringIO()
    with mock.patch.object(recheck, "sol_rpc", return_value=None), mock.patch.object(recheck, "SOL_SLEEP", 0), \
         contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        recheck.main(f.name)
    os.unlink(f.name)
    text = out.getvalue()
    assert "SOL token acct TA: ?" in text and "freeze TA: state=?" in text
    assert "SOL escrow E: SOL ?" in text and "token accounts (Tokenkeg…): ?" in text and "SOL latest E: ?" in text

def test_http_error_log_omits_path_embedded_key_and_404_returns_empty():
    key = "ANKRSECRET9876543210"
    url = f"https://rpc.ankr.com/solana/{key}"
    err = urllib.error.HTTPError(url, 403, "Forbidden", None, None)
    stderr = io.StringIO()
    with mock.patch.object(common, "ANKR", key), mock.patch("urllib.request.urlopen", side_effect=err), \
         contextlib.redirect_stderr(stderr):
        assert common.http(url) is None
        assert common.redact(f"https://x/?api-key={key}&a=1") == "https://x/?api-key=***&a=1"
    assert "HTTP 403" in stderr.getvalue() and key[:6] not in stderr.getvalue() and "***" in stderr.getvalue()
    nf = urllib.error.HTTPError("https://explorer-api.mayan.finance/v3/swap/trx/abc", 404, "Not Found", None, None)
    with mock.patch("urllib.request.urlopen", side_effect=nf), contextlib.redirect_stderr(io.StringIO()):
        assert common.http("https://explorer-api.mayan.finance/v3/swap/trx/abc") == {}

def test_sol_rpc_priority_from_env():
    import subprocess
    base = {k: v for k, v in os.environ.items() if not k.endswith("_API_KEY")}
    code = "import common; print(common.SOL_RPC, common.SOL_SLEEP)"
    def run(**keys):
        r = subprocess.run([sys.executable, "-c", code], cwd=os.path.join(ROOT, "scripts"), env={**base, **keys},
                           capture_output=True, text=True, check=True)
        return r.stdout.strip()
    assert run(HELIUS_API_KEY="h", ANKR_API_KEY="a") == "https://mainnet.helius-rpc.com/?api-key=h 0.05"
    assert run(HELIUS_API_KEY="h") == "https://mainnet.helius-rpc.com/?api-key=h 0.05"
    assert run(ANKR_API_KEY="a") == "https://rpc.ankr.com/solana/a 0.05"
    assert run() == "https://api.mainnet-beta.solana.com 0.45"

def test_evm_rpc_ankr_success_single_call():
    with mock.patch.object(common, "ANKR", "key"), \
         mock.patch.object(common, "http", return_value={"jsonrpc": "2.0", "id": 1, "result": "0x01"}) as h:
        assert common.evm_rpc("eth", "eth_call", [{}, "latest"]) == "0x01"
    assert h.call_count == 1 and h.call_args[0][0] == "https://rpc.ankr.com/eth/key"

def test_evm_freeze_decodes_per_token():
    def fake_rpc(chain, method, params):
        call = params[0]
        assert chain == "eth" and method == "eth_call" and call["data"].endswith("0" * 63 + "1")
        if call["to"] == common.USDC_ETH:
            assert call["data"].startswith(common.SEL_USDC_IS_BLACKLISTED); return "0x" + "0" * 63 + "1"
        assert call["to"] == common.USDT_ETH and call["data"].startswith(common.SEL_USDT_IS_BLACKLISTED)
        return "0x" + "0" * 64
    out = io.StringIO()
    with mock.patch.object(evm_trace, "evm_rpc", side_effect=fake_rpc), contextlib.redirect_stdout(out):
        evm_trace.freeze("0x" + "0" * 39 + "1", "eth")
    assert "USDC isBlacklisted: YES" in out.getvalue() and "USDT isBlackListed: no" in out.getvalue()

def test_bridges_all_runs_every_lookup_once():
    with mock.patch.object(bridges, "bridgers") as b, mock.patch.object(bridges, "wormhole") as w, \
         mock.patch.object(bridges, "mayan") as m, mock.patch.object(bridges, "relay") as r:
        bridges.COMMANDS["all"]("X")
    for f in (b, w, m, r):
        f.assert_called_once_with("X")

def test_mayan_trader_paging():
    page1 = [{"trader": "T", "status": "ORDER_UNLOCKED", "orderId": f"o{i}"} for i in range(50)]
    with mock.patch.object(bridges, "http", side_effect=[{"data": page1}, {"data": [{"trader": "T", "orderId": "o50"}]}]) as h, \
         contextlib.redirect_stdout(io.StringIO()):
        rows = bridges.mayan("4LkEyP9JzG2T3ttceaHhpCqLWrgm7oCPEkjzLdzLjNYJ")
    assert len(rows) == 51 and h.call_count == 2
    assert "limit=50&offset=0" in h.call_args_list[0][0][0] and "limit=50&offset=50" in h.call_args_list[1][0][0]

def test_relay_prints_request_and_distinguishes_failure():
    req = {"id": "r1", "status": "success", "user": "0xU", "recipient": "0xR", "createdAt": "2026-11-06T23:32:36.000Z",
           "data": {"inTxs": [{"chainId": 1, "hash": "0xIN", "timestamp": 1}], "outTxs": [{"chainId": 8453, "hash": "0xOUT"}]}}
    out = io.StringIO()
    with mock.patch.object(bridges, "RELAY", "k"), mock.patch.object(bridges, "http", return_value={"requests": [req]}), \
         contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        assert bridges.relay("0xU") == [req]
    text = out.getvalue()
    assert "status=success" in text and "recipient 0xR" in text
    assert "inTxs   chain 1  0xIN" in text and "outTxs  chain 8453  0xOUT" in text
    out = io.StringIO()
    with mock.patch.object(bridges, "RELAY", "k"), mock.patch.object(bridges, "http", return_value=None), \
         contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        assert bridges.relay("0xU") is None
    assert "lookup failed" in out.getvalue() and "no Relay request" not in out.getvalue()

def _summary(**kw):
    s = {"sig": "S", "time": "2026-11-06 23:32", "unix": 0, "slot": 1, "ok": True, "signers": ["K1", "K2"],
         "programs": [], "token_deltas": [], "sol_deltas": [], "cu": {}, "memo": None}
    s.update(kw); return s

def test_print_summary_labels_and_signers_flag():
    usdc = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    s = _summary(token_deltas=[{"owner": "7uTT8Xi5RWXzy7h9XL244GRgEycDYDhLjr3ZyNdXi8pZ", "mint": usdc, "raw": 5000000, "decimals": 6}])
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        sol_trace.print_summary(s)
    assert "[BRIDGE:Relay depository]" in out.getvalue() and "USDC +5" in out.getvalue() and "signers: K1, K2" in out.getvalue()
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        sol_trace.print_summary(s, signers=False)
    assert "signers:" not in out.getvalue()

def _tx_fixture(sig):
    return {"slot": 1, "blockTime": 1700000000,
            "meta": {"err": None, "preBalances": [10**9], "postBalances": [10**9], "logMessages": [],
                     "preTokenBalances": [], "postTokenBalances": []},
            "transaction": {"signatures": [sig], "message": {"accountKeys": [{"pubkey": "Ctrl", "signer": True}],
                                                              "instructions": []}}}

def test_cmd_history_respects_cap_and_prints_footer():
    def fake_rpc(method, params):
        if method == "getSignaturesForAddress":
            return [{"signature": f"sig{i}", "blockTime": 1700000000 + i, "err": None} for i in range(1000)]
        if method == "getTransaction":
            return _tx_fixture(params[0])
        raise AssertionError(method)
    for as_json in (False, True):
        out = io.StringIO()
        with mock.patch.object(sol_trace, "sol_rpc", side_effect=fake_rpc) as r, mock.patch.object(sol_trace, "SOL_SLEEP", 0), \
             contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            sol_trace.cmd_history("W", 300, as_json)
        assert sum(1 for c in r.call_args_list if c[0][0] == "getTransaction") == 300
        if as_json:
            rows = json.loads(out.getvalue())
            assert len(rows) == 300 and "-- signers" not in out.getvalue()
        else:
            assert "-- signers (300 txs; wallet itself signed 0)" in out.getvalue() and "Ctrl 100% (300 txs)" in out.getvalue()

def test_cmd_freeze_wallet_target_and_empty_wallet():
    usdc = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    info = {"state": "initialized", "mint": usdc, "tokenAmount": {"uiAmountString": "12.5"}}
    def fake_rpc(method, params):
        if method == "getAccountInfo":
            if params[0] == "W":
                return {"value": {"data": ["", "base64"], "owner": "11111111111111111111111111111111"}}
            return {"value": {"data": {"parsed": {"type": "mint", "info": {"decimals": 6}}}}}
        if method == "getTokenAccountsByOwner":
            if params[1]["programId"].startswith("Tokenkeg"):
                return {"value": [{"pubkey": "TA1", "account": {"data": {"parsed": {"type": "account", "info": info}}}}]}
            return {"value": []}
        raise AssertionError(method)
    out = io.StringIO()
    with mock.patch.object(sol_trace, "sol_rpc", side_effect=fake_rpc), contextlib.redirect_stdout(out):
        sol_trace.cmd_freeze("W")
    text = out.getvalue()
    assert text.startswith("TA1  state=initialized") and "USDC" in text and "freezeAuthority=none" in text
    def empty_rpc(method, params):
        return {"value": {"data": ["", "base64"]}} if method == "getAccountInfo" else {"value": []}
    out = io.StringIO()
    with mock.patch.object(sol_trace, "sol_rpc", side_effect=empty_rpc), contextlib.redirect_stdout(out):
        sol_trace.cmd_freeze("W")
    assert "W: no token accounts" in out.getvalue()

def test_cmd_freeze_labels_known_freeze_authority():
    usdt = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"
    acct = {"value": {"data": {"parsed": {"type": "account", "info": {"state": "initialized", "mint": usdt, "tokenAmount": {"uiAmountString": "1"}}}}}}
    mint = {"value": {"data": {"parsed": {"type": "mint", "info": {"freezeAuthority": "Q6XprfkF8RQQKoQVG33xT88H7wi8Uk1B1CC7YAs69Gi"}}}}}
    out = io.StringIO()
    with mock.patch.object(sol_trace, "sol_rpc", side_effect=lambda m, p: acct if p[0] == "TA" else mint), contextlib.redirect_stdout(out):
        sol_trace.cmd_freeze("TA")
    assert "freezeAuthority=Q6XprfkF8RQQKoQVG33xT88H7wi8Uk1B1CC7YAs69Gi [Tether (USDT)]" in out.getvalue()

def test_recheck_escrow_happy_path_and_closed_account():
    import tempfile
    usdc = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    info = {"state": "initialized", "mint": usdc, "tokenAmount": {"uiAmountString": "100"}}
    def fake_rpc(method, params):
        if method == "getBalance":
            return {"value": 500000000}
        if method == "getTokenAccountsByOwner":
            if params[1]["programId"].startswith("Tokenkeg"):
                return {"value": [{"pubkey": "TA1", "account": {"data": {"parsed": {"info": info}}}}]}
            return {"value": []}
        if method == "getSignaturesForAddress":
            return [{"signature": "s" * 30, "err": None}]  # no blockTime
        raise AssertionError(method)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump({"solana": {"escrows": ["E"]}}, f)
    out = io.StringIO()
    with mock.patch.object(recheck, "sol_rpc", side_effect=fake_rpc), mock.patch.object(recheck, "SOL_SLEEP", 0), \
         contextlib.redirect_stdout(out):
        recheck.main(f.name)
    os.unlink(f.name)
    text = out.getvalue()
    assert "SOL escrow E: SOL 0.500000" in text and "TA1  USDC" in text
    assert "freeze TA1: state=initialized USDC" in text and "\n   ? ssssssss" in text
    with mock.patch.object(recheck, "sol_rpc", return_value={"value": None}):  # closed account
        assert recheck.freeze_line("TA") == "   freeze TA: closed / not a token account"

def test_evm_internal_tx_from_registry_bridge_is_bridge_exit():
    base = "https://eth.blockscout.com/api/v2/addresses/0xabc"
    swift = "0xc38e4e6a15593f908255214653d3d947ca1c2338"
    itx = {"value": str(10**18), "timestamp": "2026-10-01T10:00:00.000000Z", "transaction_hash": "0x" + "1" * 64,
           "success": True, "from": {"hash": swift, "name": None}, "to": {"hash": "0xabc"}}
    ntx = {"timestamp": "2026-10-01T10:00:00.000000Z", "hash": "0x" + "2" * 64, "from": {"hash": "0xabc"}, "to": None,
           "value": "0", "method": None}
    def fake_http(url, *a, **k):
        if url == base:
            return {"coin_balance": "0"}
        if url.endswith("/transactions"):
            return {"items": [ntx]}
        if url.endswith("/internal-transactions"):
            return {"items": [itx]}
        return {"items": []}
    out = io.StringIO()
    with mock.patch.object(evm_trace, "http", side_effect=fake_http), contextlib.redirect_stdout(out):
        evm_trace.blockscout("0xabc", "eth")
    text = out.getvalue()
    assert "exits used: BRIDGE:Mayan Swift" in text and "PAYOUT:" not in text

def _row(unix, signers, deltas, programs=("SPL Token",), sol=(), memos=()):
    return {"unix": unix, "time": "t", "sig": "S", "ok": True, "slot": 1, "signers": list(signers), "cu": {},
            "programs": list(programs), "memo": memos[0] if memos else None, "memos": list(memos),
            "token_deltas": [{"owner": o, "mint": m, "raw": r, "decimals": 6} for o, m, r in deltas],
            "sol_deltas": [{"account": a, "lamports": l} for a, l in sol]}

def test_on_curve_signers_true_pdas_false():
    # a key that signed a transaction on mainnet must be on-curve; the System program (y = 0) is on-curve too
    assert sol_trace.on_curve("6djZ6yZCQqh8LpxX4TbU8U5rBLDLb58vidugJ93Moiw1")
    assert sol_trace.on_curve("11111111111111111111111111111111")
    # 32 x 0xff decodes to y = 2^255 - 1 >= p: never a valid point
    assert not sol_trace.on_curve("JEKNVnkbo3jma5nREBBJCDoXFVeKkD56V3xKrvRmWxFG")
    # Mayan order state accounts are PDAs
    assert not sol_trace.on_curve("GLj1kJJ1TnAvu8eT6ZJAwxM8arU9fjgjtW65bzt4uCus")
    assert "OFF-CURVE" in sol_trace.curve_label("GLj1kJJ1TnAvu8eT6ZJAwxM8arU9fjgjtW65bzt4uCus")
    assert "on-curve" in sol_trace.curve_label("6djZ6yZCQqh8LpxX4TbU8U5rBLDLb58vidugJ93Moiw1")

def test_summarize_collects_memos_from_parsed_instructions():
    memo_pid = "MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr"
    t = {"slot": 1, "blockTime": 1700000000,
         "meta": {"err": None, "preBalances": [1], "postBalances": [1], "logMessages": ["Program log: Memo (len 5): ignored"],
                  "preTokenBalances": [], "postTokenBalances": [],
                  "innerInstructions": [{"index": 0, "instructions": [{"programId": memo_pid, "parsed": "inner note"}]}]},
         "transaction": {"signatures": ["S"], "message": {"accountKeys": [{"pubkey": "K", "signer": True}],
             "instructions": [{"programId": memo_pid, "parsed": "RETURN THE FUNDS, 10% bounty"}]}}}
    s = sol_trace.summarize(t)
    assert s["memos"] == ["RETURN THE FUNDS, 10% bounty", "inner note"] and s["memo"].startswith("RETURN")
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        sol_trace.print_summary(s)
    assert "memo(data, not fact)" in out.getvalue() and "bounty" in out.getvalue()
    # log fallback when no parsed memo instruction exists
    t["transaction"]["message"]["instructions"] = []; t["meta"]["innerInstructions"] = []
    assert sol_trace.summarize(t)["memos"] == ["Memo (len 5): ignored"]

def test_print_summary_flags_co_signed():
    s = _row(1, ["A", "B"], [])
    s["time"] = "2026-01-01 00:00"
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        sol_trace.print_summary(s)
    assert "[CO-SIGNED]" in out.getvalue()
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        sol_trace.print_summary(_row(1, ["A"], []) | {"time": "x"})
    assert "[CO-SIGNED]" not in out.getvalue()

def test_activity_footer_programs_recipients_lots_sweeps_cosigned():
    usdt = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"
    W, T, V = "Wallet", "Treasury", "Victim"
    rows = [_row(100, [V], [(V, usdt, -20_000_000), (W, usdt, 20_000_000)], programs=["King7ki"])]
    rows.append(_row(103, [W], [(W, usdt, -20_000_000), (T, usdt, 20_000_000)], programs=["SPL Token"]))  # swept in 3 s
    for i in range(3):
        rows.append(_row(200 + i, [W], [(W, usdt, -20_000_000), (T, usdt, 20_000_000)], programs=["DEX:Jupiter v6"]))
    rows.append(_row(300, [W, T], [], programs=["System"], sol=[(W, -5_000_000_000), (T, 5_000_000_000)]))
    lines = "\n".join(sol_trace.activity_footer(W, rows))
    assert "-- programs:" in lines and "King7ki 1/6" in lines and "DEX:Jupiter v6 3/6" in lines
    assert "-- top value recipients" in lines and f"{T} USDT 80.0000" in lines and f"{T} SOL 5.0000" in lines
    assert "-- outgoing lots USDT: 20 ×4" in lines
    assert "-- sweep loop: 1 inbound deposits forwarded out within ≤3 s (signer Wallet)" in lines
    assert "-- co-signed transactions: 1/6" in lines
    assert sol_trace.activity_footer(W, []) == []
    # a deposit forwarded after the window is not a sweep
    rows2 = [_row(100, [V], [(W, usdt, 1)]), _row(100 + sol_trace.SWEEP_WINDOW_S + 1, [W], [(W, usdt, -1)])]
    assert not any("sweep loop" in l for l in sol_trace.activity_footer(W, rows2))

def test_cmd_history_prints_curve_header_and_activity_footer():
    sigs = [{"signature": f"S{i}", "blockTime": 1700000000 + i} for i in range(3)]
    tx = {"slot": 1, "blockTime": 1700000000,
          "meta": {"err": None, "preBalances": [1], "postBalances": [1], "logMessages": [], "preTokenBalances": [], "postTokenBalances": []},
          "transaction": {"signatures": ["S"], "message": {"accountKeys": [{"pubkey": "K", "signer": True}], "instructions": []}}}
    def fake_rpc(method, params):
        return sigs if method == "getSignaturesForAddress" else tx
    out = io.StringIO()
    with mock.patch.object(sol_trace, "sol_rpc", side_effect=fake_rpc), mock.patch.object(sol_trace, "SOL_SLEEP", 0), \
         contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        sol_trace.cmd_history("GLj1kJJ1TnAvu8eT6ZJAwxM8arU9fjgjtW65bzt4uCus", 10, False)
    text = out.getvalue()
    assert text.startswith("== GLj1kJJ1TnAvu8eT6ZJAwxM8arU9fjgjtW65bzt4uCus  OFF-CURVE")
    assert "-- signers (3 txs; wallet itself signed 0)" in text and "-- programs:" in text

def test_mayan_multi_tx_dedupes_by_order_id():
    sig = "3TdFvsLZe13f2HwZ54KuaHn5n8WgmoJJN2L4tbMyvcnKhaYEnYVHNsXXzrc8utmx4kU73zjtNgHh9Uuxiotk6J2F"
    o1 = {"orderId": "A", "trader": "T", "status": "ORDER_REFUNDED"}
    o2 = {"orderId": "B", "trader": "T", "status": "ORDER_UNLOCKED"}
    # deposit + refund tx of order A, order B, a non-Mayan tx, one failed lookup, then the ?trader= listing count
    answers = iter([o1, o1, o2, {}, None, {"metadata": {"count": 1}, "data": [o2]}])
    out = io.StringIO()
    with mock.patch.object(bridges, "http", side_effect=lambda *a, **k: next(answers)), contextlib.redirect_stdout(out):
        orders = bridges.mayan(sig, sig, sig, sig, sig)
    assert [o["orderId"] for o in orders] == ["A", "B"]
    assert "== Mayan: 2 orders from 5 transactions (3 resolved, 1 not Mayan, 1 lookups failed)" in out.getvalue()
    assert "-- listing ?trader=T: 1 orders listed vs 2 found by tx hash" in out.getvalue()
    # trader listing is de-duplicated too
    with mock.patch.object(bridges, "http", return_value={"data": [o1, o1]}), contextlib.redirect_stdout(out):
        assert len(bridges.mayan("4LkEyP9JzG2T3ttceaHhpCqLWrgm7oCPEkjzLdzLjNYJ")) == 1
    assert "1 orders from 2 rows" in out.getvalue()

def test_relay_user_listing_warns_incomplete():
    err = io.StringIO()
    with mock.patch.object(bridges, "RELAY", "k"), mock.patch.object(bridges, "http", return_value={"requests": []}), \
         contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
        bridges.relay("0xUser")
    assert "incomplete" in err.getvalue() and "prove negatives on chain" in err.getvalue()

def test_evm_calldata_text():
    msg = "we know who you are, return 90% and keep the rest"
    assert evm_trace.calldata_text("0x" + msg.encode().hex()) == msg
    assert evm_trace.calldata_text("0x") is None and evm_trace.calldata_text(None) is None
    assert evm_trace.calldata_text("0xa9059cbb" + "00" * 64) is None  # ERC-20 transfer selector, not text
    base = "https://eth.blockscout.com/api/v2/addresses/0xabc"
    tx = {"timestamp": "2026-10-01T10:00:00.000000Z", "hash": "0x" + "2" * 64, "from": {"hash": "0xOperator"},
          "to": {"hash": "0xabc", "is_contract": False}, "value": "1", "method": None, "raw_input": "0x" + msg.encode().hex()}
    def fake_http(url, *a, **k):
        if url == base:
            return {"coin_balance": "0"}
        return {"items": [tx]} if url.endswith("/transactions") else {"items": []}
    out = io.StringIO()
    with mock.patch.object(evm_trace, "http", side_effect=fake_http), contextlib.redirect_stdout(out):
        evm_trace.blockscout("0xabc", "eth")
    assert "calldata(data, not fact)" in out.getvalue() and "return 90%" in out.getvalue()

def test_docs_mention_second_pass_items():
    tf = open(os.path.join(ROOT, "skills/trace-funds/SKILL.md"), encoding="utf-8").read()
    ap = open(os.path.join(ROOT, "skills/address-profile/SKILL.md"), encoding="utf-8").read()
    conf = open(os.path.join(ROOT, "skills/trace-funds/references/confidence.md"), encoding="utf-8").read()
    br = open(os.path.join(ROOT, "skills/trace-funds/references/bridges.md"), encoding="utf-8").read()
    for needle in ("top value recipients", "memo(data, not fact)", "OFF-CURVE", "sweep loop", "de-duplicated by orderId"):
        assert needle in tf, needle
    for needle in ("OFF-CURVE", "sweep loop", "memo"):
        assert needle in ap, needle
    for needle in ("Off-curve", "Sweep loop", "Lot-size", "Co-signed", "the bot kept running"):
        assert needle in conf, needle
    assert "double-count" in br and "prove negatives on chain" in br

def test_mayan_prints_screening_deadline_and_refund_baselines():
    blocked = {"orderId": "X", "trader": "T", "status": "ORDER_REFUNDED", "sanctioned": True,
               "security": {"code": "SWAP_BLOCKED", "msg": "Detected blocked address"},
               "deadline": "2026-11-03T10:00:00.000Z", "completedAt": "2026-11-04T06:36:00.000Z",
               "refundTxHash": "R1", "fulfillTxHash": None, "refundAmount": "100", "refundTokenSymbol": "USDC"}
    early = {"orderId": "Y", "trader": "T", "status": "ORDER_REFUNDED", "sanctioned": False, "security": None,
             "deadline": "2026-11-03T10:00:00.000Z", "completedAt": "2026-11-03T09:40:00.000Z", "refundTxHash": "R2"}
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        bridges.print_mayan_order(blocked)
    text = out.getvalue()
    assert 'BLOCKED screening   sanctioned=True security=SWAP_BLOCKED "Detected blocked address"' in text
    assert "deadline    2026-11-03T10:00:00  completedAt 2026-11-04T06:36:00  (refunded 20.6 h after deadline)" in text
    assert "REFUND tx   R1  refundAmount=100 USDC" in text
    assert bridges.refund_baseline(blocked) == "after deadline" and bridges.refund_baseline(early) == "before deadline"
    lines = bridges.mayan_summary([blocked, early])
    assert lines[0].startswith("-- blocked by Mayan screening: 1/2 orders (SWAP_BLOCKED)")
    assert "after deadline: 1 (lag 20.6 h–20.6 h); before deadline: 1 (lag 20.0 min–20.0 min)" in lines[1]
    # a completed order (fulfil hash echoed into refundTxHash) is not a refund and says "completed … before deadline"
    done = {"orderId": "Z", "fulfillTxHash": "F", "refundTxHash": "F", "deadline": "2026-11-07T12:32:48.000Z",
            "completedAt": "2026-11-07T12:17:58.000Z"}
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        bridges.print_mayan_order(done)
    assert "(completed 14.8 min before deadline)" in out.getvalue() and "REFUND" not in out.getvalue()

def test_mayan_trader_listing_prints_count_and_blocked_note():
    out = io.StringIO()
    with mock.patch.object(bridges, "http", return_value={"data": [{"orderId": "a", "trader": "T"}], "metadata": {"count": 10}}), \
         contextlib.redirect_stdout(out):
        bridges.mayan("4LkEyP9JzG2T3ttceaHhpCqLWrgm7oCPEkjzLdzLjNYJ")
    text = out.getvalue()
    assert "1 orders from 1 rows (listing count=10)" in text and "blocked/sanctioned orders never appear in listings" in text
    assert "omits refunded" not in bridges.__doc__

def test_time_range_and_memo_deadline_footers():
    base = 1762171200  # 2025-11-03 12:00 UTC
    def row(unix, ins, signers, memos=(), deltas=(), sol=()):
        return {"sig": f"s{unix}", "unix": unix, "time": sol_trace.ts(unix), "ok": True, "signers": signers, "programs": ["System"],
                "token_deltas": list(deltas), "sol_deltas": list(sol), "cu": {}, "memo": None, "memos": list(memos), "ins_types": ins}
    rows = [row(base + 60 * i, ["closeAccount"], ["A"]) for i in range(10)] + [row(base + 3600, ["withdrawFromNonce"], ["A"])]
    lines = sol_trace.time_range_footer(rows)
    assert lines[0] == "-- instruction types, first → last (90 % by):"
    assert lines[1] == "   closeAccount ×10  2025-11-03 12:00 → 12:09  (90 % by 12:09)"
    assert lines[2].startswith("   withdrawFromNonce ×1  2025-11-03 13:00 → 13:00")
    assert lines[3].startswith("-- last tx 2025-11-03 13:00:00 UTC  s")
    # memo with a 48 h term sent by V to wallet W; W never answers → expired, no reply
    memo_row = row(base, [], ["V"], memos=["Return the funds within 48 hours and keep 10%"],
                   sol=[{"account": "V", "lamports": -5000}, {"account": "W", "lamports": 5000}])
    lines = sol_trace.memo_deadline_footer("W", [memo_row, row(base + 100, ["transfer"], ["W"])])
    assert len(lines) == 1 and "→ expires 2025-11-05 12:00; reply before expiry: expired" in lines[0] and "sent 2025-11-03 12:00 by V" in lines[0]
    # W sends value back to V inside the window → counted as a reply
    reply = row(base + 7200, ["transfer"], ["W"], sol=[{"account": "W", "lamports": -1}, {"account": "V", "lamports": 1}])
    lines = sol_trace.memo_deadline_footer("W", [memo_row, reply])
    assert "reply before expiry: 1 reply tx, first 2025-11-03 14:00" in lines[0]
    assert sol_trace.memo_deadline("no term here", base) is None and sol_trace.memo_deadline("7 days", base) == base + 7 * 86400

def test_activity_footer_lists_programs_of_cosigned_txs():
    rows = [{"sig": "a", "unix": 1, "signers": ["A", "B"], "programs": ["DEX:pump.fun AMM", "SPL Token"], "token_deltas": [],
             "sol_deltas": [], "cu": {}, "memos": [], "ins_types": []},
            {"sig": "b", "unix": 2, "signers": ["A"], "programs": ["System"], "token_deltas": [], "sol_deltas": [], "cu": {}, "memos": [], "ins_types": []}]
    text = "\n".join(sol_trace.activity_footer("A", rows))
    assert "-- co-signed transactions: 1/2" in text and "programs: DEX:pump.fun AMM 1, SPL Token 1" in text

def test_summarize_collects_instruction_types():
    t = {"slot": 1, "blockTime": 1700000000, "meta": {"err": None, "preBalances": [0], "postBalances": [0], "preTokenBalances": [],
                                                       "postTokenBalances": [], "innerInstructions": [], "logMessages": []},
         "transaction": {"signatures": ["s"], "message": {"accountKeys": [{"pubkey": "A", "signer": True}], "instructions": [
             {"programId": "ComputeBudget111111111111111111111111111111"},
             {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "parsed": {"type": "closeAccount", "info": {}}},
             {"programId": "11111111111111111111111111111111", "parsed": {"type": "withdrawFromNonce", "info": {}}},
             {"programId": "KingXYZ11111111111111111111111111111111111"}]}}}
    assert sol_trace.summarize(t)["ins_types"] == ["closeAccount", "withdrawFromNonce", "KingXYZ1…"]

def test_cmd_program_prints_upgrade_history_and_rate():
    prog, pd = "99vQwtBwYtrqqD9YSXbdum3KBdxPAVxYTaQ3cfnJSrN2", "6y7C7Lfh1WRRbKohE2FQmFBD2asw3yMi17kStwEcAWWF"
    def loader_tx(unix, typ, sig):
        return {"slot": 1, "blockTime": unix, "meta": {"err": None, "preBalances": [0], "postBalances": [0], "preTokenBalances": [],
                "postTokenBalances": [], "innerInstructions": [], "logMessages": []},
                "transaction": {"signatures": [sig], "message": {"accountKeys": [{"pubkey": "G", "signer": True}], "instructions": [
                    {"programId": sol_trace.LOADER, "parsed": {"type": typ, "info": {"authority": "G"}}}]}}}
    day = 86400
    txs = {"u1": loader_tx(1751372720, "deployWithMaxDataLen", "u1"), "u2": loader_tx(1751372720 + 10 * day, "upgrade", "u2"),
           "u3": loader_tx(1751372720 + 20 * day, "upgrade", "u3"), "u4": loader_tx(1751372720 + 25 * day, "setAuthority", "u4")}
    def rpc(method, params):
        if method == "getAccountInfo" and params[0] == prog:
            return {"value": {"owner": sol_trace.LOADER, "executable": True,
                              "data": {"program": "bpf-upgradeable-loader", "parsed": {"type": "program", "info": {"programData": pd}}}}}
        if method == "getAccountInfo" and params[0] == pd:
            return {"value": {"owner": sol_trace.LOADER, "data": {"parsed": {"type": "programData", "info": {"authority": "6Bz8", "slot": 386211280}}}}}
        if method == "getSignaturesForAddress":
            return [{"signature": s} for s in ("u4", "u3", "u2", "u1")]
        if method == "getTransaction":
            return txs[params[0]]
        raise AssertionError(method)
    out = io.StringIO()
    with mock.patch.object(sol_trace, "sol_rpc", side_effect=rpc), mock.patch.object(sol_trace, "SOL_SLEEP", 0), \
         contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        sol_trace.cmd_program(prog, 300)
    text = out.getvalue()
    assert f"== {prog} [BRIDGE:Relay]" in text and f"-- programData {pd}  upgrade authority 6Bz8  last deploy slot 386211280" in text
    assert "-- loader transactions: 4 of 4 decoded signatures (cap 300)" in text
    assert "2025-07-01 12:25  deployWithMaxDataLen authority=G  u1" in text and "setAuthority         authority=G  u4" in text
    assert "-- upgrades: 3 between 2025-07-01 12:25 and 2025-07-21 12:25 (one every ~10.0 d); 3 in the 30 d before the latest" in text

def test_cmd_program_non_upgradeable_account():
    out = io.StringIO()
    with mock.patch.object(sol_trace, "sol_rpc", return_value={"value": {"owner": "11111111111111111111111111111111", "executable": False, "data": ["", "base64"]}}), \
         contextlib.redirect_stdout(out):
        sol_trace.cmd_program("GLj1kJJ1TnAvu8eT6ZJAwxM8arU9fjgjtW65bzt4uCus", 10)
    assert "-- not an upgradeable-loader program" in out.getvalue()

def test_recheck_sections_carry_read_time_and_as_of_line(tmp_path=None):
    import tempfile
    case = {"solana": {"wallets": ["W"], "token_accounts": ["TA"]}, "bridgers": ["X"]}
    path = os.path.join(tempfile.mkdtemp(), "case.json")
    json.dump(case, open(path, "w"))
    def rpc(method, params):
        if method == "getTokenAccountBalance":
            return {"value": {"uiAmountString": "5"}}
        if method == "getAccountInfo":
            return {"value": {"data": {"parsed": {"info": {"state": "frozen", "mint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"}}}}}
        return []
    out = io.StringIO()
    with mock.patch.object(recheck, "sol_rpc", side_effect=rpc), mock.patch.object(recheck, "http", return_value={"data": {"total": 0}}), \
         mock.patch.object(recheck, "SOL_SLEEP", 0), contextlib.redirect_stdout(out):
        recheck.main(path)
    text = out.getvalue()
    for h in ("## Solana balances (read ", "## Solana freeze state (read ", "## Solana latest activity (read ", "## Bridgers orders (read "):
        assert h in text, h
    assert "freeze TA: state=frozen USDC" in text
    assert text.strip().splitlines()[-1].startswith("## as-of stamps (quote every one that differs in the report lead): Solana balances 20")
    assert "EVM" not in text and "TRON" not in text  # sections absent from case.json print no header

def test_registry_mayan_program_ids_decode_to_32_bytes():
    for pid, label in common.SOL_PROGRAMS.items():
        if "Mayan" in label:
            assert len(sol_trace.b58decode(pid).rjust(32, b"\x00")) == 32 and len(sol_trace.b58decode(pid)) == 32, pid
    assert "BLZRi6frs4X4DNLw56V4EXai1b6QVESN1BhHBTYM9VcY" in common.SOL_PROGRAMS and "mayan34VedncxdK2XobtvWFDXQASUTBXhUVzt2kKgny" in common.SOL_PROGRAMS

def test_docs_mention_third_pass_items():
    tf = open(os.path.join(ROOT, "skills/trace-funds/SKILL.md"), encoding="utf-8").read()
    ap = open(os.path.join(ROOT, "skills/address-profile/SKILL.md"), encoding="utf-8").read()
    cr = open(os.path.join(ROOT, "skills/case-report/SKILL.md"), encoding="utf-8").read()
    conf = open(os.path.join(ROOT, "skills/trace-funds/references/confidence.md"), encoding="utf-8").read()
    br = open(os.path.join(ROOT, "skills/trace-funds/references/bridges.md"), encoding="utf-8").read()
    pack = open(os.path.join(ROOT, "skills/case-report/references/action-pack.md"), encoding="utf-8").read()
    rd = open(os.path.join(ROOT, "README.md"), encoding="utf-8").read()
    for needle in ("author's replies", "stated read time", "sol_trace.py program", "-- instruction types", "-- memo deadline", "sanctioned"):
        assert needle in tf, needle
    assert "sol_trace.py program" in ap and "how often it happened before" in ap
    for needle in ("as of\" stamp", "Prose must not outrun the check", "quotes, not facts", "read time", "Outreach when the victim is unknown"):
        assert needle in cr, needle
    for needle in ("Base rate", "Memo deadlines", "two populations", "Time range per instruction type", "Characterisations"):
        assert needle in conf, needle
    assert "never appear in" in br and "two baselines" in br and "FUDE" in br and "mayan34VedncxdK2XobtvWFDXQASUTBXhUVzt2kKgny" in br
    for needle in ("Mayan", "Relay", "SEAL 911", "seal_911_bot", "police report comes first", "Outreach when the victim is unknown", "reaches the thief too"):
        assert needle in pack, needle
    assert "`program`" in rd and "as-of stamps" in rd and "sanctioned" in rd

if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f(); print("ok", n)
