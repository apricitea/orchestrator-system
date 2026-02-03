"""
Agent Coordination Module

Implements advanced multi-agent coordination patterns:
- Debate system (adversarial collaboration)
- Reflective thinking (self-critique)
- Consensus building
"""

from agents.coordination.agent_debate import (
    AgentDebateManager,
    Challenge,
    ChallengeSeverity,
    DebateResult,
    DebateRound,
    DebateState,
    get_debate_manager,
)

__all__ = [
    "AgentDebateManager",
    "Challenge",
    "ChallengeSeverity",
    "DebateResult",
    "DebateRound",
    "DebateState",
    "get_debate_manager",
]
