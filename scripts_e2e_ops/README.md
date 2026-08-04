# scripts_e2e_ops/

This directory was previously named `tests/`, which was misleading: nothing
here is an automated test suite. These are live-deployment verification
scripts — they spin up the real orchestrator against a real Trello board,
create real GitHub repos/PRs, and poll a running process over minutes. They
require real credentials (`.env`, `policy.conf`) and a running Ollama/worker
stack, and several hardcode `/home/ubuntu` as the deployment path. They are
not runnable in CI and were never meant to be.

Renamed rather than deleted because they document real operational
verification the system has gone through historically, and some overlap
with `run_e2e_test.sh` at the repo root.

## Known gap: this repo doesn't currently import

`utils/`, `config/`, and `worker/telegram/` are imported throughout the
codebase (`main.py` included) but aren't present in this repository — they
were never committed. As pushed, `python main.py` and most of `agents/`
fail with `ModuleNotFoundError` before any of this reaches the scripts in
this directory. Noting this here rather than pretending these scripts are
currently runnable against a fresh clone.
