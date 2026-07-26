# Autonomous Agent Orchestrator

A self-hosted autonomous coding agent that runs on a schedule, processes a task queue, and operates your codebases with minimal supervision.

Designed to run as a systemd timer or cron job. Each invocation picks up the highest-priority pending task, executes it using Claude Code, and handles the full git workflow — committing, pushing, and opening PRs automatically.

---

## What it does

**Priority queue processing:**
1. Resume any task interrupted by a token limit in the previous run
2. Process the next pending task in the queue
3. Pull new tasks from the task backlog into the queue
4. Self-improvement: analyse recent execution metrics, generate improvement tasks

**Per-task execution:**
- Retrieves relevant context from a knowledge base (Qdrant hybrid dense+sparse RAG, with LightRAG graph as primary and Qdrant as fallback)
- Detects task type (bugfix, feature, refactor, security, docs, test, performance) and injects type-specific workflow instructions
- Injects past failure records for similar tasks to avoid repeating mistakes
- Classifies reversibility before executing destructive operations
- Runs Claude Code as a subprocess with a structured prompt
- Scores output quality using an LLM-as-judge step
- Auto-commits on solo repos; creates branches + PRs on team repos

**Safety:**
- Immutable policy file (`policy.conf`) defines blocked commands and paths — the agent cannot override these regardless of task instructions
- Credential redaction in all log output
- Hard cap on turns and runtime per task
- `STEP_BLOCKED` escape hatch: agent outputs this instead of proceeding when a required action is prohibited

---

## Architecture

```
orchestrator.py
├── Config          — all paths/credentials from environment variables
├── Policy          — blocked commands/paths from immutable policy.conf
├── Queue           — PostgreSQL-backed task queue with priority + retry tracking
├── Knowledge       — hybrid RAG (LightRAG graph → Qdrant → keyword grep fallback)
├── Failure memory  — stores past task failures, injects them into future prompts
├── Task execution  — builds structured prompt, runs claude CLI, captures output
├── Decomposition   — splits complex tasks into subtasks, runs synthesis agent
├── Git workflow    — branch/commit/push/PR automation
├── Judge           — LLM scores task output quality (0–10), flags poor outcomes
└── Self-improvement — analyses metrics + KPI state, generates fix tasks
```

---

## Database schema

The orchestrator uses a PostgreSQL database with the following tables (in the `orchestrator` schema):

| Table | Purpose |
|---|---|
| `orchestrator.projects` | Registered workspaces (path, team/solo, default branch) |
| `orchestrator.tasks` | Task definitions (title, description, priority) |
| `orchestrator.queue` | Execution queue (status, attempts, last output, session ID) |
| `orchestrator.sessions` | Claude session tracking per queue item |
| `orchestrator.task_failures` | Failure memory — past errors with embeddings for retrieval |

---

## Requirements

- Python 3.11+
- PostgreSQL 15+
- Redis (for knowledge cache — optional but recommended)
- [Claude Code CLI](https://github.com/anthropics/claude-code) (`claude`) authenticated and on PATH
- `gh` CLI authenticated (for PR workflow)
- Qdrant (for RAG — optional, falls back to keyword grep)

```bash
pip install -r requirements.txt
```

---

## Setup

**1. Configure environment**

```bash
cp .env.example .env
# fill in DATABASE_URL, GITHUB_TOKEN, WORKSPACE_ROOT at minimum
```

**2. Configure policy**

```bash
cp policy.conf.example policy.conf
# review blocked_commands and blocked_paths
# optional: make immutable — sudo chattr +i policy.conf
```

**3. Create database schema**

```sql
CREATE SCHEMA IF NOT EXISTS orchestrator;

CREATE TABLE orchestrator.projects (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    workspace_path TEXT NOT NULL UNIQUE,
    default_branch TEXT NOT NULL DEFAULT 'main',
    is_team_repo BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE orchestrator.tasks (
    id SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    priority INTEGER NOT NULL DEFAULT 1,
    tags TEXT[],
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE orchestrator.queue (
    id SERIAL PRIMARY KEY,
    task_id INTEGER REFERENCES orchestrator.tasks(id),
    project_id INTEGER REFERENCES orchestrator.projects(id),
    workspace_path TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    priority INTEGER NOT NULL DEFAULT 1,
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    last_output TEXT,
    git_branch TEXT,
    claude_session_id TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

CREATE TABLE orchestrator.sessions (
    claude_session_id TEXT PRIMARY KEY,
    session_name TEXT,
    task_id INTEGER,
    queue_id INTEGER,
    project_id INTEGER,
    workspace_path TEXT,
    status TEXT DEFAULT 'active',
    last_active_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE orchestrator.task_failures (
    id SERIAL PRIMARY KEY,
    queue_id INTEGER,
    title TEXT,
    description TEXT,
    error_summary TEXT,
    stdout_tail TEXT,
    stderr_tail TEXT,
    embedding FLOAT[],
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

**4. Register a project**

```sql
INSERT INTO orchestrator.projects (name, workspace_path, default_branch, is_team_repo)
VALUES ('my-project', '/path/to/workspaces/my-project', 'main', false);
```

**5. Add a task**

```sql
INSERT INTO orchestrator.queue (title, description, priority, workspace_path)
VALUES (
    'Fix the flaky test in auth module',
    'The test test_session_expiry in tests/test_auth.py fails intermittently. Investigate and fix the root cause.',
    2,
    '/path/to/workspaces/my-project'
);
```

**6. Run**

```bash
python orchestrator.py
```

**As a systemd timer:**

```ini
# /etc/systemd/system/orchestrator.service
[Unit]
Description=Autonomous Orchestrator

[Service]
Type=oneshot
WorkingDirectory=/path/to/orchestrator-system
ExecStart=/usr/bin/python3 orchestrator.py
EnvironmentFile=/path/to/orchestrator-system/.env

# /etc/systemd/system/orchestrator.timer
[Unit]
Description=Run orchestrator every 2 hours

[Timer]
OnCalendar=*-*-* 00/2:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
sudo systemctl enable --now orchestrator.timer
```

---

## Task execution flow

```
queue item picked
  → knowledge retrieved (RAG)
  → failure context injected
  → task type detected → type-specific instructions added
  → is_complex? → decompose into subtasks → run each → synthesize
               → no → run single Claude session
  → output judged (LLM score 0–10)
  → git: autocommit → push → PR (team) or direct push (solo)
  → result written to DB
```

---

## Stack

Python · PostgreSQL · Redis · Qdrant · fastembed · Claude Code CLI · gh CLI
