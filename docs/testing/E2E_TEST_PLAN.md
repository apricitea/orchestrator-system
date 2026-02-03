# Comprehensive End-to-End Test Plan for Autonomous Orchestrator

## Overview

This document provides a complete, step-by-step plan to test the autonomous orchestrator system from Trello task creation through PR approval.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Environment Setup](#environment-setup)
3. [Trello Board Setup](#trello-board-setup)
4. [Test Task Creation](#test-task-creation)
5. [Orchestrator Execution](#orchestrator-execution)
6. [PR Review Process](#pr-review-process)
7. [Feedback Loop Verification](#feedback-loop-verification)
8. [Multi-Iteration Testing](#multi-iteration-testing)
9. [Troubleshooting Guide](#troubleshooting-guide)
10. [Success Criteria](#success-criteria)

---

## 1. Prerequisites

### 1.1 System Requirements

**System Specifications:**
- OS: Linux (Ubuntu 20.04+)
- RAM: 4GB minimum, 8GB recommended
- Disk: 20GB free space
- Python: 3.10+

### 1.2 Required Accounts & Tokens

**GitHub Setup:**
```bash
# GitHub personal access token with scopes:
# - repo (full control)
# - pull_requests (read/write)
# - contents (read/write)

export GITHUB_TOKEN="ghp_xxxxxxxxxxxxxxxxxxxx"
```

**Trello Setup:**
```bash
# Trello API key and token
# Get from: https://trello.com/app-key

export TRELLO_API_KEY="your_trello_api_key"
export TRELLO_TOKEN="your_trello_token"
```

### 1.3 Git Configuration

```bash
# Configure git user
git config --global user.name "AI Orchestrator"
git config --global user.email "orchestrator@ai-agent.com"

# Install gh CLI
wget https://github.com/cli/cli/releases/download/v2.40.0/gh_2.40.0_linux_amd64.deb
sudo dpkg -i gh_2.40.0_linux_amd64.deb

# Authenticate gh CLI
gh auth login
```

### 1.4 Repository Setup

```bash
# Clone or create test repository
cd /home/ubuntu
mkdir test-orchestrator-repo
cd test-orchestrator-repo
git init

# Create initial structure
mkdir -p src tests docs
echo "# Test Repository" > README.md
git add .
git commit -m "Initial commit"

# Create on GitHub
gh repo create test-orchestrator --public --source=. --remote=origin
git push -u origin main
```

---

## 2. Environment Setup

### 2.1 Activate Virtual Environment

```bash
cd /home/ubuntu
source venv/bin/activate
```

### 2.2 Verify Installation

```bash
# Test all imports
python3 -c "
from agents.orchestrator.enhanced_orchestrator import get_enhanced_orchestrator
from agents.orchestrator.task_context import TaskContext, get_task_context_manager
from agents.workers.git_agent import GitAgent
from worker.trello.client import TrelloClient
from agents.github.github_pr_reviewer import GitHubPRReviewer
from agents.github.pr_manager import get_pr_manager
print('✅ All imports successful')
"
```

### 2.3 Verify Configuration Files

```bash
# Check .env file
cat ~/.env | grep -E "GITHUB_TOKEN|TRELLO"

# Verify Trello client configuration
python3 -c "
from worker.trello.client import get_trello_client
client = get_trello_client()
print(f'Configured: {client.is_configured()}')
print(f'Board ID: {client.config.trello_board_id}')
"
```

### 2.4 Checkpoint Directory

```bash
# Ensure checkpoint directory exists and is writable
mkdir -p /tmp/task_checkpoints
ls -la /tmp/task_checkpoints
```

---

## 3. Trello Board Setup

### 3.1 Verify Board Lists

```bash
python3 -c "
from worker.trello.client import get_trello_client
import asyncio

async def check_lists():
    client = get_trello_client()
    lists = await client.get_lists()
    print('Trello Lists:')
    for name, list_id in lists.items():
        print(f'  - {name}: {list_id}')

asyncio.run(check_lists())
"
```

**Expected Output:**
```
Trello Lists:
  - TODO: [list_id_1]
  - In Progress: [list_id_2]
  - Review: [list_id_3]
  - Done: [list_id_4]
```

### 3.2 Verify Labels

```bash
python3 -c "
from worker.trello.client import get_trello_client
import asyncio

async def check_labels():
    client = get_trello_client()
    labels = await client.get_labels()
    print('Available Labels:')
    for label in labels:
        print(f'  - {label.get(\"name\")}: {label.get(\"color\")}')

asyncio.run(check_labels())
"
```

### 3.3 Clean Up Old Test Cards

```bash
# Remove any existing test cards
python3 -c "
from worker.trello.client import get_trello_client
import asyncio

async def cleanup():
    client = get_trello_client()
    cards = await client.get_todo_cards()

    for card in cards:
        if 'TEST' in card.title.upper() or 'E2E' in card.title.upper():
            print(f'Deleting test card: {card.title}')
            await client.move_card(card.id, client.config.trello_list_done)
            # Or delete completely if needed

asyncio.run(cleanup())
"
```

---

## 4. Test Task Creation

### 4.1 Priority System

**Priority Labels (in Trello):**
- 🔴 **P0 - Critical** (red label) - System breaking, security issues
- 🟠 **P1 - High** (orange label) - Important features
- 🟡 **P2 - Medium** (yellow label) - Normal tasks
- 🟢 **P3 - Low** (green label) - Nice to have

### 4.2 Create Test Tasks

Run this script to create comprehensive test tasks:

```python
#!/usr/bin/env python3
"""
Create test tasks in Trello for end-to-end orchestrator testing.
"""

import asyncio
from worker.trello.client import get_trello_client

TEST_TASKS = [
    {
        "title": "[E2E TEST] Simple Feature - Add Hello World Function",
        "description": """
## Task Description
Add a simple hello_world() function to the repository.

## Requirements
- Create src/hello.py
- Implement hello_world() function that returns "Hello, World!"
- Add basic tests

## Working Directory
/home/ubuntu/test-orchestrator-repo
        """,
        "priority": "P3 - Low",
        "label": "green",
        "expected_outcome": "PR created and approved"
    },
    {
        "title": "[E2E TEST] Bug Fix - Fix Typo in README",
        "description": """
## Task Description
Fix a typo in the README.md file.

## Requirements
- Change "Test Repository" to "Test Repository (E2E)"
- Commit the change

## Working Directory
/home/ubuntu/test-orchestrator-repo
        """,
        "priority": "P1 - High",
        "label": "orange",
        "expected_outcome": "PR created and approved"
    },
    {
        "title": "[E2E TEST] Feature - Add Calculator Module",
        "description": """
## Task Description
Create a calculator module with basic operations.

## Requirements
- Create src/calculator.py
- Implement add(), subtract(), multiply(), divide()
- Add comprehensive tests
- Add docstrings

## Working Directory
/home/ubuntu/test-orchestrator-repo
        """,
        "priority": "P2 - Medium",
        "label": "yellow",
        "expected_outcome": "PR created, needs revisions (missing error handling)"
    },
    {
        "title": "[E2E TEST] CRITICAL - Security Fix - Input Validation",
        "description": """
## Task Description
Add input validation to calculator module.

## Requirements
- Validate numeric inputs
- Handle division by zero
- Add type checking

## Working Directory
/home/ubuntu/test-orchestrator-repo

## Context
This is a follow-up to calculator module. Wait for calculator PR first.
        """,
        "priority": "P0 - Critical",
        "label": "red",
        "expected_outcome": "Should wait for calculator PR first"
    },
]

async def create_test_tasks():
    client = get_trello_client()

    # Get or create labels
    label_ids = {}
    for task in TEST_TASKS:
        priority = task["priority"]
        color = task["label"]
        label_id = await client.get_or_create_label(priority, color)
        label_ids[priority] = label_id

    # Get TODO list
    lists = await client.get_lists()
    todo_list_id = lists.get("TODO")

    if not todo_list_id:
        print("❌ TODO list not found!")
        return

    # Create cards
    for i, task in enumerate(TEST_TASKS, 1):
        print(f"\nCreating task {i}/{len(TEST_TASKS)}: {task['title']}")

        # Create card
        card_id = await client.create_card(
            name=task["title"],
            description=task["description"],
            list_id=todo_list_id,
        )

        # Add priority label
        priority_label_id = label_ids.get(task["priority"])
        if priority_label_id:
            await client.add_label_to_card(card_id, priority_label_id)

        print(f"  ✅ Created: {task['title']}")
        print(f"     Priority: {task['priority']}")
        print(f"     Card ID: {card_id}")

    print(f"\n✅ Created {len(TEST_TASKS)} test tasks in TODO list")
    print("\nNext: Run orchestrator to process tasks")

if __name__ == "__main__":
    asyncio.run(create_test_tasks())
```

Save as `/home/ubuntu/create_test_tasks.py` and run:

```bash
cd /home/ubuntu
python3 create_test_tasks.py
```

### 4.3 Verify Tasks Created

```bash
python3 -c "
from worker.trello.client import get_trello_client
import asyncio

async def verify_tasks():
    client = get_trello_client()
    cards = await client.get_todo_cards()

    print(f'Found {len(cards)} tasks in TODO:')
    print('\nPriority Order:')

    # Sort by priority (P0 first)
    priority_order = {'P0 - Critical': 0, 'P1 - High': 1, 'P2 - Medium': 2, 'P3 - Low': 3}

    sorted_cards = sorted(cards, key=lambda c: [
        priority_order.get(label.get('name', 'P3 - Low'), 999)
        for label in c.labels or []
    ])

    for card in sorted_cards:
        priority = ', '.join([label.get('name', '') for label in (card.labels or [])])
        print(f'  - [{priority}] {card.title}')
        print(f'    ID: {card.id}')

asyncio.run(verify_tasks())
"
```

---

## 5. Orchestrator Execution

### 5.1 Single Task Test Mode

Test with ONE simple task first:

```bash
cd /home/ubuntu

# Run orchestrator in test mode
python3 -c "
import asyncio
from run_orchestrator_on_trello import process_single_trello_task

async def test_one():
    # Get the P3 task (simplest)
    from worker.trello.client import get_trello_client
    client = get_trello_client()
    cards = await client.get_todo_cards()

    # Find the E2E test task
    test_card = None
    for card in cards:
        if 'Hello World' in card.title:
            test_card = card
            break

    if test_card:
        print(f'Testing with: {test_card.title}')
        await process_single_trello_task(test_card)
    else:
        print('Test card not found!')

asyncio.run(test_one())
"
```

### 5.2 Monitor Task Processing

```bash
# In one terminal, monitor Trello changes
watch -n 2 "python3 -c \"
from worker.trello.client import get_trello_client
import asyncio
async def check():
    client = get_trello_client()
    for name, list_id in (await client.get_lists()).items():
        cards = await client.get_list_cards(list_id)
        if cards:
            print(f'\\n{name}: {len(cards)} cards')
            for c in cards[:3]:
                print(f'  - {c.title[:40]}')
asyncio.run(check())
\""
```

### 5.3 Full Orchestrator Run

```bash
cd /home/ubuntu
nohup python3 run_orchestrator_on_trello.py > /tmp/orchestrator.log 2>&1 &

# Monitor logs
tail -f /tmp/orchestrator.log
```

### 5.4 Verify Priority Ordering

```bash
# Check that highest priority (P0) is processed first
grep -E "Task:|priority|P0|P1|P2|P3" /tmp/orchestrator.log | head -20
```

**Expected Flow:**
```
1. Check TODO list for cards
2. Sort by priority (P0 → P1 → P2 → P3)
3. Move highest priority to In Progress
4. Process task
5. Create PR
6. Run PR review
7. Move to Review or back to TODO with fix task
8. Repeat
```

---

## 6. PR Review Process

### 6.1 Automated Review Components

The automated PR reviewer checks:

**Security Scan:**
- SQL injection vulnerabilities
- XSS vulnerabilities
- Hardcoded secrets/credentials
- Input validation issues

**Quality Scan:**
- Error handling
- Testing coverage
- Documentation
- Code style

### 6.2 Monitor PR Reviews

```bash
# Check PR reviews being posted
grep -A 10 "Running automated PR review" /tmp/orchestrator.log

# Check review verdicts
grep -E "Verdict: APPROVED|NEEDS_CHANGES|REJECTED" /tmp/orchestrator.log
```

### 6.3 View PR on GitHub

```bash
# Get list of open PRs
gh pr list --repo test-orchestrator --state open

# View specific PR details
gh pr view 1 --repo test-orchestrator --json title,body,state,reviews
```

### 6.4 Verify Review Comments

```bash
# Check review comments
gh api repos/test-orchestrator/pulls/1/comments | jq '.[].body | .[:100]'
```

---

## 7. Feedback Loop Verification

### 7.1 Expected Feedback Loop Behavior

```
┌─────────────────────────────────────────────────────────┐
│              FEEDBACK LOOP DECISION MATRIX              │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  Verdict: APPROVED                                     │
│    → Action: MARK_DONE                                  │
│    → Trello: Move to Review → Done                      │
│    → Status: Task complete                              │
│                                                          │
│  Verdict: NEEDS_CHANGES                                 │
│    → Action: CREATE_FIX_TASK                            │
│    → Trello: Add to TODO (with [FIX] prefix)           │
│    → Status: Needs revision                             │
│                                                          │
│  Verdict: REJECTED                                      │
│    → Action: CREATE_FIX_TASK                            │
│    → Trello: Add to TODO (with [FIX] prefix)           │
│    → Status: Needs revision                             │
│                                                          │
│  Attempts ≥ 5                                           │
│    → Action: ESCALATE                                   │
│    → Trello: Move to Blocked                           │
│    → Status: Escalated to human                         │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

### 7.2 Verify Fix Task Creation

```bash
# Check for fix tasks being created
grep -E "\[FIX\]|\[P1\].*FIX" /tmp/orchestrator.log | head -10

# Check Trello for fix cards
python3 -c "
from worker.trello.client import get_trello_client
import asyncio

async def check_fix_tasks():
    client = get_trello_client()
    cards = await client.get_todo_cards()

    fix_tasks = [c for c in cards if '[FIX]' in c.title.upper()]

    print(f'Found {len(fix_tasks)} fix tasks:')
    for card in fix_tasks:
        print(f'  - {card.title}')
        print(f'    Original: {card.source_id if hasattr(card, \"source_id\") else \"N/A\"}')

asyncio.run(check_fix_tasks())
"
```

### 7.3 Verify PR Update vs Create

```bash
# Check PR manager decisions
grep -E "action.*created|action.*updated|action.*reused" /tmp/orchestrator.log

# Check iteration tracking
grep -E "Starting iteration|Iteration [0-9]+:" /tmp/orchestrator.log
```

---

## 8. Multi-Iteration Testing

### 8.1 Force a Needs Changes Scenario

Create a task that will intentionally fail review:

```python
#!/usr/bin/env python3
"""
Create a task that will trigger NEEDS_CHANGES verdict.
"""

import asyncio
from worker.trello.client import get_trello_client

async def create_intentional_failure_task():
    client = get_trello_client()

    lists = await client.get_lists()
    todo_list_id = lists.get("TODO")

    task_desc = """
## Task: Add Insecure Function (INTENTIONAL TEST)

## Requirements
Create a function that takes user input and executes it.

## ⚠️  WARNING
This task is DESIGNED to fail security review!

Expected flow:
1. Agent creates function with eval() or exec()
2. PR review finds security issue
3. PR rejected with NEEDS_CHANGES
4. Fix task created
5. Agent fixes with proper validation

## Working Directory
/home/ubuntu/test-orchestrator-repo
    """

    card_id = await client.create_card(
        name="[E2E TEST] Insecure Function - Will Fail Review",
        description=task_desc,
        list_id=todo_list_id,
    )

    # Add P1 label
    label_id = await client.get_or_create_label("P1 - High", "orange")
    await client.add_label_to_card(card_id, label_id)

    print(f"✅ Created intentional failure task")
    print(f"   Card ID: {card_id}")
    print(f"\nExpected flow:")
    print(f"  1. Task → In Progress → Implementation")
    print(f"  2. PR created with security issue")
    print(f"  3. Review: REJECTED (SQL injection risk)")
    print(f"  4. Fix task created")
    print(f"  5. Agent fixes the issue")
    print(f"  6. Updated PR approved")

if __name__ == "__main__":
    asyncio.run(create_intentional_failure_task())
```

Save as `/home/ubuntu/create_failure_test.py` and run:

```bash
python3 create_failure_test.py
```

### 8.2 Monitor Multi-Iteration Flow

```bash
# Watch the full iteration cycle
tail -f /tmp/orchestrator.log | grep -E "iteration|verdict|action|PR #"
```

**Expected Output Pattern:**
```
🔄 Starting iteration 1
📝 Implementation complete
🆕 Created PR #1: https://github.com/test/pull/1
🔍 Running automated PR review...
Verdict: REJECTED
Security: 2 critical issues
🔄 Feedback Loop Decision: CREATE_FIX_TASK
⚠️ Fix task needed

🔄 Starting iteration 2
📝 Implementation complete
🔄 Updating existing PR #1
🔍 Running automated PR review...
Verdict: APPROVED
✅ PR approved by automated review
```

### 8.3 Verify Checkpoint Persistence

```bash
# Check checkpoint files
ls -la /tmp/task_checkpoints/

# View a checkpoint
cat /tmp/task_checkpoints/{trello_card_id}.json | python3 -m json.tool | head -50
```

**Checkpoint Contents:**
```json
{
  "task_id": "task_abc123",
  "trello_card_id": "abc123def456",
  "original_task": "...",
  "current_iteration": 2,
  "current_pr_number": 15,
  "current_status": "in_review",
  "iterations": [
    {
      "iteration_number": 1,
      "status": "needs_revision",
      "pr_number": 15,
      "pr_action": "created",
      "review_verdict": "rejected",
      "security_issues": [...],
      "fix_recommendations": ["Fix SQL injection", "Add validation"]
    },
    {
      "iteration_number": 2,
      "status": "completed",
      "pr_number": 15,
      "pr_action": "updated",
      "review_verdict": "approved"
    }
  ]
}
```

---

## 9. Troubleshooting Guide

### 9.1 Common Issues

#### Issue 1: Agent Not Picking Up Tasks

**Symptoms:**
- TODO list has tasks but agent doesn't process them
- Log shows "No tasks found"

**Diagnosis:**
```bash
# Check if agent can access Trello
python3 -c "
from worker.trello.client import get_trello_client
import asyncio
async def test():
    client = get_trello_client()
    cards = await client.get_todo_cards()
    print(f'Found {len(cards)} tasks')
    for card in cards:
        print(f'  - {card.title}')
asyncio.run(test())
"
```

**Solutions:**
1. Check Trello API credentials in `~/.env`
2. Verify board ID is correct
3. Check TODO list name matches exactly

#### Issue 2: PR Not Created

**Symptoms:**
- Task moves to In Progress
- Implementation completes
- No PR created

**Diagnosis:**
```bash
# Check git_agent logs
grep -A 5 "git_agent.*execute" /tmp/orchestrator.log

# Check for git errors
grep -i "error\|failed\|exception" /tmp/orchestrator.log | grep -i "git\|pr"
```

**Solutions:**
1. Verify `GITHUB_TOKEN` is set
2. Check repo exists on GitHub
3. Verify gh CLI is authenticated: `gh auth status`

#### Issue 3: PR Review Not Running

**Symptoms:**
- PR created successfully
- No review comment posted

**Diagnosis:**
```bash
# Check PR reviewer initialization
grep -A 10 "PR reviewer" /tmp/orchestrator.log

# Test reviewer manually
python3 -c "
from agents.github.github_pr_reviewer import GitHubPRReviewer
import asyncio
async def test():
    reviewer = GitHubPRReviewer()
    # Test _pr_exists method
    exists = await reviewer._pr_exists('your-username', 'test-orchestrator', 1)
    print(f'PR exists check: {exists}')
asyncio.run(test())
"
```

**Solutions:**
1. Verify repo owner/name is correct
2. Check PR number exists
3. Run reviewer manually to debug

#### Issue 4: Checkpoint Corruption

**Symptoms:**
- "Failed to load checkpoint" errors
- JSON decode errors

**Diagnosis:**
```bash
# Validate checkpoint JSON
for file in /tmp/task_checkpoints/*.json; do
    echo "Checking $file..."
    python3 -m json.tool "$file" > /dev/null && echo "  ✅ Valid" || echo "  ❌ Invalid"
done
```

**Solutions:**
1. Delete corrupted checkpoints
2. System will create new ones
3. Check file locking issues

#### Issue 5: File Lock Timeout

**Symptoms:**
- "Failed to acquire lock" warnings
- Checkpoint save hangs

**Diagnosis:**
```bash
# Check for stale lock files
ls -la /tmp/task_checkpoints/*.lock 2>/dev/null || echo "No lock files"

# Check for stuck processes
ps aux | grep -i orchestrator
```

**Solutions:**
1. Kill stuck orchestrator processes
2. Remove stale lock files manually
3. Increase lock timeout in code if needed

### 9.2 Debug Mode

Enable detailed logging:

```bash
# Run with debug logging
DEBUG=1 python3 run_orchestrator_on_trello.py 2>&1 | tee /tmp/debug.log
```

### 9.3 Manual Recovery

If agent gets stuck:

```bash
# 1. Stop the orchestrator
pkill -f run_orchestrator_on_trello

# 2. Check current state
python3 -c "
from worker.trello.client import get_trello_client
from agents.orchestrator.task_context import get_task_context_manager
import asyncio

async def check_state():
    client = get_trello_client()
    manager = get_task_context_manager()

    # Check in-progress cards
    in_progress = await client.get_in_progress_cards()
    print(f'In Progress: {len(in_progress)}')

    # Check checkpoints
    checkpoints = manager.list_all_checkpoints()
    print(f'Checkpoints: {len(checkpoints)}')

    for card_id in checkpoints:
        ctx = manager.load_checkpoint(card_id)
        if ctx:
            print(f'  {card_id}: Iteration {ctx.current_iteration}, PR #{ctx.current_pr_number}')

asyncio.run(check_state())
"

# 3. Reset stuck cards if needed
# Manually move cards back to TODO or to Done as appropriate
```

---

## 10. Success Criteria

### 10.1 Test Checklist

**Phase 1: Task Processing**
- [ ] Agent picks up tasks from TODO list
- [ ] Tasks processed in priority order (P0 → P1 → P2 → P3)
- [ ] Cards move from TODO → In Progress → Review/Done

**Phase 2: PR Creation**
- [ ] Branch created for each task
- [ ] Code committed with proper format
- [ ] PR created with description
- [ ] PR URL extracted and stored

**Phase 3: Automated Review**
- [ ] Security scan runs on each PR
- [ ] Quality scan runs on each PR
- [ ] Review comment posted to GitHub
- [ ] Verdict generated (APPROVED/NEEDS_CHANGES/REJECTED)

**Phase 4: Feedback Loop**
- [ ] APPROVED PRs move to Review → Done
- [ ] REJECTED PRs create fix tasks
- [ ] Fix tasks processed before new tasks
- [ ] PR updated (not recreated) on iteration 2
- [ ] Checkpoint saves after each iteration

**Phase 5: Multi-Iteration**
- [ ] Task can iterate multiple times
- [ ] Each iteration tracked in checkpoint
- [ ] PR history preserved across iterations
- [ ] Task completes successfully after approval

**Phase 6: Edge Cases**
- [ ] Handles PR already exists case
- [ ] Handles deleted PR gracefully
- [ ] Handles missing Trello card
- [ ] Handles network failures with retry

### 10.2 Verification Commands

```bash
# Full system health check
python3 << 'EOF'
import asyncio
from worker.trello.client import get_trello_client
from agents.orchestrator.task_context import get_task_context_manager

async def health_check():
    print("="*60)
    print("SYSTEM HEALTH CHECK")
    print("="*60)

    # 1. Trello connection
    print("\n[1/5] Trello Connection...")
    client = get_trello_client()
    try:
        lists = await client.get_lists()
        print(f"  ✅ Connected - Found {len(lists)} lists")
    except Exception as e:
        print(f"  ❌ Failed: {e}")
        return

    # 2. Checkpoint system
    print("\n[2/5] Checkpoint System...")
    try:
        manager = get_task_context_manager()
        checkpoints = manager.list_all_checkpoints()
        print(f"  ✅ System OK - {len(checkpoints)} checkpoints")
    except Exception as e:
        print(f"  ❌ Failed: {e}")
        return

    # 3. GitHub connection
    print("\n[3/5] GitHub Connection...")
    import subprocess
    try:
        result = subprocess.run(['gh', 'auth', 'status'],
                              capture_output=True, text=True)
        if result.returncode == 0:
            print(f"  ✅ Authenticated")
        else:
            print(f"  ❌ Not authenticated")
    except Exception as e:
        print(f"  ❌ Failed: {e}")
        return

    # 4. Module imports
    print("\n[4/5] Module Imports...")
    try:
        from agents.automation.id_tracking import TaskContext
        from agents.orchestrator.task_context import TaskContext
        from agents.workers.git_agent import GitAgent
        from agents.github.pr_manager import get_pr_manager
        from agents.github.github_pr_reviewer import GitHubPRReviewer
        print(f"  ✅ All modules importable")
    except Exception as e:
        print(f"  ❌ Import failed: {e}")
        return

    # 5. File system
    print("\n[5/5] File System...")
    import os
    dirs = ['/tmp/task_checkpoints', '/tmp/task_recovery']
    all_ok = True
    for d in dirs:
        if os.path.exists(d):
            print(f"  ✅ {d} exists")
        else:
            print(f"  ⚠️  {d} missing (will be created)")

    print("\n" + "="*60)
    print("HEALTH CHECK COMPLETE - SYSTEM READY")
    print("="*60)

asyncio.run(health_check())
EOF
```

### 10.3 Expected Timeline

**Single Task (Simple):**
- Task pickup: Immediate
- Implementation: 1-3 minutes
- PR creation: 30 seconds
- PR review: 30 seconds
- Total: ~2-5 minutes

**Single Task (Complex, 1 iteration):**
- Implementation: 3-5 minutes
- PR creation: 30 seconds
- PR review (rejected): 30 seconds
- Fix task creation: Immediate
- Fix implementation: 2-3 minutes
- PR update: 30 seconds
- PR review (approved): 30 seconds
- Total: ~7-10 minutes

**Full Queue (4 tasks):**
- ~15-30 minutes depending on complexity
- Tasks processed in priority order
- Parallel processing possible with multiple agents

---

## 11. Test Execution Script

Complete automated test script:

```bash
#!/bin/bash
# run_e2e_test.sh - Complete end-to-end test

set -e

echo "╔════════════════════════════════════════════════════════════╗"
echo "║        AUTONOMOUS ORCHESTRATOR - E2E TEST SUITE           ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Phase 1: Setup
echo "📋 Phase 1: Environment Setup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Activate venv
source /home/ubuntu/venv/bin/activate

# Check prerequisites
echo "Checking prerequisites..."
python3 -c "
from worker.trello.client import get_trello_client
from agents.orchestrator.task_context import get_task_context_manager
print('✅ All imports successful')
" || { echo "❌ Import check failed"; exit 1; }

echo "✅ Environment ready"
echo ""

# Phase 2: Create test tasks
echo "📋 Phase 2: Create Test Tasks"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python3 /home/ubuntu/create_test_tasks.py || { echo "❌ Task creation failed"; exit 1; }
echo ""

# Phase 3: Verify tasks
echo "📋 Phase 3: Verify Tasks Created"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python3 -c "
from worker.trello.client import get_trello_client
import asyncio
async def check():
    client = get_trello_client()
    cards = await client.get_todo_cards()
    print(f'Found {len(cards)} tasks:')
    for card in cards:
        labels = ', '.join([l.name for l in card.labels]) if card.labels else 'None'
        print(f'  - {card.title}')
        print(f'    Priority: {labels}')
asyncio.run(check())
"
echo ""

# Phase 4: Start orchestrator
echo "📋 Phase 4: Start Orchestrator"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Kill any existing instances
pkill -f run_orchestrator_on_trello || true
sleep 2

# Start orchestrator in background
cd /home/ubuntu
nohup python3 run_orchestrator_on_trello.py > /tmp/orchestrator.log 2>&1 &
ORCH_PID=$!
echo "Orchestrator started (PID: $ORCH_PID)"
echo "  Log file: /tmp/orchestrator.log"
echo ""

# Phase 5: Monitor progress
echo "📋 Phase 5: Monitor Progress"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Monitor for 10 minutes
for i in {1..20}; do
    echo "Check $i/20..."

    # Show current status
    python3 -c "
from worker.trello.client import get_trello_client
import asyncio
async def status():
    client = get_trello_client()
    lists = await client.get_lists()
    for name, list_id in lists.items():
        if name in ['TODO', 'In Progress', 'Review', 'Done']:
            cards = await client.get_list_cards(list_id)
            print(f'  {name}: {len(cards)} cards')
asyncio.run(status())
" 2>/dev/null || true

    # Show recent log lines
    echo "  Recent activity:"
    tail -5 /tmp/orchestrator.log 2>/dev/null | grep -E "Task:|PR #|Verdict:|✅|❌" | head -3 || echo "  (waiting for activity...)"

    # Check if all tasks done
    todo_count=$(python3 -c "
import asyncio
from worker.trello.client import get_trello_client
async def count():
    client = get_trello_client()
    cards = await client.get_todo_cards()
    print(len(cards))
asyncio.run(count())
" 2>/dev/null || echo "0")

    if [ "$todo_count" -eq "0" ]; then
        echo ""
        echo "✅ All tasks completed!"
        break
    fi

    sleep 30
done

echo ""
echo "📋 Phase 6: Final Verification"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Show final stats
python3 << 'EOF'
import asyncio
from worker.trello.client import get_trello_client

async def final_report():
    client = get_trello_client()

    print("\n" + "="*60)
    print("FINAL REPORT")
    print("="*60)

    lists = await client.get_lists()

    for name, list_id in lists.items():
        if name in ['TODO', 'In Progress', 'Review', 'Done']:
            cards = await client.get_list_cards(list_id)
            if cards:
                print(f"\n{name}:")
                for card in cards:
                    labels = ', '.join([l.name for l in (card.labels or [])])
                    print(f"  - {card.title}")
                    print(f"    Labels: {labels}")

    # Check checkpoints
    from agents.orchestrator.task_context import get_task_context_manager
    manager = get_task_context_manager()
    checkpoints = manager.list_all_checkpoints()

    print(f"\n📊 Checkpoints Created: {len(checkpoints)}")

    for card_id in checkpoints:
        ctx = manager.load_checkpoint(card_id)
        if ctx:
            print(f"  {card_id}:")
            print(f"    Iterations: {ctx.current_iteration}")
            print(f"    PR: #{ctx.current_pr_number}" if ctx.current_pr_number else "    PR: None")
            print(f"    Status: {ctx.current_status.value}")

asyncio.run(final_report())
EOF

echo ""
echo "╔════════════════════════════════════════════════════════════╗"
echo "║              E2E TEST SUITE COMPLETE                        ║"
echo "╚════════════════════════════════════════════════════════════╝"
```

Save as `/home/ubuntu/run_e2e_test.sh` and run:

```bash
chmod +x /home/ubuntu/run_e2e_test.sh
./run_e2e_test.sh
```

---

## 12. Quick Reference

### 12.1 Key Commands

```bash
# Create test tasks
python3 /home/ubuntu/create_test_tasks.py

# Start orchestrator
cd /home/ubuntu
python3 run_orchestrator_on_trello.py

# Monitor logs
tail -f /tmp/orchestrator.log

# Check Trello status
python3 -c "
from worker.trello.client import get_trello_client
import asyncio
async def check():
    client = get_trello_client()
    for name, list_id in (await client.get_lists()).items():
        cards = await client.get_list_cards(list_id)
        print(f'{name}: {len(cards)}')
asyncio.run(check())
"

# View checkpoints
ls -la /tmp/task_checkpoints/
cat /tmp/task_checkpoints/*.json | jq '.'
```

### 12.2 Log Patterns

```bash
# Task processing
grep "Task:" /tmp/orchestrator.log

# PR creation
grep -E "Created PR|PR #" /tmp/orchestrator.log

# Reviews
grep -E "Verdict:|APPROVED|REJECTED" /tmp/orchestrator.log

# Iterations
grep "Starting iteration" /tmp/orchestrator.log

# Errors
grep -E "Error|Failed|Exception" /tmp/orchestrator.log
```

### 12.3 File Locations

```
Configuration:
  ~/.env                          # API tokens
  /home/ubuntu/worker/config.yaml  # Trello config

Code:
  /home/ubuntu/run_orchestrator_on_trello.py
  /home/ubuntu/agents/orchestrator/
  /home/ubuntu/agents/workers/

Data:
  /tmp/task_checkpoints/          # Task state
  /tmp/task_recovery/             # Agent recovery

Logs:
  /tmp/orchestrator.log
  /var/log/orchestrator/          # If configured
```

---

## 13. Next Steps After Testing

### 13.1 If All Tests Pass

1. **Deploy to Production**
   ```bash
   # Run orchestrator as service
   sudo cp /home/ubuntu/orchestrator.service /etc/systemd/system/
   sudo systemctl enable orchestrator
   sudo systemctl start orchestrator
   ```

2. **Set Up Monitoring**
   ```bash
   # Log aggregation
   tail -f /tmp/orchestrator.log | grep -E "ERROR|WARN"

   # Metrics dashboard (if configured)
   # Access at http://localhost:8080
   ```

3. **Scale Up**
   - Add more agents for parallel processing
   - Configure task priorities
   - Set up human escalation policies

### 13.2 If Tests Fail

1. **Identify Failure Point**
   - Review logs: `/tmp/orchestrator.log`
   - Check checkpoint state: `/tmp/task_checkpoints/`
   - Verify Trello state

2. **Fix and Retry**
   - Fix identified issue
   - Clean up: `rm /tmp/task_checkpoints/*.json`
   - Restart test: `./run_e2e_test.sh`

3. **Get Help**
   - Check troubleshooting guide (Section 9)
   - Review documentation in `/home/ubuntu/*.md`
   - Enable debug mode: `DEBUG=1`

---

## 14. Conclusion

This comprehensive test plan provides:

✅ **Complete Setup Instructions**
- Environment configuration
- Trello board setup
- Repository preparation

✅ **Test Task Creation**
- Multiple priority levels
- Different complexity levels
- Expected outcomes documented

✅ **Execution Monitoring**
- Real-time progress tracking
- Log analysis
- Verification commands

✅ **Feedback Loop Validation**
- Multi-iteration testing
- Fix task creation
- PR update vs create logic

✅ **Troubleshooting**
- Common issues and solutions
- Debug procedures
- Recovery methods

✅ **Success Criteria**
- Clear test checklist
- Expected timelines
- Verification commands

**Ready to test!** 🚀
