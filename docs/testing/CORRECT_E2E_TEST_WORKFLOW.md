# CORRECT End-to-End Test Workflow

## ❌ WRONG WAY (What I Did Before - DO NOT DO THIS)

```bash
# WRONG - Bypasses daemon and Trello
python3 -m agents.orchestrator.main_orchestrator
```

**Why This Is Wrong:**
- Bypasses the daemon completely
- No Trello card created or managed
- No card movement through lists
- Doesn't test the real production workflow

---

## ✅ CORRECT WAY (Production Workflow)

### Step 1: Create Card in Trello TODO List

Use Python to create a card via Trello API:

```python
from worker.trello.client import get_trello_client

async def create_test_card():
    client = get_trello_client()

    card_name = "[project-name] [agent] P2: Task description"
    card_desc = """Working Directory: /home/ubuntu/projects/project-name

Task: Full task description here

Requirements:
1. Requirement 1
2. Requirement 2
..."""

    card_id = await client.create_card(name=card_name, desc=card_desc)
    await client.add_card_label(card_id, "P2", "yellow")

    print(f"Card created: {card_id}")
```

### Step 2: Monitor Card Movement

Watch the card move through lists automatically:

```bash
# Check status every 30 seconds
watch -n 30 'python3 << EOF
import asyncio
from worker.trello.client import get_trello_client

async def check():
    client = get_trello_client()

    for list_name in ["To do", "In Progress", "Review", "Done"]:
        print(f"\n{list_name}:")
        # ... check cards ...

asyncio.run(check())
EOF'
```

### Step 3: Expected Card Movement

1. **TODO** → Daemon picks up card
2. **In Progress** → Task executing
3. **Review** → PR created, awaiting review
4. **Done** → PR approved and merged (or fix cards created)

### Step 4: Verify Outputs

When card reaches Review, verify:

1. **PR created**: Check GitHub for new PR
2. **Commit message**: Should describe the feature (not "chore: generate...")
3. **PR title**: Should describe the feature (not "Create pull request...")
4. **Files created**: Code, tests, documentation
5. **Tests pass**: All tests passing
6. **Security scan**: No critical issues
7. **Repository clean**: On main branch, no uncommitted changes

### Step 5: Monitor Fix Workflow (if applicable)

If PR review finds issues:
- Fix card created in In Progress
- Fix card processed → new PR created
- Review cycle repeats

---

## Key Differences

| Aspect | Wrong Way | Correct Way |
|--------|-----------|-------------|
| **Entry point** | Direct orchestrator | Daemon + Trello card |
| **Trello cards** | None | Created and managed |
| **Card movement** | N/A | TODO → Progress → Review → Done |
| **Orchestrator used** | main_orchestrator | enhanced_orchestrator |
| **Context tracking** | Minimal | Full (trello_card_id, etc.) |
| **Feedback loop** | None | PR review → fix cards |
| **Production-like?** | ❌ No | ✅ Yes |

---

## Why The Correct Way Matters

1. **Tests Real Workflow**: Production uses daemon + Trello
2. **Tests Integration**: Verifies all components work together
3. **Tests Feedback Loop**: PR review creates fix cards
4. **Tests Card Movement**: Verifies Trello integration
5. **Tests Context Passing**: trello_card_id propagated correctly

---

## Common Mistakes to Avoid

### ❌ Mistake 1: Running Orchestrator Directly
```bash
# WRONG
python3 -m agents.orchestrator.main_orchestrator
```

### ❌ Mistake 2: Creating Cards in Wrong List
```python
# WRONG - Don't create in Done or In Progress
card_id = await client.create_card(name=..., desc=..., list_id=done_list_id)

# CORRECT - Create in TODO (default)
card_id = await client.create_card(name=..., desc=...)
```

### ❌ Mistake 3: Not Waiting for Daemon
```python
# WRONG - Try to process immediately
card_id = await client.create_card(...)
# Immediately run orchestrator <- WRONG

# CORRECT - Let daemon pick it up
card_id = await client.create_card(...)
# Wait 30-60 seconds for daemon to process
# Check card moved to In Progress
```

### ❌ Mistake 4: Checking Wrong Lists
```python
# WRONG - Check Done immediately after creation
done_cards = await client.get_done_cards()  # Will be empty!

# CORRECT - Check workflow progress
todo_cards = await client.get_todo_cards()  # Should be empty after pickup
progress_cards = await client.get_in_progress_cards()  # Should have the card
```

---

## Verification Checklist

After test completes:

- [ ] Card started in TODO
- [ ] Card moved to In Progress (daemon picked it up)
- [ ] Card moved to Review (task completed, PR created)
- [ ] PR created on GitHub
- [ ] Commit message is descriptive (e.g., "feat: add...")
- [ ] PR title is descriptive (not "Create pull request...")
- [ ] Repository is on main branch
- [ ] Working tree is clean
- [ ] Tests pass
- [ ] Security scan clean
- [ ] If review issues: Fix card created in In Progress

---

## Example Test Task

Good test tasks are:
- Simple features (1-3 files)
- Clear requirements
- Testable
- Not too complex (avoid large refactors)

**Good Example:**
```
Add a footer component with copyright year
```

**Bad Example:**
```
Refactor entire architecture to use microservices
```

---

## Timeline Expectations

- **0:00** - Create card in TODO
- **0:30** - Daemon picks up, moves to In Progress
- **1:00-3:00** - Task executing (depending on complexity)
- **3:00** - Card moves to Review, PR created
- **3:30** - PR review completes
- **4:00** - Either:
  - Card moves to Done (if approved)
  - Fix card created (if issues found)

---

## Files To Monitor

1. **Trello**: Watch card movement
2. **GitHub**: Watch PR creation and status
3. **Repository**: Watch branch state and commits
4. **Daemon logs**: `/home/ubuntu/logs/` (if available)

---

## Rollback Plan

If something goes wrong:

1. **Card stuck in TODO**: Check daemon is running (`ps aux | grep daemon`)
2. **Card stuck in In Progress**: Check task_executor logs for errors
3. **Card stuck in Review**: Manually review PR on GitHub
4. **Repository in bad state**:
   ```bash
   git checkout main
   git restore .
   ```
5. **Daemon not working**: Restart daemon

---

## Success Criteria

Test is successful when:

1. ✅ Card moved through all expected lists
2. ✅ PR created with correct title and commit message
3. ✅ Code is functional and tested
4. ✅ Repository left clean
5. ✅ No errors in daemon logs
6. ✅ If issues found: Fix workflow triggered correctly

---

**Remember: The goal is to test the PRODUCTION workflow, not bypass it!**
