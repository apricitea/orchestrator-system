# Autonomous Agent Guidelines - TRELLO FORMAT

## TRELLO CARD FORMAT (MANDATORY)

All Trello cards MUST follow this exact format:

```
[project-name] [agent] P#: Task description here
```

### Components:

1. **[project-name]**: Project identifier
   - Example: `[laptop-recommendation]`
   - Must be the first tag in square brackets

2. **[agent]**: Agent task indicator
   - Literal text `[agent]`
   - Indicates this is an autonomous agent task

3. **P#**: Priority level
   - P0: Critical
   - P1: High
   - P2: Medium
   - P3: Low

4. **Description**: Task description
   - Clear, concise description of what needs to be done

### Examples:

✅ **CORRECT**:
```
[laptop-recommendation] [agent] P0: Add price drop email notifications
[laptop-recommendation] [agent] P1: Fix scraper rate limiting issue
[laptop-recommendation] [agent] P2: Add keyboard navigation support
[laptop-recommendation] [agent] P3: Update README with new features
```

❌ **INCORRECT**:
```
[coding_agent] Add email notifications  (wrong agent tag)
[laptop-recommendation] Add notifications (missing priority)
Email notifications task (missing project and agent tags)
```

---

## TASK DESCRIPTION FORMAT

Every Trello card MUST include a detailed description:

```markdown
## Task Description
Brief summary of what needs to be done

## Requirements
1. Requirement 1
2. Requirement 2
3. Requirement 3

## Working Directory
/home/ubuntu/projects/project-name

## Expected Workflow:
1. [git_agent] Create feature branch
2. [coding_agent] Implement feature
3. [testing_agent] Write tests
4. [review_agent] Code review
5. [git_agent] Commit changes
6. [git_agent] Create pull request
```

---

## PRIORITY LEVELS

| Priority | Label Color | Usage                      | Response Time |
|----------|-------------|----------------------------|---------------|
| P0       | Red         | Critical/Bug               | Immediate     |
| P1       | Orange      | High priority              | < 1 hour      |
| P2       | Yellow      | Medium priority            | < 1 day       |
| P3       | Green       | Low priority/Enhancement    | < 1 week      |

---

## SPECIAL TAGS

Supported special tags (in addition to project name):
- `[agent]` - Autonomous agent task (REQUIRED)
- `[bug]` - Bug fix
- `[feature]` - New feature
- `[hotfix]` - Emergency hotfix

---

## WORKING DIRECTORY

The working directory MUST be specified in the task description:

```markdown
## Working Directory
/home/ubuntu/projects/project-name
```

Supported formats:
- Inline: `Working Directory: /path/to/project`
- Markdown: `## Working Directory\n/path/to/project`

---

## ORCHESTRATOR WORKFLOW

### 1. Task Selection
- P0 tasks processed first
- P1 tasks second
- P2 tasks third
- P3 tasks last

### 2. Task Decomposition
Tasks are automatically decomposed into subtasks:

```json
[
  {"agent": "git_agent", "task": "Create feature branch", ...},
  {"agent": "coding_agent", "task": "Implement feature", ...},
  {"agent": "testing_agent", "task": "Write tests", ...},
  {"agent": "review_agent", "task": "Code review", ...},
  {"agent": "git_agent", "task": "Commit changes", ...},
  {"agent": "git_agent", "task": "Create PR", ...}
]
```

### 3. Agent Routing
Subtasks are routed to specialized agents:
- **git_agent**: Git operations (branch, commit, PR)
- **coding_agent**: Code implementation
- **testing_agent**: Test creation and execution
- **review_agent**: Code review
- **security_agent**: Security scanning
- **debug_agent**: Bug fixing
- **docs_agent**: Documentation

### 4. Execution
- Tasks executed in dependency order
- Parallel execution of independent tasks
- Automatic retry on failure
- Checkpoint-based recovery

### 5. Pull Request Creation
- PR automatically created after all subtasks complete
- PR review automatically triggered
- Trello card updated with PR URL

---

## VERIFICATION CHECKLIST

Before creating a Trello card, verify:

- [ ] Format: `[project-name] [agent] P#: Description`
- [ ] Priority label assigned (P0/P1/P2/P3)
- [ ] Working directory specified
- [ ] Requirements clearly listed
- [ ] Expected workflow defined
- [ ] Project name matches actual project

---

## BEST PRACTICES

### DO:
✅ Use consistent naming conventions
✅ Provide detailed requirements
✅ Specify working directory explicitly
✅ Include security requirements when applicable
✅ Define clear acceptance criteria
✅ Use priority levels appropriately

### DON'T:
❌ Create vague tasks
❌ Forget the [agent] tag
❌ Skip priority labels
❌ Omit working directory
❌ Mix multiple features in one task
❌ Use P0 for non-critical issues

---

## EXAMPLE TASKS

### P0 - Critical Bug Fix
```
[laptop-recommendation] [agent] P0: Fix memory leak in scraper

## Requirements
1. Investigate memory leak in Amazon scraper
2. Fix leak and add memory monitoring
3. Add unit tests to prevent regression
4. Deploy fix to production

## Working Directory
/home/ubuntu/projects/laptop-recommendation
```

### P1 - High Priority Feature
```
[laptop-recommendation] [agent] P1: Add user authentication

## Requirements
1. Implement JWT-based authentication
2. Add login/register endpoints
3. Create user profile management
4. Add unit tests with 80%+ coverage

## Working Directory
/home/ubuntu/projects/laptop-recommendation
```

### P2 - Medium Priority Enhancement
```
[laptop-recommendation] [agent] P2: Implement search filters

## Requirements
1. Add price range filter
2. Add brand filter
3. Add specs filter
4. Update UI for filter selection

## Working Directory
/home/ubuntu/projects/laptop-recommendation
```

### P3 - Low Priority Documentation
```
[laptop-recommendation] [agent] P3: Update API documentation

## Requirements
1. Document new endpoints
2. Add usage examples
3. Update authentication section
4. Add troubleshooting guide

## Working Directory
/home/ubuntu/projects/laptop-recommendation
```

---

## AGENT CAPABILITIES

### git_agent
- Create/delete branches
- Commit changes
- Create pull requests
- Push to remote
- Clone repositories

### coding_agent
- Write code in any language
- Follow security best practices
- Implement error handling
- Add logging and monitoring

### testing_agent
- Write unit tests
- Execute test suites
- Generate coverage reports
- Test edge cases

### review_agent
- Code quality review
- Security review
- Architecture review
- Performance analysis

### security_agent
- Scan for vulnerabilities
- Check for hardcoded secrets
- Validate input sanitization
- Test for XSS/SQL injection

---

## FILES AND CONFIGURATION

### Modified Files for Proper Format Support:

1. **/home/ubuntu/worker/trello/client.py** (lines 220-240)
   - Parses tags from Trello card titles
   - Extracts project name and agent indicator
   - Removes tags to get clean description

2. **/home/ubuntu/agents/workers/git_agent.py** (lines 119-147)
   - Enhanced working directory extraction
   - Supports both inline and markdown formats

3. **/home/ubuntu/agents/orchestrator/main_orchestrator.py** (lines 478-500)
   - Working directory propagation to subtasks
   - Multi-line format support

---

## TROUBLESHOOTING

### Task not being picked up?
- Check format: `[project-name] [agent] P#: Description`
- Verify priority label is assigned
- Ensure task is in "To do" list

### Wrong working directory?
- Check task description includes `## Working Directory`
- Verify path is correct and accessible
- Check filesystem jail configuration

### PR not being created?
- Verify git push authentication
- Check repository permissions
- Ensure branch is pushed to remote

---

## STATUS

✅ All guidelines implemented and tested
✅ Proper format verified in production
✅ Autonomous orchestrator fully functional

**Last Updated**: 2026-01-29
**Status**: PRODUCTION READY
