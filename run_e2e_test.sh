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
if [ -f /home/ubuntu/venv/bin/activate ]; then
    source /home/ubuntu/venv/bin/activate
    echo "✅ Virtual environment activated"
else
    echo "❌ Virtual environment not found at /home/ubuntu/venv"
    echo "   Please create it first:"
    echo "   python3 -m venv /home/ubuntu/venv"
    echo "   source /home/ubuntu/venv/bin/activate"
    echo "   pip install -r requirements.txt"
    exit 1
fi

# Set PYTHONPATH
export PYTHONPATH="/home/ubuntu:$PYTHONPATH"
echo "✅ PYTHONPATH set to /home/ubuntu"

# Check prerequisites
echo "Checking prerequisites..."
python3 -c "
from worker.trello.client import get_trello_client
from agents.orchestrator.task_context import get_task_context_manager
print('✅ All imports successful')
" || { echo "❌ Import check failed"; exit 1; }

echo "✅ Environment ready"
echo ""

# Phase 2: Clean up old test data
echo "📋 Phase 2: Cleanup Old Test Data"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Remove old checkpoints
rm -f /tmp/task_checkpoints/test*.json 2>/dev/null || true
echo "✅ Old checkpoints cleaned"

# Stop any running orchestrator
pkill -f run_orchestrator_on_trello || true
sleep 2
echo "✅ Orchestrator stopped"

# Phase 3: Verify setup test repo
echo "📋 Phase 3: Verify Test Repository"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

if [ ! -d /home/ubuntu/test-orchestrator-repo ]; then
    echo "Creating test repository..."
    mkdir -p /home/ubuntu/test-orchestrator-repo
    cd /home/ubuntu/test-orchestrator-repo
    git init
    echo "# Test Repository for Orchestrator E2E Testing" > README.md
    git add .
    git commit -m "Initial commit"

    # Check if repo exists on GitHub
    if gh repo view test-orchestrator &>/dev/null; then
        echo "✅ GitHub repo exists"
    else
        echo "Creating GitHub repo..."
        gh repo create test-orchestrator --public --source=. --remote=origin || {
            echo "⚠️  Could not create GitHub repo (may already exist)"
        }
    fi
else
    echo "✅ Test repository exists"
fi

# Phase 4: Create test tasks
echo ""
echo "📋 Phase 4: Create Test Tasks"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python3 /home/ubuntu/create_test_tasks.py || { echo "❌ Task creation failed"; exit 1; }
echo ""

# Phase 5: Verify tasks
echo "📋 Phase 5: Verify Tasks Created"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
python3 -c "
from worker.trello.client import get_trello_client
import asyncio
async def check():
    client = get_trello_client()
    cards = await client.get_todo_cards()
    print(f'Found {len(cards)} tasks in TODO:')
    for card in cards:
        # Note: Task model doesn't have labels directly
        # Labels are stored in metadata or accessed via Trello API
        print(f'  - {card.title}')
        if hasattr(card, 'priority'):
            print(f'    Priority: {card.priority}')
asyncio.run(check())
"
echo ""

# Phase 6: Start orchestrator
echo "📋 Phase 6: Start Orchestrator"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

cd /home/ubuntu

# Start orchestrator in background
nohup python3 run_orchestrator_on_trello.py > /tmp/orchestrator.log 2>&1 &
ORCH_PID=$!
echo "Orchestrator started (PID: $ORCH_PID)"
echo "  Log file: /tmp/orchestrator.log"
echo ""

# Wait for startup
sleep 5

# Check if process is running
if ps -p $ORCH_PID > /dev/null; then
    echo "✅ Orchestrator is running"
else
    echo "❌ Orchestrator failed to start"
    echo "Check log: tail -20 /tmp/orchestrator.log"
    exit 1
fi

# Phase 7: Monitor progress
echo ""
echo "📋 Phase 7: Monitor Progress"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Monitoring for 10 minutes (will stop early if all tasks complete)..."
echo ""

MAX_CHECKS=20
CHECK_INTERVAL=30

for i in $(seq 1 $MAX_CHECKS); do
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Check $i/$MAX_CHECKS - $(date +%H:%M:%S)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    # Show Trello status
    echo "📊 Trello Status:"
    python3 -c "
from worker.trello.client import get_trello_client
import asyncio
async def status():
    try:
        client = get_trello_client()

        # Check each list
        todo = await client.get_todo_cards()
        in_progress = await client.get_in_progress_cards()
        review = await client.get_review_cards()

        # Get Done list (note: 'Done' not 'done')
        done = []
        try:
            # Can't easily get done cards without a specific method
            # Just show what we have
            pass
        except:
            pass

        if todo:
            print(f'  TODO: {len(todo)} cards')
            for card in todo[:2]:
                title = card.title[:40] + ('...' if len(card.title) > 40 else '')
                priority = card.priority if hasattr(card, 'priority') else 'N/A'
                print(f'    - {title} [{priority}]')

        if in_progress:
            print(f'  In Progress: {len(in_progress)} cards')
            for card in in_progress[:2]:
                title = card.title[:40] + ('...' if len(card.title) > 40 else '')
                print(f'    - {title}')

        if review:
            print(f'  Review: {len(review)} cards')
            for card in review[:2]:
                title = card.title[:40] + ('...' if len(card.title) > 40 else '')
                print(f'    - {title}')

    except Exception as e:
        print(f'  Error: {e}')
asyncio.run(status())
" 2>/dev/null

    # Show recent log lines
    echo ""
    echo "📝 Recent Activity:"
    if [ -f /tmp/orchestrator.log ]; then
        tail -10 /tmp/orchestrator.log 2>/dev/null | grep -E "Task:|PR #|Verdict:|✅|❌|🔄" | tail -5 || echo "  (waiting for activity...)"
    else
        echo "  (waiting for log file...)"
    fi

    # Check if all tasks done
    todo_count=$(python3 -c "
import asyncio
from worker.trello.client import get_trello_client
async def count():
    try:
        client = get_trello_client()
        cards = await client.get_todo_cards()
        print(len(cards))
    except:
        print('-1')
asyncio.run(count())
" 2>/dev/null || echo "0")

    # Check if orchestrator still running
    if ! ps -p $ORCH_PID > /dev/null; then
        echo ""
        echo "⚠️  Orchestrator process stopped!"
        echo "   Check log: tail -50 /tmp/orchestrator.log"
        break
    fi

    if [ "$todo_count" -eq "0" ]; then
        echo ""
        echo "✅ All tasks completed!"
        break
    fi

    if [ $i -lt $MAX_CHECKS ]; then
        echo ""
        echo "⏳ Waiting ${CHECK_INTERVAL}s..."
        sleep $CHECK_INTERVAL
    fi
done

echo ""
echo "📋 Phase 8: Final Verification"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Stop orchestrator
if ps -p $ORCH_PID > /dev/null; then
    echo "Stopping orchestrator..."
    kill $ORCH_PID 2>/dev/null || true
    sleep 2
fi

# Show final stats
python3 << 'EOF'
import asyncio
import os
from worker.trello.client import get_trello_client
from agents.orchestrator.task_context import get_task_context_manager

async def final_report():
    client = get_trello_client()
    manager = get_task_context_manager()

    print("\n" + "="*70)
    print("                    FINAL REPORT")
    print("="*70)

    # Trello status
    print("\n📊 Trello Board Status:")

    stats = {}
    # Get cards from each list using available methods
    todo = await client.get_todo_cards()
    in_progress = await client.get_in_progress_cards()
    review = await client.get_review_cards()

    stats['TODO'] = todo
    stats['In Progress'] = in_progress
    stats['Review'] = review
    stats['Done'] = []  # Can't easily get done cards

    for name, cards in stats.items():
        if cards:
            print(f"\n{name}: {len(cards)} cards")
            for card in cards:
                print(f"  - {card.title}")
                if hasattr(card, 'priority'):
                    print(f"    Priority: {card.priority}")

    # Checkpoint summary
    print("\n💾 Checkpoint Summary:")
    checkpoints = manager.list_all_checkpoints()
    print(f"Total checkpoints: {len(checkpoints)}")

    if checkpoints:
        for card_id in checkpoints[:5]:  # Show first 5
            ctx = manager.load_checkpoint(card_id)
            if ctx:
                print(f"\n  📋 {ctx.trello_card_id}:")
                print(f"     Task: {ctx.original_task[:50]}...")
                print(f"     Iterations: {ctx.current_iteration}")
                if ctx.current_pr_number:
                    print(f"     PR: #{ctx.current_pr_number}")
                print(f"     Status: {ctx.current_status.value}")

                # Show iteration details
                if ctx.iterations:
                    for iteration in ctx.iterations:
                        verdict = iteration.review_verdict.value if iteration.review_verdict else "PENDING"
                        print(f"       - Iteration {iteration.iteration_number}: {iteration.status} ({verdict})")

    # Test results summary
    print("\n✅ Test Results:")
    done_count = len(stats.get('Done', []))
    in_progress_count = len(stats.get('In Progress', []))
    review_count = len(stats.get('Review', []))
    todo_count = len(stats.get('TODO', []))

    total_tasks = done_count + in_progress_count + review_count + todo_count
    completed = done_count / total_tasks if total_tasks > 0 else 0

    print(f"  Total tasks: {total_tasks}")
    print(f"  Completed: {done_count} ({completed*100:.0f}%)")
    print(f"  In Progress: {in_progress_count}")
    print(f"  In Review: {review_count}")
    print(f"  Pending: {todo_count}")

    print("\n" + "="*70)

    if done_count == total_tasks and total_tasks > 0:
        print("            🎉 ALL TESTS PASSED! 🎉")
    elif done_count > 0:
        print("            ⚠️  PARTIAL SUCCESS")
        print(f"            {done_count}/{total_tasks} tasks completed")
    else:
        print("            ❌ TESTS FAILED")

    print("="*70)

asyncio.run(final_report())
EOF

echo ""
echo "📋 Phase 9: Cleanup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo ""
echo "💾 Logs saved to: /tmp/orchestrator.log"
echo "💾 Checkpoints saved to: /tmp/task_checkpoints/"
echo ""
echo "To view detailed logs:"
echo "  tail -100 /tmp/orchestrator.log | less"
echo ""
echo "To clean up test data:"
echo "  rm -f /tmp/task_checkpoints/test*.json"
echo "  # Or manually delete test tasks from Trello"
echo ""

echo "╔════════════════════════════════════════════════════════════╗"
echo "║              E2E TEST SUITE COMPLETE                        ║"
echo "╚════════════════════════════════════════════════════════════╝"
