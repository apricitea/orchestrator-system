# 🚨 CRITICAL BUG: Infinite Fix Loop

## Summary

The orchestrator is creating an **infinite loop of fix cards** that can never complete because:

1. **Testing agent creates wrong tests**: Python pytest for React components
2. **Tests fail**: Cannot test React/TypeScript with Python pytest
3. **PR reviewer rejects**: "Tests are failing"
4. **Fix cards created**: But fixes can't work (wrong framework)
5. **Loop forever**: More fix cards, none completing

## Current State (DISASTER)

```
Trello Review: 7 cards
  - 1 original task (stuck in Review)
  - 6 FIX cards (all failing)

Trello Done: 0 cards
  - NOTHING IS COMPLETING!
```

## Root Cause Analysis

### Bug Location 1: Orchestrator Task Decomposition

**File:** `main_orchestrator.py` (task decomposition)

**Problem:** Doesn't pass `framework` parameter for React projects

```json
// WRONG - Missing framework
"context": {
  "language": "javascript",
  "file_path": "src/tests/components/WelcomeHeading.test.js"
}

// CORRECT - Should include framework
"context": {
  "language": "javascript",
  "framework": "jest",  // ← MISSING!
  "file_path": "src/tests/components/WelcomeHeading.test.js"
}
```

### Bug Location 2: Testing Agent Default

**File:** `/home/ubuntu/agents/workers/testing_agent.py:56`

```python
framework = kwargs.get("framework", "pytest")  # ← DEFAULTS TO PYTEST!
```

**Problem:** Defaults to pytest for EVERYTHING, including React projects!

### Bug Location 3: No Framework Detection

**Problem:** testing_agent doesn't detect from:
- File extension (.tsx/.jsx → Jest/Vitest, .py → pytest)
- Project structure (package.json → Jest, setup.py → pytest)
- Language + framework combo (javascript+react → Jest)

## Evidence

### WelcomeHeading Test (WRONG)

```python
# File: src/components/__tests__/WelcomeHeading.test.tsx
import pytest  # ← WRONG! Should be Jest for React
from unittest.mock import patch, MagicMock  # ← MOCKS!

# This can NEVER work - testing React with Python!
@patch('src.components.WelcomeHeading.render')
def test_renders_default_heading_without_props(self, mock_render, frontend_component):
    # Testing mocked methods that don't exist!
    pass
```

### Git Log (Fix Spam)

```
69449a5a fix: address review feedback from PR #39 (cycle 1)
554910aa fix: address review feedback from PR #39 (cycle 1)
f55d896b fix: address review feedback from PR #39 (cycle 1)
0ecc1910 fix: resolve review feedback from PR #39 (cycle 1)
```

**4 fix commits for PR #39 alone!** None can work!

## Impact

### Immediate Impact

1. **6 stuck cards in Review** - None can complete
2. **0 cards in Done** - Nothing finishing
3. **Infinite fix loop** - Wasting API tokens and time
4. **Developer frustration** - Can't use the system

### Long-term Impact

1. **System unusable** - Nothing completes successfully
2. **Resource waste** - Infinite loop costs money
3. **Broken trust** - System appears broken

## Solution

### Fix 1: Orchestrator Must Pass Framework

**When:** Task decomposition for testing_agent

**Logic:**
```python
# If coding task used framework="react", pass it to testing task
if subtask_agent == "testing_agent":
    # Get framework from related coding task
    coding_framework = extract_framework_from_dependencies(subtask)
    context["framework"] = map_to_test_framework(coding_framework)
```

**Mapping:**
- `react` → `jest` or `vitest`
- `vue` → `vitest`
- `fastapi` → `pytest`
- `flask` → `pytest`
- `next` → `jest`

### Fix 2: Testing Agent Framework Detection

**When:** framework not specified in kwargs

**Logic:**
```python
# Auto-detect framework from project
if not framework:
    if file_path.endswith(('.tsx', '.jsx')):
        # Check for React project
        if os.path.exists('package.json'):
            framework = 'jest' if has_jest() else 'vitest'
    elif file_path.endswith('.py'):
        framework = 'pytest'
```

### Fix 3: Add Escape Hatch

**When:** Too many fix cycles (e.g., 3+)

**Logic:**
```python
# After 3 fix attempts, move card to "Blocked" or notify human
if fix_cycle >= 3:
    move_card_to_blocked(card_id, reason="Unable to fix after 3 attempts")
    notify_human("Card blocked, manual intervention needed")
```

## Other Issues Found

### Issue 1: Moving Too Fast?

**Question:** "Is it trying to do things so fast that nothing is working?"

**Answer:** Not exactly "too fast", but:
- Creates cards without proper framework detection
- Doesn't validate test framework before creating tests
- No checks to prevent impossible combinations (Python + React)

### Issue 2: PR Reviewer Too Strict?

**Question:** "Are the reviewer agents performing great?"

**Answer:** Reviewer is actually working correctly!
- It's RIGHT to reject tests that can't pass
- The tests ARE failing (pytest can't test React)
- The problem is UPSTREAM (wrong test creation)

### Issue 3: Spammy Messages

**Question:** "All the spammy messages"

**Answer:** Side effect of infinite loop:
- Multiple fix cards for same PR
- Each fix creates a commit
- Each fix card adds noise

## Immediate Action Required

1. **Stop the daemon** - Prevent more stuck cards
2. **Clear Review list** - Move stuck cards manually
3. **Apply Fix 1** - Orchestrator framework passing
4. **Apply Fix 2** - Testing agent detection
5. **Apply Fix 3** - Escape hatch for stuck cards
6. **Test thoroughly** - Verify React → Jest, Python → pytest
7. **Restart daemon** - With fixes applied

## Testing Plan

### Test 1: React Project
```
Task: Create React button component
Expected:
  - Component created (.jsx)
  - Tests created with Jest
  - Tests pass
  - Card moves to Done
```

### Test 2: Python Project
```
Task: Create Python utility function
Expected:
  - Function created (.py)
  - Tests created with pytest
  - Tests pass
  - Card moves to Done
```

### Test 3: Framework Detection
```
Task: Create component without specifying framework
Expected:
  - Auto-detect from file extension
  - .tsx → Jest
  - .py → pytest
```

## Files to Modify

1. `/home/ubuntu/agents/orchestrator/main_orchestrator.py`
   - Task decomposition: Pass framework to testing_agent

2. `/home/ubuntu/agents/workers/testing_agent.py`
   - Add framework detection logic
   - Fix default framework behavior

3. `/home/ubuntu/agents/orchestrator/enhanced_orchestrator.py`
   - Add escape hatch for fix cycles

## Priority

**CRITICAL** - System is currently broken and unusable.

**Estimated Fix Time:** 2-3 hours
- 1 hour: Orchestrator framework passing
- 1 hour: Testing agent detection
- 30 min: Escape hatch
- 30 min: Testing

---

**This must be fixed BEFORE any more tasks are processed, or the infinite loop will continue.**
