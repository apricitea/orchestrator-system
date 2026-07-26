# STRICT END-TO-END AUTONOMOUS AGENT RULES

## 🚨 CRITICAL RULES - NEVER VIOLATE

### Rule 1: Project Discovery & Validation
```python
MANDATORY_VALIDATION_CHECKLIST = [
    "✅ Project exists in /home/ubuntu/projects/{project_name}/",
    "✅ Git remote is correctly configured",
    "✅ Can fetch from origin",
    "✅ Working directory is valid",
]

ALWAYS:
1. Check /home/ubuntu/projects/ for project folder
2. Validate git remote: `git remote -v`
3. Test git fetch: `git fetch origin`
4. If remote missing → STOP and ASK USER
5. Never guess or assume remote URL
```

### Rule 2: Trello Task Format (STRICT)
```python
REQUIRED_TRELLO_FORMAT = "[{project_name}] [agent] P{priority}: {description}"

VALID EXAMPLES:
- "[laptop-recommendation] [agent] P0: Fix authentication bug"
- "[web-api] [agent] P1: Add user profile endpoint"

FORBIDDEN:
- ❌ Custom test formats
- ❌ Missing project name
- ❌ Missing priority level
- ❌ Agent field other than "[agent]"
```

### Rule 3: Pre-Work Git Operations (MANDATORY)
```python
BEFORE_ANY_CODING = [
    "1. cd /home/ubuntu/projects/{project_name}/",
    "2. git checkout main",           # MUST be on main
    "3. git fetch origin",            # MUST fetch latest
    "4. git pull origin main",        # MUST pull latest
    "5. git status",                  # Verify clean state
]

NEVER_SKIP = True
NEVER_ASSUME_LOCAL_IS_LATEST = True
```

### Rule 4: Task Breakdown Requirements
```python
EVERY_TASK_MUST_INCLUDE = {
    "git_agent": ["Create branch from LATEST main"],
    "coding_agent": ["Implement with working_directory context"],
    "testing_agent": ["Write tests", "Run tests"],
    "security_agent": ["Security scan"],
    "review_agent": ["Review code quality, security, tests"],
    "git_agent": ["Commit with conventional commit"],
    "git_agent": ["Push to origin"],
    "git_agent": ["Create PR with template"],
    "pr_reviewer": ["Automated PR review"],
}

MANDATORY_CONTEXT = {
    "working_directory": "/home/ubuntu/projects/{project_name}/",
    "remote_verified": True,
    "main_branch_pulled": True,
}
```

### Rule 5: Code Review Feedback Loop
```python
REVIEW_FEEDBACK_LOOP = {
    "round_1": {
        "reviewer": "review_agent",
        "action": "Review code, tests, security",
        "on_issues": "Create fix task in Trello"
    },
    "round_2": {
        "reviewer": "pr_reviewer",  # After PR created
        "action": "Review full PR",
        "verdicts": ["approved", "needs_changes", "rejected"]
    },
    "max_rounds": 3,
    "escalate_after": "If not approved after 3 rounds → notify human"
}
```

### Rule 6: PR Creation & Push (STRICT)
```python
PR_CREATION_CHECKLIST = [
    "✅ Branch created from LATEST main",
    "✅ Code committed with conventional commit message",
    "✅ Tests passing",
    "✅ Security scan passed",
    "✅ Review agent approved",
    "✅ git push origin {branch_name}",
    "✅ gh pr create --title {title} --body {body}",
    "✅ Verify PR created: gh pr view {pr_number}",
]

NEVER:
- ❌ Create PR without pushing to origin
- ❌ Create PR without review approval
- ❌ Skip verification step
```

### Rule 7: PR Review Flow (MANDATORY)
```python
PR_REVIEW_PROCESS = [
    "1. Automated PR reviewer analyzes PR",
    "2. Verdict: approved / needs_changes / rejected",
    "3. If approved → Proceed to Telegram",
    "4. If needs_changes → Create fix task → Return to Step 1",
    "5. If rejected → Create fix task → Return to Step 1",
    "6. Max 3 iterations → Escalate to human",
]

PR_REVIEW_MUST_CHECK = [
    "Code quality",
    "Test coverage",
    "Security vulnerabilities",
    "Documentation",
    "Conventional commits",
    "Branch cleanliness",
]
```

### Rule 8: Telegram Notification (FINAL STEP)
```python
ONLY_AFTER_PR_APPROVED = {
    "notification": {
        "chat_id": "get_from_env()",
        "message": f"""
🎉 PR APPROVED AND READY TO MERGE!

Project: {project_name}
PR: #{pr_number}
Title: {pr_title}
URL: {pr_url}

Branch: {branch_name} → main
Author: Autonomous Agent

✅ All checks passed
✅ Code review approved
✅ Tests passing
✅ Security scan clean

👉 Please review and merge: {pr_url}
        """,
    },
    "ACTIONS_BEFORE": [
        "PR must be approved by pr_reviewer",
        "All tests must pass",
        "Security scan must pass",
        "Code must be pushed to origin",
    ],
}
```

---

## 🔄 COMPLETE E2E WORKFLOW (STRICT)

```
┌─────────────────────────────────────────────────────────────┐
│  PHASE 1: TASK CREATION & VALIDATION                        │
└─────────────────────────────────────────────────────────────┘

1. User creates Trello card with format:
   "[{project}] [agent] P{level}: {description}"

2. System validates:
   ✅ Format is correct
   ✅ Project exists in /home/ubuntu/projects/{project}/
   ✅ Git remote is configured
   ✅ Can fetch from origin

   ❌ If any fail → STOP and ASK USER

┌─────────────────────────────────────────────────────────────┐
│  PHASE 2: TASK PICKUP & PREPARATION                          │
└─────────────────────────────────────────────────────────────┘

3. Agent picks up task from Trello (In Progress)

4. Pre-work git operations (MANDATORY):
   cd /home/ubuntu/projects/{project}/
   git checkout main
   git fetch origin
   git pull origin main
   git status

5. Break down task into subtasks:
   - Create feature branch
   - Implement code
   - Write tests
   - Run tests
   - Security scan
   - Code review
   - Commit
   - Push
   - Create PR

┌─────────────────────────────────────────────────────────────┐
│  PHASE 3: EXECUTION & REVIEW LOOPS                           │
└─────────────────────────────────────────────────────────────┘

6. Execute subtasks with feedback loops:

   FOR EACH subtask:
   a. Execute with working_directory context
   b. Reflective thinking (self-critique)
   c. If fails → Retry with different approach
   d. Max 3 attempts → Escalate

7. Code Review Loop:
   a. review_agent reviews code
   b. If issues found → Create fix task
   c. Re-run from step 6
   d. If approved → Proceed

8. Create PR (only after review approval):
   a. git push origin {branch}
   b. gh pr create --title ... --body ...
   c. Verify PR exists

9. PR Review Loop:
   a. pr_reviewer analyzes full PR
   b. Verdict: approved/needs_changes/rejected
   c. If not approved → Create fix task
   d. Loop back to step 6
   e. Max 3 iterations → Escalate

┌─────────────────────────────────────────────────────────────┐
│  PHASE 4: COMPLETION & NOTIFICATION                          │
└─────────────────────────────────────────────────────────────┘

10. PR Approved → Send Telegram notification:
    - Project name
    - PR number and URL
    - Branch names
    - All check results
    - Request to merge

11. Move Trello card to "Review Done" list

12. Mark task as complete

┌─────────────────────────────────────────────────────────────┐
│  PHASE 5: HUMAN MERGE (MANUAL)                               │
└─────────────────────────────────────────────────────────────┘

13. Human receives Telegram notification
14. Human reviews PR
15. Human merges PR
16. Human deletes branch (optional)
```

---

## 🚨 ERROR HANDLING (STRICT)

```python
ERROR_RECOVERY = {
    "project_not_found": """
        STOP. Ask user:
        "Project '{project_name}' not found in /home/ubuntu/projects/
         Current projects: {list_projects()}
         Please provide GitHub URL to set up."
    """,

    "git_remote_missing": """
        STOP. Ask user:
        "Git remote not configured for {project}
         Please provide:
         1. GitHub repository URL
         2. Git remote name (origin/upstream)"
    """,

    "git_fetch_failed": """
        STOP. Ask user:
        "Cannot fetch from origin for {project}
         Please check:
         1. Internet connection
         2. GitHub credentials
         3. Repository permissions"
    """,

    "tests_failing": """
        STOP. Do NOT create PR.
        Create fix task in Trello with:
        - Test failures
        - Error logs
        - Suggested fixes
    """,

    "security_issues_found": """
        STOP. Do NOT create PR.
        Create fix task in Trello with:
        - Security vulnerabilities
        - Severity levels
        - Required fixes
    """,

    "review_rejected": """
        STOP. Do NOT create PR.
        Create fix task in Trello with:
        - Review feedback
        - Required changes
        - Blocker issues
    """,

    "pr_review_rejected": """
        STOP. Do NOT notify Telegram.
        Create fix task in Trello with:
        - PR review feedback
        - Verdict: rejected
        - All issues to fix
    """,

    "max_iterations_reached": """
        STOP. Escalate to human.
        Send Telegram:
        "🚨 ESCALATION REQUIRED
         Task: {task}
         After {n} iterations, cannot complete.
         Please review: {trello_url}"
    """,
}
```

---

## 📁 PROJECT STRUCTURE (STRICT)

```
/home/ubuntu/
├── projects/
│   ├── laptop-recommendation/          ✅ VALID
│   │   ├── .git/config                 → remote: git@github.com:TheCurators/laptop-recommendation.git
│   │   ├── README.md
│   │   └── ...
│   │
│   ├── web-api/                        ✅ VALID
│   │   ├── .git/config                 → remote: git@github.com:TheCurators/web-api.git
│   │   └── ...
│   │
│   └── {project-name}/                 ✅ PATTERN
│       ├── .git/config                 → MUST have origin remote
│       └── ...
│
├── agents/                             ✅ Autonomous agent system
├── worker/                             ✅ Trello integration
└── STRICT_E2E_RULES.md                 ✅ THIS FILE
```

---

## 🔍 VALIDATION CHECKLISTS

### Project Setup Validation
```python
def validate_project(project_name: str) -> bool:
    """Strict project validation."""

    checks = {
        "folder_exists": Path(f"/home/ubuntu/projects/{project_name}").exists(),
        "is_git_dir": Path(f"/home/ubuntu/projects/{project_name}/.git").exists(),
        "has_remote": check_git_remote(project_name),
        "can_fetch": test_git_fetch(project_name),
        "remote_is_github": is_github_remote(project_name),
    }

    if not all(checks.values()):
        missing = [k for k, v in checks.items() if not v]
        raise ProjectValidationError(
            f"Project {project_name} validation failed: {missing}"
        )

    return True
```

### Pre-Commit Validation
```python
def validate_before_commit(project_name: str) -> bool:
    """Strict pre-commit validation."""

    checks = {
        "on_feature_branch": check_branch_type("feature/*"),
        "branch_from_main": verify_branch_from_main(),
        "tests_pass": run_tests()["exit_code"] == 0,
        "security_clean": security_scan()["issues"] == [],
        "review_approved": get_review_status() == "approved",
    }

    if not all(checks.values()):
        return False

    return True
```

### Pre-PR Validation
```python
def validate_before_pr(project_name: str) -> bool:
    """Strict pre-PR validation."""

    checks = {
        "committed": check_git_status(clean=True),
        "pushed_to_origin": verify_branch_on_remote(),
        "review_approved": get_review_status() == "approved",
        "tests_pass": run_tests()["exit_code"] == 0,
        "security_clean": security_scan()["issues"] == [],
    }

    if not all(checks.values()):
        raise PrePRValidationError(f"Cannot create PR: {checks}")

    return True
```

---

## ✅ FINAL ACCEPTANCE CRITERIA

A task is ONLY complete when ALL of:

1. ✅ Code written in correct project directory
2. ✅ Tests written and passing
3. ✅ Security scan passed (no critical/high issues)
4. ✅ Code review approved
5. ✅ Committed with conventional commit message
6. ✅ Pushed to origin remote
7. ✅ PR created on GitHub
8. ✅ PR review approved (automated reviewer)
9. ✅ Telegram notification sent
10. ✅ Trello card moved to "Review Done"

**IF ANY STEP FAILS → DO NOT PROCEED → CREATE FIX TASK**

---

## 🚨 ZERO TOLERANCE POLICY

```
NEVER ASSUME → ALWAYS VALIDATE
NEVER GUESS → ALWAYS VERIFY
NEVER SKIP → ALWAYS FOLLOW CHECKLIST
NEVER PROCEED WITHOUT VALIDATION

IF UNCERTAIN → STOP AND ASK
IF ERROR → STOP AND ESCALATE
IF UNABLE TO VALIDATE → STOP AND ASK USER
```

---

## 📞 ESCALATION PROCEDURE

```python
def escalate_to_human(reason: str, context: dict):
    """Escalate to human when unable to proceed."""

    message = f"""
🚨 AUTONOMOUS AGENT ESCALATION

Reason: {reason}

Context:
{json.dumps(context, indent=2)}

Task URL: {trello_card_url}
Project: {project_name}

PLEASE REVIEW AND TAKE ACTION.
    """

    send_telegram_notification(message)
    create_trello_card(
        name=f"[ESCALATION] {project_name}: {reason}",
        description=message,
        priority="P0"
    )
```

---

## 📋 DAILY OPERATION CHECKLIST

### Before Starting Work
- [ ] Verify all projects have correct git remotes
- [ ] Verify GitHub credentials are valid
- [ ] Verify Trello connection is working
- [ ] Verify Telegram bot is working

### During Work
- [ ] Every task validated before pickup
- [ ] Every git pull from origin before coding
- [ ] Every code review passed before commit
- [ ] Every PR review passed before notification

### After Work
- [ ] All PRs notified via Telegram
- [ ] All Trello cards moved to correct lists
- [ ] All errors escalated
- [ ] All projects in clean state

---

## 🔧 SETUP REQUIRED

### Environment Variables
```bash
# Required
GITHUB_TOKEN=ghp_xxx
TELEGRAM_BOT_TOKEN=xxx
TELEGRAM_CHAT_ID=xxx
TRELLO_API_KEY=xxx
TRELLO_TOKEN=xxx
ANTHROPIC_API_KEY=xxx

# Project-specific (optional)
LAPTOP_RECOMMENDATION_REPO=git@github.com:TheCurators/laptop-recommendation.git
WEB_API_REPO=git@github.com:TheCurators/web-api.git
# ... etc
```

### Git Configuration
```bash
# All projects must use SSH remotes
git@github.com:TheCurators/{project}.git

# Never use HTTPS for automation
# https://github.com/... ❌
```

---

## 📝 CHANGELOG

### Version 1.0 - Initial Strict Rules
- Established zero-tolerance policy for errors
- Defined strict validation at every step
- Implemented feedback loops at every stage
- Added escalation procedures
- Created Telegram notification system

### Version History
- All violations documented
- All fixes applied
- All lessons learned incorporated

---

## 🎯 SUCCESS METRICS

```
ZERO_MISTAKES_GOAL = {
    "wrong_repository": 0,
    "stale_main_branch": 0,
    "failed_tests_committed": 0,
    "security_issues_committed": 0,
    "pr_without_review": 0,
    "missing_telegram_notify": 0,
    "wrong_project_path": 0,
}

Current Status: ENFORCING STRICT VALIDATION
```

---

**THIS IS THE LAW. FOLLOW IT STRICTLY. NO EXCEPTIONS.**
