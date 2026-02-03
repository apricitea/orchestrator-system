"""
Multi-Agent Debate System

Implements adversarial collaboration between agents:
- Agents can challenge each other's work
- Security agent challenges coding agent on security
- Review agent mediates disputes
- Consensus-based decision making
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Literal

from agents.base.agent_interface import AgentRegistry, get_agent_registry
from agents.base.base_agent import AgentResult
from utils.logger import get_logger


class DebateState(str, Enum):
    """State of the debate."""
    INITIATED = "initiated"
    IN_PROGRESS = "in_progress"
    CONSENSUS = "consensus"
    ESCALATED = "escalated"
    TIMEOUT = "timeout"


class ChallengeSeverity(str, Enum):
    """Severity level of a challenge."""
    LOW = "low"  # Suggestion, not blocking
    MEDIUM = "medium"  # Should address before proceeding
    HIGH = "high"  # Must address, blocking issue
    CRITICAL = "critical"  # Security/safety critical, must fix


@dataclass
class Challenge:
    """A challenge raised by one agent against another's work."""
    id: str
    challenger_agent: str  # Agent raising the challenge
    target_agent: str  # Agent whose work is being challenged
    severity: ChallengeSeverity
    category: Literal["security", "quality", "architecture", "best_practices", "other"]
    title: str
    description: str
    evidence: List[str] = field(default_factory=list)
    suggested_fix: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    resolved: bool = False
    resolution: Optional[str] = None


@dataclass
class DebateRound:
    """One round of debate between agents."""
    round_number: int
    proposal: Dict[str, Any]
    challenges: List[Challenge]
    responses: Dict[str, str] = field(default_factory=dict)
    consensus_reached: bool = False


@dataclass
class DebateResult:
    """Result of the debate process."""
    state: DebateState
    rounds: List[DebateRound]
    final_decision: str  # "accept", "revise", "reject"
    challenges_resolved: int
    challenges_blocking: int
    consensus_summary: str
    modified_proposal: Optional[Dict[str, Any]] = None


class AgentDebateManager:
    """
    Manages debates between agents.

    Implements adversarial collaboration to improve code quality:
    1. Proposing agent presents work
    2. Challenging agents review and raise issues
    3. Proposing agent responds to challenges
    4. Mediator facilitates consensus
    5. Iterate until consensus or escalation
    """

    def __init__(self, registry: Optional[AgentRegistry] = None):
        """Initialize debate manager."""
        self.registry = registry or get_agent_registry()
        self.logger = get_logger("agent_debate")
        self.max_rounds = 3
        self.timeout_seconds = 300  # 5 minutes max per debate

        # Define which agents should review which agents
        self.review_pairs = {
            "coding_agent": ["security_agent", "review_agent"],
            "security_agent": ["review_agent"],
            "testing_agent": ["review_agent"],
            "docs_agent": ["review_agent"],
            "deploy_agent": ["security_agent", "review_agent"],
        }

    async def initiate_debate(
        self,
        proposing_agent: str,
        proposal: Dict[str, Any],
        task_context: Dict[str, Any],
    ) -> DebateResult:
        """
        Initiate a debate on work from proposing_agent.

        Args:
            proposing_agent: Agent whose work is being debated
            proposal: The work being proposed (code, config, etc.)
            task_context: Context about the original task

        Returns:
            Debate result with consensus decision
        """
        self.logger.info(
            "Initiating debate",
            proposer=proposing_agent,
            task=task_context.get("task", "")[:50],
        )

        start_time = asyncio.get_event_loop().time()
        rounds = []

        # Identify challengers based on review pairs
        challengers = self.review_pairs.get(proposing_agent, ["review_agent"])

        for round_num in range(1, self.max_rounds + 1):
            self.logger.info("Debate round", round=round_num, proposer=proposing_agent)

            # Round 1: Challengers review proposal
            if round_num == 1:
                challenges = await self._collect_challenges(
                    challengers=challengers,
                    proposing_agent=proposing_agent,
                    proposal=proposal,
                    task_context=task_context,
                )
            else:
                # Subsequent rounds: Only unresolved challenges
                challenges = await self._collect_challenges(
                    challengers=challengers,
                    proposing_agent=proposing_agent,
                    proposal=proposal,
                    task_context=task_context,
                    previous_challenges=[
                        c for r in rounds for c in r.challenges if not c.resolved
                    ],
                )

            debate_round = DebateRound(
                round_number=round_num,
                proposal=proposal,
                challenges=challenges,
            )
            rounds.append(debate_round)

            # Check if no challenges → accept
            if not challenges:
                self.logger.info("No challenges raised", round=round_num)
                return DebateResult(
                    state=DebateState.CONSENSUS,
                    rounds=rounds,
                    final_decision="accept",
                    challenges_resolved=0,
                    challenges_blocking=0,
                    consensus_summary="No challenges raised. Work accepted as-is.",
                )

            # Categorize challenges
            blocking_challenges = [
                c for c in challenges
                if c.severity in [ChallengeSeverity.HIGH, ChallengeSeverity.CRITICAL]
            ]

            # If no blocking challenges → accept with suggestions
            if not blocking_challenges:
                self.logger.info("No blocking challenges", round=round_num)
                return DebateResult(
                    state=DebateState.CONSENSUS,
                    rounds=rounds,
                    final_decision="accept",
                    challenges_resolved=len(challenges),
                    challenges_blocking=0,
                    consensus_summary=self._generate_nonblocking_summary(challenges),
                )

            # Give proposing agent chance to respond
            responses = await self._collect_responses(
                proposing_agent=proposing_agent,
                challenges=blocking_challenges,
                proposal=proposal,
            )
            debate_round.responses = responses

            # Check if all challenges addressed
            all_resolved = all(c.resolved for c in blocking_challenges)
            if all_resolved:
                self.logger.info("All challenges resolved", round=round_num)
                return DebateResult(
                    state=DebateState.CONSENSUS,
                    rounds=rounds,
                    final_decision="accept",
                    challenges_resolved=len(blocking_challenges),
                    challenges_blocking=0,
                    consensus_summary=self._generate_resolved_summary(blocking_challenges),
                )

            # Check timeout
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > self.timeout_seconds:
                self.logger.warning("Debate timeout", elapsed=elapsed)
                return DebateResult(
                    state=DebateState.TIMEOUT,
                    rounds=rounds,
                    final_decision="escalate",
                    challenges_resolved=0,
                    challenges_blocking=len(blocking_challenges),
                    consensus_summary="Debate timeout. Escalating to human review.",
                )

        # Max rounds reached without consensus
        self.logger.warning("Max rounds reached", rounds=self.max_rounds)
        return DebateResult(
            state=DebateState.ESCALATED,
            rounds=rounds,
            final_decision="escalate",
            challenges_resolved=0,
            challenges_blocking=len(blocking_challenges),
            consensus_summary=self._generate_escalation_summary(blocking_challenges),
        )

    async def _collect_challenges(
        self,
        challengers: List[str],
        proposing_agent: str,
        proposal: Dict[str, Any],
        task_context: Dict[str, Any],
        previous_challenges: Optional[List[Challenge]] = None,
    ) -> List[Challenge]:
        """Collect challenges from all challenger agents."""
        challenges = []

        for challenger in challengers:
            if not self.registry.is_registered(challenger):
                self.logger.warning("Challenger not registered", agent=challenger)
                continue

            self.logger.info(
                "Requesting challenge",
                challenger=challenger,
                target=proposing_agent,
            )

            # Call challenger agent with review task
            result = await self.registry.call_agent(
                challenger,
                f"Review work from {proposing_agent} and raise any challenges. "
                f"Task: {task_context.get('task', '')}",
                proposal=proposal,
                task_context=task_context,
                previous_challenges=previous_challenges,
                review_mode="challenge",  # Special mode for challenges
            )

            # Extract challenges from result
            if result.metadata and "challenges" in result.metadata:
                agent_challenges = result.metadata["challenges"]
                if isinstance(agent_challenges, list):
                    challenges.extend(agent_challenges)

        # Filter duplicates based on title
        seen_titles = set()
        unique_challenges = []
        for challenge in challenges:
            if challenge.title not in seen_titles:
                seen_titles.add(challenge.title)
                unique_challenges.append(challenge)

        return unique_challenges

    async def _collect_responses(
        self,
        proposing_agent: str,
        challenges: List[Challenge],
        proposal: Dict[str, Any],
    ) -> Dict[str, str]:
        """Collect responses from proposing agent to challenges."""
        if not self.registry.is_registered(proposing_agent):
            self.logger.error("Proposing agent not registered", agent=proposing_agent)
            return {}

        self.logger.info(
            "Requesting responses",
            proposer=proposing_agent,
            num_challenges=len(challenges),
        )

        result = await self.registry.call_agent(
            proposing_agent,
            f"Address these {len(challenges)} challenges to your work",
            challenges=[c.__dict__ for c in challenges],
            proposal=proposal,
            respond_to_challenges=True,
        )

        responses = {}
        if result.metadata and "challenge_responses" in result.metadata:
            responses = result.metadata["challenge_responses"]

        # Mark resolved challenges
        for challenge in challenges:
            if str(challenge.id) in responses:
                response = responses[str(challenge.id)]
                if any(
                    word in response.lower()
                    for word in ["fixed", "addressed", "resolved", "corrected"]
                ):
                    challenge.resolved = True
                    challenge.resolution = response

        return responses

    def _generate_nonblocking_summary(self, challenges: List[Challenge]) -> str:
        """Generate summary for non-blocking challenges."""
        lines = ["Work accepted with suggestions:"]
        for challenge in challenges:
            lines.append(f"- {challenge.title}: {challenge.description}")
        return "\n".join(lines)

    def _generate_resolved_summary(self, challenges: List[Challenge]) -> str:
        """Generate summary for resolved challenges."""
        lines = ["All challenges were successfully addressed:"]
        for challenge in challenges:
            lines.append(
                f"- {challenge.title}: {challenge.resolution or 'Addressed'}"
            )
        return "\n".join(lines)

    def _generate_escalation_summary(self, challenges: List[Challenge]) -> str:
        """Generate summary for escalation."""
        lines = [
            "Unable to reach consensus. Escalating to human review.",
            "\nUnresolved blocking issues:",
        ]
        for challenge in challenges:
            lines.append(
                f"- [{challenge.severity.value.upper()}] {challenge.title}: "
                f"{challenge.description}"
            )
            if challenge.suggested_fix:
                lines.append(f"  Suggested: {challenge.suggested_fix}")
        return "\n".join(lines)


def get_debate_manager() -> AgentDebateManager:
    """Get global debate manager instance."""
    return AgentDebateManager()
