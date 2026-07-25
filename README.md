# Autonomous Agent Orchestrator System

A research project exploring multi-agent orchestration for end-to-end software development: task decomposition, parallel agent execution, self-healing retries, and an automated PR workflow, coordinated via Trello.

## Overview

Nine specialized agents (coding, testing, security, review, git, debug, docs, planning, deployment) handle a task from a Trello card through to an opened PR:

1. Task decomposition into dependent subtasks
2. Parallel execution across agents
3. Test run + security scan
4. Auto-fix loop on failure (up to 3 retries, then moved to Blocked)
5. Code review, commit, PR creation
6. Automated PR review

```
                     TASK START
              (Trello TODO card or CLI)
                        │
                        ▼
              TASK DECOMPOSITION
        break into subtasks, assign agents
                        │
                        ▼
             PARALLEL EXECUTION WAVES
   branch → build+test → review → commit → PR
                        │
                        ▼
                 Tests pass? ──No──► auto-fix loop (max 3) ──► still failing? Blocked
                        │Yes
                        ▼
                    Create PR
                        │
                        ▼
              PR review (security, quality, tests)
                        │
              Approved? ──No──► fix card created
                        │Yes
                        ▼
                  Merge, move to Done
```

## Key mechanisms

- **Test framework auto-detection** from file extension/project structure (pytest, Jest/Vitest, gotest, JUnit) — fixes an earlier bug where the testing agent ran pytest against React components.
- **Security scanning** across 7 categories: SQL injection, XSS, hardcoded secrets, command injection, path traversal, dangerous operations, malicious code patterns.
- **Escape hatch**: after 3 failed auto-fix attempts, a card moves to Blocked instead of looping forever.

## Repository structure

```
agents/
├── orchestrator/   # main / enhanced / SOTA / strict-E2E orchestrator variants
├── workers/         # coding, testing, git, review, security, debug agents
├── github/          # PR review + management
└── automation/      # quality guard, task ID tracking
docs/                 # architecture, testing, bug reports, guides
scripts/, tests/
```

## Installation

```bash
git clone https://github.com/apricitea/orchestrator-system.git
cd orchestrator-system

pip install -r requirements.txt
cp .env.example .env  # set ANTHROPIC_API_KEY, GITHUB_TOKEN, TRELLO_* keys
```

## Usage

```bash
python scripts/orchestrator_cli.py \
  --task "Add user authentication" \
  --project "/path/to/project" \
  --working-directory "/path/to/project"
```

Or via the Python API:

```python
from agents.orchestrator.enhanced_orchestrator import create_enhanced_orchestrator

orchestrator = await create_enhanced_orchestrator()
result = await orchestrator.execute(
    task="Add user authentication feature",
    working_directory="/path/to/project",
    trello_card_id="card_id_from_trello",
)
```

## Status

Personal research project — functional for the agent workflows described above, not benchmarked, and no reliability/accuracy numbers are published here.

## Author

**Alvin Christian Nataputra** ([@apricitea](https://github.com/apricitea))

## License

MIT — see [LICENSE](LICENSE).
