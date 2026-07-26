"""
Retrieval Augmented Generation (RAG) Agent

Enhances LLM responses with relevant context from:
- Codebase documentation
- Similar code patterns
- Historical solutions
- Best practices
"""

from typing import Any, Dict, List, Optional

from agents.base.base_agent import BaseAgent, AgentConfig, AgentResult
from config.settings import get_settings
from memory.embeddings import get_embedding_service
from memory.long_term.vector_store import VectorStore
from models.llm.llm_wrapper import get_llm_wrapper, LLMResponse
from utils.logger import get_logger


class RetrievalAgent(BaseAgent):
    """
    Retrieval Augmented Generation (RAG) agent.

    Enhances LLM responses with relevant context from the codebase,
    documentation, and knowledge base.
    """

    def __init__(self, config: AgentConfig):
        super().__init__(config)
        self.embedding_service = get_embedding_service()
        self.vector_store = VectorStore()
        self.settings = get_settings()

    async def execute(self, task: str, **kwargs: Any) -> AgentResult:
        """
        Execute task with RAG-enhanced context.

        Args:
            task: Task description
            **kwargs: Additional parameters (language, file_type, etc.)

        Returns:
            Agent result with RAG-enhanced response
        """
        # Step 1: Generate query embedding
        query_embedding = await self.embedding_service.embed(task)

        # Step 2: Retrieve relevant context
        context_parts = []
        context_sources = []

        # Search codebase
        code_results = await self._search_codebase(task, query_embedding, limit=3)
        if code_results:
            context_parts.append("### Relevant Code:")
            for result in code_results:
                context_parts.append(f"File: {result['payload']['file_path']}")
                context_parts.append(f"```{result['payload']['language']}")
                code_snippet = result['payload'].get('code', '')[:500]  # Limit snippet size
                context_parts.append(code_snippet)
                context_parts.append("```")
            context_sources.append(f"{len(code_results)} code files")

        # Search documentation
        docs_results = await self._search_docs(query_embedding, limit=2)
        if docs_results:
            context_parts.append("\n### Relevant Documentation:")
            for result in docs_results:
                doc_content = result['payload'].get('content', '')[:400]
                context_parts.append(doc_content)
            context_sources.append(f"{len(docs_results)} docs")

        # Step 3: Build enhanced prompt
        if context_parts:
            enhanced_prompt = f"""Task: {task}

Relevant Context:
{chr(10).join(context_parts)}

Use this context to help complete the task. Adapt the patterns and code to your specific situation.
If the context isn't directly relevant, prioritize the user's request over the examples."""
        else:
            enhanced_prompt = task
            self.logger.logger.info("No RAG context found, using original task")

        # Step 4: Get LLM response with enhanced prompt
        llm = get_llm_wrapper()
        response: LLMResponse = await llm.generate(
            prompt=enhanced_prompt,
            model=self.config.model,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )

        return AgentResult(
            status="success",
            output=response.content,
            metadata={
                "tokens_used": response.total_tokens,
                "context_sources": context_sources,
                "rag_enabled": len(context_sources) > 0,
            },
        )

    async def validate(self, result: AgentResult) -> bool:
        """Validate RAG result."""
        return result.is_success()

    async def _search_codebase(
        self,
        query: str,
        query_vector: List[float],
        limit: int = 3,
    ) -> List[Dict[str, Any]]:
        """Search codebase for relevant code."""
        try:
            results = await self.vector_store.search(
                collection_name=self.vector_store.CODEBASE_COLLECTION,
                query_vector=query_vector,
                limit=limit,
                score_threshold=0.6,
            )
            return results
        except Exception as e:
            self.logger.logger.warning("Codebase search failed", error=str(e))
            return []

    async def _search_docs(
        self,
        query_vector: List[float],
        limit: int = 2,
    ) -> List[Dict[str, Any]]:
        """Search documentation."""
        try:
            results = await self.vector_store.search(
                collection_name=self.vector_store.DOCS_COLLECTION,
                query_vector=query_vector,
                limit=limit,
                score_threshold=0.6,
            )
            return results
        except Exception as e:
            self.logger.logger.warning("Documentation search failed", error=str(e))
            return []

    async def _search_patterns(
        self,
        language: Optional[str],
        limit: int = 3,
    ) -> List[Dict[str, Any]]:
        """Search for code patterns by language."""
        # This would search for common patterns in the PATTERNS collection
        # For now, return empty as patterns aren't indexed yet
        return []


async def create_rag_agent() -> RetrievalAgent:
    """Create and initialize the RAG agent."""
    config = AgentConfig(
        name="retrieval_agent",
        description="RAG-enhanced agent for context-aware responses",
        model=get_settings().default_model,
        temperature=0.7,
        max_tokens=4096,
    )

    return RetrievalAgent(config)
