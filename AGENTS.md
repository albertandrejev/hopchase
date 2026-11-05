<!-- bmad:context -->
<!-- Verified 2026-11-05 against fe299f0. Managed by bmad-project-context; edits inside this block are replaced on refresh. Keep anything you want preserved outside the markers. -->

## hopchase

Claude plugin for crypto fund-tracing across Solana, EVM chains and TRON, ending in a case report. Python scripts in `scripts/`, plugin skills in `skills/`, manifest in `.claude-plugin/`.

## Policy

- Never push to main; work on a branch and open a PR. Commits must be signed and history linear, so no merge commits.
- Read API keys only from environment variables via `scripts/common.py`; never write them to output, logs, reports or commits.

## Where things are

- Adding a bridge: follow "Adding a new bridge" in `skills/trace-funds/references/bridges.md`.
- Adding a skill or script: add it to the lists in `tests/test_smoke.py` and to `README.md`; the test only covers what is listed.

## Running and verifying

- Requires Python 3.11+: the scripts use `datetime.UTC`.
- Run `python3 tests/test_smoke.py` before every PR; there is no CI, so nothing else checks the change. It does not exercise the tracers against live APIs.
- Keep `tests/` offline; verify live API behavior by running the script by hand.

## Conventions that differ from defaults

- Use only the standard library in `scripts/`; the plugin has no install step. Make HTTP calls through `common.http` or `common.sol_rpc`, which handle backoff, not `requests`.
- Write results to stdout and progress to stderr via `common.log`; the skills redirect stdout into trace files.

<!-- /bmad:context -->
