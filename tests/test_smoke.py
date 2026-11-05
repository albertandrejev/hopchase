"""Offline smoke tests: no network. Run: python3 -m pytest tests/ or python3 tests/test_smoke.py"""
import sys, os, json, re
ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import sol_trace, common

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

if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f(); print("ok", n)
