"""
RAG (Retrieval Augmented Generation) Agent Package

Provides context-aware agent responses using vector search over codebase
and documentation.
"""

from agents.rag.retrieval_agent import RetrievalAgent, create_rag_agent

__all__ = [
    "RetrievalAgent",
    "create_rag_agent",
]
